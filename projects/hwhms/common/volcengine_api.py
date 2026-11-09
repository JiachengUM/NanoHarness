import json
import logging
import time
from typing import Dict, List, Optional

import aiohttp
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat import ChatCompletionSystemMessageParam
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel, Field
from volcengine.viking_knowledgebase import VikingKnowledgeBaseService

from nanoai.model.llm import RunResult
from projects.hwhms.common.config.config import AppConfig
from projects.hwhms.common.volcengine_utils import VolcengineUtils

logger = logging.getLogger(__name__)


DEFAULT_SYS_PROMPT = f"你是一个车联网领域意图分类的助手，请根据用户输入的内容，返回意图的类别。"

async def llm(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> RunResult[str]:
    """异步版本。"""

    model = model
    client = client

    messages = _compose_messages(input, messages_or_sys_prompt)
    response = await client.chat.completions.create(
        model=model, messages=messages, **kwargs
    )
    response_msg: ChatCompletionMessage = response.choices[0].message
    if response_msg.content is None:
        raise RuntimeError(f"got empty response.content")

    output = response_msg.content
    
    messages.append({
        "role": "assistant",
        "content": response_msg.content,
    })

    return RunResult(output=output, response=response_msg, messages=messages)

def _compose_messages(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
) -> list[ChatCompletionMessageParam]:
    """将输入和消息历史合并为OpenAI API的messages参数。"""

    assert isinstance(input, str), f"input must be str, but got {type(input)}"
    assert isinstance(messages_or_sys_prompt, (str, list)), f"messages_or_sys_prompt must be str or list, but got {type(messages_or_sys_prompt)}"
        

    if isinstance(messages_or_sys_prompt, str):
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam({"role": "system", "content": messages_or_sys_prompt})
        ]
    else:
        messages: list[ChatCompletionMessageParam] = messages_or_sys_prompt

    # 创建用户消息内容
    messages.append(ChatCompletionUserMessageParam(role="user", content=input))
    
    return messages

class ItemChunkField(BaseModel):
    """"""
    field_name: str
    field_value: Optional[str]

    def to_dict(self):
        """将对象转换为可序列化的字典"""
        return {
            "field_name": self.field_name,
            "field_value": self.field_value
        }

class KnowledgeItem(BaseModel):
    """知识库接口返回的单项"""
    id: str
    content: str
    score: float
    point_id: str
    chunk_type: str  # image
    chunk_source: str  # document
    chunk_id: int
    process_time: int
    doc_info: Dict
    recall_position: int
    update_time: int
    chunk_title: Optional[str] = None  # 设置默认值None
    chunk_attachment: Optional[List] = Field(default_factory=list)  # 默认为空列表
    table_chunk_fields: Optional[List[ItemChunkField]] = Field(default_factory=list)  # 默认为空列表
    from_recall_queue: Optional[str]
    original_coordinate: Optional[Dict] = Field(default=None, exclude=True)

    def get_image_url(self):
        if self.chunk_type == 'image' and self.chunk_attachment:
            return self.chunk_attachment[0].get('link', '')
        else:
            return ''

    def is_structured(self):
        """是否结构化数据"""
        if self.table_chunk_fields:
            return True
        else:
            return False

    def get_metadata_type(self) -> str:
        if self.table_chunk_fields:
            return self.table_chunk_fields[2].field_value
        else:
            return "0"

    def get_metadata_value(self, idx: int) -> str:
        if self.table_chunk_fields:
            return self.table_chunk_fields[idx].field_value
        else:
            return ""
        
    def to_dict(self):
        """将对象转换为可序列化的字典"""
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "table_chunk_fields": [field.to_dict() for field in self.table_chunk_fields],
        }

class KnowledgeData(BaseModel):
    """知识库接口返回的数据体"""
    rewrite_query: Optional[str]
    result_list: Optional[List[KnowledgeItem]]
    
_viking_knowledgebase_service = None

async def init_viking_knowledgebase_service(
    host: str = AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN,
    ak: str = AppConfig.RAG_AK,
    sk: str = AppConfig.RAG_SK,
) -> VikingKnowledgeBaseService:
    if _viking_knowledgebase_service:
        return _viking_knowledgebase_service
    viking_knowledgebase_service = VikingKnowledgeBaseService(host=host, scheme="https", connection_timeout=30, socket_timeout=30)
    viking_knowledgebase_service.set_ak(ak)
    viking_knowledgebase_service.set_sk(sk)
    return viking_knowledgebase_service

async def search_konwledge(
    query: str,
    host: str = AppConfig.RAG_KNOWLEDGE_BASE_DOMAIN,
    account_id: str = AppConfig.RAG_ACCOUNT_ID,
    ak: str = AppConfig.RAG_AK,
    sk: str = AppConfig.RAG_SK,
    limit=2,
    collection_name="HW_REWRITING",
    viking_knowledgebase_service: VikingKnowledgeBaseService = None
) -> Optional[List[KnowledgeItem]]:
    pre_processing = {
        "need_instruction": False, # 是否拼接 instruction 进行检索
        "return_token_usage": True, # 是否返回search流程中各阶段的token使用量
        "messages": [ # 多轮对话信息
            {"role": "system", "content": ""},
            {"role": "user"}
        ]
    }
    post_processing = {
        "get_attachment_link": False, # 是否获取切片中图片的临时下载链接
        "rerank_only_chunk": False, # 是否仅根据 chunk 内容计算重排分数（ chunk 内容 or chunk title + 内容）
        "rerank_switch": False #自动对结果做 rerank
    }
    viking_knowledgebase_service = viking_knowledgebase_service or await init_viking_knowledgebase_service(host=host, ak=ak, sk=sk)
    res = viking_knowledgebase_service.search_knowledge(collection_name=collection_name,query=query,
                                                            pre_processing=pre_processing, limit=limit, dense_weight=0.5,
                                                            post_processing=post_processing, project="default")
    print(res)
    knowledge_data = KnowledgeData.parse_raw(json.dumps(res))
    if knowledge_data:
        result_list = knowledge_data.result_list
        ## 取里面socre最高的两条记录，且score大于0.5的记录
        result_list = sorted(result_list, key=lambda x: x.score, reverse=True)
        result_list = [item for item in result_list if item.score > 0.4]
        result_list = result_list[:2]
        return result_list
    return None

