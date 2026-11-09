import asyncio
import logging
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter
from fastapi.requests import Request
from pydantic import BaseModel, Field

from projects.hwhms.car_a.core import DecisionPath, IntentClassifier
from projects.hwhms.car_a.core_rewrite import QueryRewrite
from projects.hwhms.car_b.core import IntentClassifierCarB
from projects.hwhms.common import volcengine_api
from projects.hwhms.common.auth_utils import verify_authorization
from projects.hwhms.common.config.config import AppConfig
from projects.hwhms.common.constants import Domain

router = APIRouter()

logger = logging.getLogger(__name__)

# ========== 请求模型 ==========
class IntentClsRequest(BaseModel):
    input: str
    history: list[str] = []

class RewriteRequest(BaseModel):
    input: str
    history: list[str] = []

class History(BaseModel):
    q: str = Field(..., description="问题")
    a: str = Field(..., description="回答")

class Message(BaseModel):
    query: str = Field(..., description="用户最新一轮的问题")
    history: Optional[list[History]] = Field(default_factory=list, description="历史对话记录, q/a成对出现")
    chat_id: str = Field(..., description="聊天ID, 用于标识一次对话")
    question_id: str = Field(..., description="问题ID, 用于标识一次对话中的一个问题")
    car_type: Literal["CAR_A", "CAR_B"] = Field(..., description="车辆类型, 只能有两种值: CAR_A或CAR_B")

# ========== 响应模型 ==========
class IntentInfo(BaseModel):
    """意图识别信息"""
    domain: str = Field(..., description="意图领域")
    query: str = Field(..., description="原始查询")

class Choice(BaseModel):
    """单个选择结果"""
    rewritten_query: Optional[str] = Field(default=None, description="改写后的查询")
    intent: IntentInfo = Field(..., description="意图信息")
    reject: bool = Field(default=False, description="是否拒绝")

class ChatCompletionResponse(BaseModel):
    """聊天补全响应"""
    id: str = Field(default_factory=lambda: f"cmpl-{uuid4().hex[:24]}", description="完成ID")
    object: str = Field(default="text_completion", description="对象类型")
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()), description="创建时间戳")
    choices: list[Choice] = Field(..., description="结果选择列表")


# ========== 辅助函数 ==========
def build_chat_response(
    intent_domain: str,
    original_query: str,
    rewritten_query: Optional[str] = None,
    reject: bool = False
) -> ChatCompletionResponse:
    """
    构建聊天补全响应
    
    Args:
        intent_domain: 意图领域
        original_query: 原始查询
        rewritten_query: 改写后的查询
        reject: 是否拒绝
        
    Returns:
        ChatCompletionResponse: 格式化的响应对象
    """
    return ChatCompletionResponse(
        choices=[
            Choice(
                rewritten_query=rewritten_query,
                intent=IntentInfo(
                    domain=intent_domain,
                    query=original_query
                ),
                reject=reject
            )
        ]
    )

INTENT_TYPE_TO_DOMAIN = {
    "传统垂域": "TRADITIONAL_CAR_DOMAIN",
    "用车助手": "CAR_TIPS_DOMAIN",
    "出行助手": "TRAVEL_ASSIST_DOMAIN",
    "搜索助手": "INFO_SEARCH_DOMAIN",
    "趣味助手": "GENERAL_CHAT_DOMAIN",
    "闲聊百科": "GENERAL_KNOWLEDGE_QA"
}

# 全局实例，避免重复创建
intent_classifier_instance = IntentClassifier()
intent_classifier_car_b_instance = IntentClassifierCarB()
query_rewriter_instance = QueryRewrite()

@router.get("/")
async def health():
    return "health check success"

@router.post("/intent_cls")
async def intent_cls(request: IntentClsRequest):
    result = await intent_classifier_instance.run(query=request.input, history=request.history, output_structure=False)
    return result.domain

@router.post("/rewrite")
async def rewrite(request: RewriteRequest):
    result = await query_rewriter_instance.run(query=request.input, history=request.history, output_structure=False)
    return result

