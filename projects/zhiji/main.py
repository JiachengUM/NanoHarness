from __future__ import annotations

from typing import Any, List, Optional
import uuid
import logging
import os
import json
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

from fastapi import FastAPI
from pydantic import BaseModel, Field

from projects.zhiji.core import IntentClassifier
from projects.zhiji.common.engine_api import CarInfo, HistoryItem, close_volcengine_session
from projects.zhiji.domain.complex import complex_navigation

# 配置日志
def setup_logging():
    """初始化日志配置"""
    logger = logging.getLogger("zhiji_api")
    logger.setLevel(logging.INFO)
    
    # 清除已有 handlers
    logger.handlers.clear()
    
    # 日志文件路径
    # Docker 环境使用 /var/logs，本地开发使用项目目录下的 logs
    app_name = os.getenv("APP_NAME", "zhiji-intent-api")
    
    # 先尝试使用 Docker 环境的日志目录
    docker_log_dir = f"/var/logs/{app_name}"
    try:
        os.makedirs(docker_log_dir, exist_ok=True)
        log_dir = docker_log_dir
    except (PermissionError, OSError):
        # 没有写权限，使用本地开发环境的日志目录
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        log_dir = os.path.join(project_root, "logs", app_name)
        os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, "api.log")
    
    # 文件日志处理器（按天轮转，保留7天）
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        fmt='[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(name)s] [%(lineno)d]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # 控制台日志处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(file_formatter)
    logger.addHandler(console_handler)
    
    return logger

# 初始化日志
api_logger = setup_logging()

app = FastAPI(title="Intent Recognition API")
classifier = IntentClassifier()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    await close_volcengine_session()

# 复杂意图类别名称集合
COMPLEX_CATEGORY_NAMES = {complex_navigation.name}


class QueryInput(BaseModel):
    query: str = Field(..., description="用户输入的query")
    chat_id: str = Field(..., description="聊天会话ID")
    history: List[HistoryItem] = Field(default_factory=list, description="历史对话")
    car_info: Optional[CarInfo] = Field(default=None, description="车辆信息")
    vehicle_id: Optional[str] = Field(default=None, description="设备唯一ID")
    vehicle_name: Optional[str] = Field(default=None, description="车辆市售名称")
    longitude: Optional[float] = Field(default=None, description="经度, GCJ02火星坐标系")
    latitude: Optional[float] = Field(default=None, description="纬度, GCJ02火星坐标系")
    function_call_version: Optional[str] = Field(default=None, description="函数调用版本")

class ResponseData(BaseModel):
    message: Optional[str] = None
    domain: Optional[str] = None
    intent_type: Optional[str] = None
    byte_intent_type: Optional[str] = None
    input: Optional[str] = None
    slot_data: Optional[str] = None
    origin_intent_type: Optional[str] = None
    next_process: Optional[str] = None
    question_id: Optional[str] = None
    reject: bool = False
    debug_info: dict = Field(default_factory=dict)
    isComplexIntent: bool = False
    llm_raw_result: Optional[str] = Field(default=None, description="LLM原始分类结果，用于调试")
    prompt_result: Optional[str] = Field(default=None, description="最终使用的分类结果，用于调试")


class APIResponse(BaseModel):
    data: ResponseData
    errno: int = 0
    msg: str = "success"


@app.post("/intent", response_model=APIResponse)
async def intent_recognition(payload: QueryInput) -> APIResponse:
    """意图识别接口，记录请求和响应日志"""
    start_time = time.time()
    
    # 记录请求日志（只记录 query 和 history）
    request_log = {
        "timestamp": datetime.now().isoformat(),
        "chat_id": payload.chat_id,
        "query": payload.query,
        "history": [{"q": h.q, "a": h.a} for h in payload.history] if payload.history else [],
    }
    api_logger.info(f"[REQUEST] {json.dumps(request_log, ensure_ascii=False)}")
    
    # 处理请求
    classification = await classifier.run(
        query=payload.query,
        history=payload.history if payload.history else None,
        car_info=payload.car_info.model_dump(exclude_none=True) if payload.car_info else None,
        longitude=payload.longitude,
        latitude=payload.latitude,
        vehicle_id=payload.vehicle_id,
        vehicle_name=payload.vehicle_name,
        function_call_version=payload.function_call_version,
    )

    api_result = classification.api_result
    debug_info = (
        api_result.debug_info.model_dump(exclude_none=True)
        if api_result.debug_info
        else {}
    )
    
    # 从 prompt_result 判断是否为复杂意图
    is_complex_intent = (
        classification.prompt_result in COMPLEX_CATEGORY_NAMES
        if classification.prompt_result
        else False
    )

    if api_result.reject or api_result.intent is None:
        data = ResponseData(
            reject=True,
            debug_info=debug_info,
            isComplexIntent=is_complex_intent,
            byte_intent_type=None,
            llm_raw_result=classification.llm_raw_result,
            prompt_result=classification.prompt_result,
        )
        response = APIResponse(data=data)
    else:
        intent = api_result.intent
        question_id = api_result.question_id or str(uuid.uuid4())
        
        byte_intent_type = api_result.byte_intent_type or ""

        data = ResponseData(
            message=intent.message or "",
            domain=intent.domain or "",
            intent_type=intent.intent_type or "",
            byte_intent_type=byte_intent_type,
            input=intent.input or payload.query,
            slot_data=intent.slot_data or "",
            origin_intent_type=intent.origin_intent_type or intent.intent_type or "",
            next_process=intent.next_process or "",
            question_id=question_id,
            reject=False,
            debug_info=debug_info,
            isComplexIntent=is_complex_intent,
            llm_raw_result=classification.llm_raw_result,
            prompt_result=classification.prompt_result,
        )
        response = APIResponse(data=data)
    
    # 计算处理时间
    process_time = time.time() - start_time
    
    # 记录响应日志
    response_log = {
        "timestamp": datetime.now().isoformat(),
        "chat_id": payload.chat_id,
        "query": payload.query,
        "status_code": 200,
        "process_time_ms": round(process_time * 1000, 2),
        "reject": response.data.reject,
        "domain": response.data.domain,
        "intent_type": response.data.intent_type,
        "byte_intent_type": response.data.byte_intent_type,
        "is_complex_intent": response.data.isComplexIntent,
        "question_id": response.data.question_id,
        "llm_raw_result": response.data.llm_raw_result,
        "prompt_result": response.data.prompt_result,
    }
    api_logger.info(f"[RESPONSE] {json.dumps(response_log, ensure_ascii=False)}")
    
    return response