class HistoryItem(BaseModel):
    """历史对话记录"""
    q: str = Field(..., description="用户query")
    a: str = Field(..., description="大模型或者插件的回答")

class CarInfo(BaseModel):
    """车辆信息"""
    # 基本信息
    vehicle_name: Optional[str] = Field(None, description="车辆市售名称")
    sound_zone: Optional[str] = Field(None, description="音区，即说话人当前位置")

    # 娱乐信息
    song: Optional[str] = Field(None, description="正在播放的歌名")
    singer: Optional[str] = Field(None, description="正在播放的音乐的歌手")
    video_name: Optional[str] = Field(None, description="视频名称（电影、电视剧、综艺等视频）")
    video_episodes: Optional[int] = Field(None, description="视频集数")
    audio_name: Optional[str] = Field(None, description="音频名称（音乐、相声、有声读物等音频）")
    audio_producer: Optional[str] = Field(None, description="音频制作人")

    # 位置信息
    current_location: Optional[str] = Field(None, description="用户当前位置")
    target_location: Optional[str] = Field(None, description="用户询问的地点，正式项目不支持")
    home_location: Optional[str] = Field(None, description="用户家的位置")
    company_location: Optional[str] = Field(None, description="用户公司的位置")

    # 导航信息
    nav_dest_name: Optional[str] = Field(None, description="导航目的地名字")
    nav_dest_address: Optional[str] = Field(None, description="导航目的地地址")
    nav_waypoint: Optional[str] = Field(None, description="导航途经点")
    nav_remain_distance: Optional[str] = Field(None, description="导航剩余距离")
    nav_remain_cost: Optional[str] = Field(None, description="导航剩余时长")
    nav_road_congestion: Optional[str] = Field(None, description="道路拥堵情况")

    # 车辆状态
    battery: Optional[int] = Field(None, ge=0, le=100, description="电量百分比")
    tts_language: Optional[str] = Field("mandarin", description="TTS当前播报语言")

    # 日程信息
    next_event_type: Optional[str] = Field(None, description="下一个日程类型")
    next_event_title: Optional[str] = Field(None, description="下一个日程标题")

    car_heading: Optional[int] = Field(None, ge=0, le=360, description="车头朝向，0-360，单位：度数")

class VolcRequestBodyPrepare(BaseModel):
    query: Optional[str] = Field(None, description="提问")
    car_type: Optional[str] = Field(
        None,
        description="车辆类型"
    )
    history: Optional[List[HistoryItem]] = Field(
        None,
        description="历史对话记录，q/a成对出现"
    )
    car_info: Optional[CarInfo] = Field(
        None,
        description="车辆相关信息"
    )
    function_call_version: Optional[str] = Field(
        None,
        description="Function_call版本号",
        examples=["v1.0", "v2.0", "latest"]
    )

    def to_dict(self) -> Dict:
        """返回包含所有非None字段的字典，字段名使用别名"""
        return self.dict(by_alias=True, exclude_none=True)

    @classmethod
    def build(cls, **extra_fields) -> 'VolcRequestBodyPrepare':
        base_data = {
            **extra_fields
        }
        result = cls(**base_data)
        return result

class VolcengineIntentResult(BaseModel):
    """意图类型"""
    intent_type: Optional[str] = Field(None, description="意图类型")
    input: Optional[str] = Field(None, description="输入信息")

## 获取意图类型
async def volcengine_intent(
    query: str,
    history: Optional[list[HistoryItem]] = None,
    **kwargs,
) -> VolcengineIntentResult:
    start_time = time.time()
    url = f"{AppConfig.VOLC_URL}/dpfm/v1/chat/intent"
    ak = AppConfig.AK
    sk = AppConfig.SK
    logger.info(f"火山引擎意图识别开始: {start_time}, url: {url}, ak: {ak}, sk: {sk}")
    body = VolcRequestBodyPrepare.build(query=query, history=history, **kwargs)
    querystr = VolcengineUtils.prepare_querystr()
    signature = VolcengineUtils.generate_signature(method="POST", querystr=querystr, body=json.dumps(body.to_dict() ) if body else None, sk=sk)
    headers = VolcengineUtils.prepare_headers_http(f"{ak}:{signature}")
    print(headers)
    print(querystr)
    
    # 🚀 性能优化：使用异步HTTP请求，避免阻塞事件循环
    # 将同步的 requests.post() 改为异步的 aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{url}?{querystr}",
            headers=headers,
            json=body.to_dict() if body else None,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            response_text = await response.text()
            print(response_text)
            response_data = await response.json()
            data = response_data.get('data', {})
    
    logger.info(f"火山引擎意图识别耗时: {time.time() - start_time:.2f}秒")
    return VolcengineIntentResult(
        intent_type=data.get('intent_type'),
        input=data.get('input')
    )