@router.post("/chat/intent/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: Request):
    # 验证请求头
    auth_error = verify_authorization(request)
    if auth_error:
        logger.error(f"Authorization failed: {auth_error}")
        return auth_error

    # 解析请求体
    request_body = await request.json()
    messages = request_body.get("messages", {})
    message = Message(**messages)
    logger.info(f"Message: {message}")

    history = message.history
    # 将history转成字符串 格式：用户：问题，助手：回答，用换行符分隔
    if history:
        history_str = "\n".join([f"用户：{h.q}\n助手: {h.a}" for h in history])
        # 将 History 对象转换为字典，以便 volcengine_api 能够正确解析
        history_dict_list = [{"q": h.q, "a": h.a} for h in history]
    else:
        history_str = ""
        history_dict_list = None

    input = message.query

    # TODO 目前是CAR_A的代码，后续需要支持CAR_B（CAR_A是五分类，CAR_B是二分类：传统垂域和百科闲聊）
    # 创建三个并行任务
    if message.car_type == "CAR_A":
        intent_task = asyncio.create_task(
            intent_classifier_instance.run(query=input, history=history_dict_list, output_structure=False)
        )
    else:
        intent_task = asyncio.create_task(
            intent_classifier_car_b_instance.run(query=input, history=history_dict_list, output_structure=False)
        )
    rewrite_task = asyncio.create_task(
        query_rewriter_instance.run(query=input, history=history_str, output_structure=False)
    )
    volcengine_task = asyncio.create_task(
        volcengine_api.volcengine_intent(input, history_dict_list)
    )
    
    tasks = {intent_task, rewrite_task, volcengine_task}
    intent_result = None
    rewrite_result = None
    volcengine_result = None
    
    try:
        # 使用超时等待所有任务
        timeout_time = 2.0
        start_time = asyncio.get_event_loop().time()
        
        while tasks:
            remaining_time = timeout_time - (asyncio.get_event_loop().time() - start_time)
            if remaining_time <= 0:
                raise asyncio.TimeoutError()
            
            # 等待任何一个任务完成
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED, timeout=remaining_time)
            
            if not done:
                raise asyncio.TimeoutError()
            
            # 处理已完成的任务
            for task in done:
                tasks.remove(task)
                
                if task == volcengine_task:
                    volcengine_result = await task
                    logger.info(f"volcengine_result: {volcengine_result}")
                    # 条件1: volcengine_intent 返回 operation_manual
                    if volcengine_result.intent_type == "operation_manual":
                        logger.info("volcengine_intent returned operation_manual, cancelling other tasks")
                        # 取消其他任务
                        for t in pending:
                            t.cancel()
                        
                        # 直接返回结果
                        response = build_chat_response(
                            intent_domain=INTENT_TYPE_TO_DOMAIN.get(Domain.VEHICLE, "GENERAL_CHAT_DOMAIN") if message.car_type == "CAR_A" else INTENT_TYPE_TO_DOMAIN.get(Domain.KNOWLEDGE, "GENERAL_KNOWLEDGE_QA"),
                            original_query=input,
                            reject=False
                        )
                        logger.info(f"Response: {response}")
                        return response
                
                elif task == intent_task:
                    intent_result = await task
                    logger.info(f"intent_result: {intent_result.domain}, decision_path: {intent_result.decision_path}, category: {intent_result.category}, reason: {intent_result.reason}")
                    # 条件2: intent_classifier 返回传统垂域且 decision_path 是 BY_RAG_TRADITIONAL
                    if intent_result.domain == Domain.TRADITIONAL and intent_result.decision_path == DecisionPath.BY_RAG_TRADITIONAL:
                        logger.info("intent_classifier returned TRADITIONAL with BY_RAG_TRADITIONAL, cancelling other tasks")
                        # 取消其他任务
                        for t in pending:
                            t.cancel()
                        
                        # 直接返回结果
                        response = build_chat_response(
                            intent_domain=INTENT_TYPE_TO_DOMAIN.get(intent_result.domain, "GENERAL_CHAT_DOMAIN") if message.car_type == "CAR_A" else INTENT_TYPE_TO_DOMAIN.get(intent_result.domain, "GENERAL_KNOWLEDGE_QA"),
                            original_query=input,
                            # rewritten_query=rewrite_result,
                            reject=False
                        )
                        logger.info(f"Response: {response}")
                        return response
                
                elif task == rewrite_task:
                    rewrite_result = await task
        
        # 所有任务都完成了，但没有满足提前返回的条件
        # 使用原有逻辑处理结果
        logger.info(f"All tasks completed normally")
        print(f"volcengine_result:{volcengine_result}")
        if volcengine_result.intent_type == "operation_manual":
            intent_result.domain = Domain.VEHICLE

        response = build_chat_response(
            intent_domain=INTENT_TYPE_TO_DOMAIN.get(intent_result.domain, "GENERAL_CHAT_DOMAIN") if message.car_type == "CAR_A" else INTENT_TYPE_TO_DOMAIN.get(intent_result.domain, "GENERAL_KNOWLEDGE_QA"),
            original_query=input,
            rewritten_query=rewrite_result,
            reject=False
        )
        logger.info(f"Response: {response}")
        return response
        
    except asyncio.TimeoutError as e:
        # 取消所有未完成的任务
        for task in tasks:
            task.cancel()
        logger.error(f"Request timeout, query: {input}, {e}")
        return build_chat_response(
            intent_domain="GENERAL_CHAT_DOMAIN" if message.car_type == "CAR_A" else "GENERAL_KNOWLEDGE_QA",
            original_query=input,
            reject=False
        )

@router.get("/test_nacos_config")
async def test_nacos_config():
    return AppConfig.AK