"""
记忆库 API 服务
提供将对话添加到记忆库的 FastAPI 接口
"""
import asyncio
import json
import logging
import os
import time
import uuid
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Literal, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from projects.mind.complex_reasoning.utils.http_client import HttpClient
from projects.mind.demo.sgm_processor.agent import AgentDoStreamRequest, SGMAgent

# from projects.mind.mem.volc_api import add_to_memory, SearchMemory, search_memory
# from projects.mind.mem.volc_api.retrieval import MemoryResponse
# from projects.mind.intent.task_data.message import Message
# from projects.mind.mem.volc_api.memory import (
#     BatchDeleteEvent,
#     BatchDeleteEventFilter,
#     BatchDeleteProfile,
#     BatchDeleteProfileFilter,
#     DeleteMemoryResponse as VolcDeleteMemoryResponse,
#     batch_delete_event,
#     batch_delete_profile,
# )


# 日志目录与文件名
LOG_DIR = "/var/logs/memory-api"
LOG_FILE = os.path.join(LOG_DIR, "memory_api.log")

def _setup_logging() -> None:
    """配置日志：输出到 /var/logs/memory-api/*.log，若目录不存在则尝试创建。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass  # 无权限时仅用 root logger，不写文件
    logger = logging.getLogger("memory_api")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        try:
            fh = RotatingFileHandler(
                LOG_FILE,
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return None

_setup_logging()
logger = logging.getLogger("memory_api")

app = FastAPI(
    title="记忆库 API",
    description="提供将对话添加到记忆库的服务",
    version="1.0.0",
)

# 当前 session_id；进程内有效，重启或多 worker 时清空（单用户场景）
_current_session_id: str | None = None


# ── SGM Processor 模型 ──────────────────────────────────────────────────────

class QAPair(BaseModel):
    q: str = Field(..., description="用户问题")
    a: str = Field(..., description="助手回答")


class SGMProcessorRequest(BaseModel):
    query: str = Field(..., description="查询内容")
    request_id: str = Field(..., description="请求ID")
    history: List[QAPair] = Field(default_factory=list)
    chat_id: Optional[str] = Field(None)
    question_id: Optional[str] = Field(None)
    intent_type: Optional[str] = Field("复杂推理")
    car_info: Optional[Dict[str, Any]] = Field(default_factory=dict)


class Instruction(BaseModel):
    function_code: str
    params: List[Dict[str, Any]] = Field(default_factory=list)
    domain: Optional[str] = Field(None)


class Payload(BaseModel):
    isEnd: bool = Field(default=False)
    instructions: List[Instruction] = Field(default_factory=list)
    query: str = Field(default="")
    reject: bool = Field(default=False)
    content: str = Field(default=None)
    ttsText: str = Field(default=None)
    observation: Optional[Any] = Field(default=None)


class ProcessorResponse(BaseModel):
    payload: Payload
    type: str = Field(default="")
    requestId: str


def _sse_chunk(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# # ── Memory 模型 ──────────────────────────────────────────────────────────────

# # 请求/响应模型
# class ConversationMessage(BaseModel):
#     """对话消息模型（简化版，用于 API 请求）"""
#     role: Literal["user", "assistant", "system"] = Field(..., description="发言人角色")
#     content: str = Field(..., description="消息内容（文本）")


# class AddMemoryRequest(BaseModel):
#     """添加记忆请求模型"""
#     conversation: list[ConversationMessage] = Field(..., description="对话列表，包含多轮对话消息")
#     user_id: str = Field(..., description="用户ID，用于标识对话所属用户")
#     start_new: bool = Field(default=False, description="是否开启新会话：True 时用新时间戳生成新 session_id 并沿用；False 时沿用当前 session_id",)


# class AddMemoryResponse(BaseModel):
#     """添加记忆响应模型"""
#     success: bool = Field(..., description="是否成功")
#     message: str = Field(..., description="响应消息")
#     session_id: str | None = Field(default=None, description="会话ID")
#     timestamp: int = Field(..., description="时间戳（毫秒）")


# class DeleteMemoryRequest(BaseModel):
#     """按 user_id 删除该用户全部 event 与 profile 的请求"""
#     user_id: str = Field(..., description="要删除记忆的用户ID")
#     collection_name: str = Field(default="SGM", description="记忆库名称，默认 SGM")


# class DeleteByUserResponse(BaseModel):
#     """按 user_id 删除的响应（汇总 event + profile 两次删除结果）"""
#     success: bool = Field(..., description="是否全部删除成功（event 与 profile 均 code==0）")
#     message: str = Field(..., description="汇总说明")
#     event: VolcDeleteMemoryResponse = Field(..., description="事件记忆删除结果")
#     profile: VolcDeleteMemoryResponse = Field(..., description="画像记忆删除结果")


# # API 端点
# @app.get("/")
# async def root():
#     """根路径，重定向到文档"""
#     return {"message": "记忆库 API 服务", "docs": "/docs"}


# @app.get("/health")
# async def health():
#     """健康检查"""
#     return {"status": "ok", "service": "memory-api"}


# @app.post("/memory/add", response_model=AddMemoryResponse)
# async def add_memory(request: AddMemoryRequest) -> AddMemoryResponse:
#     """
#     添加对话到记忆库
    
#     将多轮对话添加到指定的记忆库中，系统会自动提取事件和画像信息。
    
#     **参数说明**：
#     - `conversation`: 对话列表，按时间顺序排列，包含用户和助手的多轮对话
#     - `user_id`: 用户唯一标识，用于区分不同用户的记忆
#     - `start_new`: 为 True 时开启新会话（新 session_id）；为 False 时沿用当前 session_id。首次调用建议传 True。
    
#     **默认配置**：
#     - `collection_name`: 默认为 "SGM"
#     - `session_id`: 自动生成，格式为 "session" + 时间戳（毫秒）
#     - `default_assistant_id`: 默认为 "小途助手"
    
#     **返回说明**：
#     - `success`: 是否成功添加
#     - `message`: 响应消息
#     - `session_id`: 会话ID（自动生成）
#     - `timestamp`: 时间戳
    
#     **示例请求**：
#     ```json
#     {
#         "conversation": [
#             {"role": "user", "content": "我最近很喜欢听周杰伦的歌。"},
#             {"role": "assistant", "content": "周杰伦的歌确实很经典，有没有特别喜欢的专辑？"},
#             {"role": "user", "content": "我最喜欢他的《叶惠美》和《七里香》。"}
#         ],
#         "user_id": "user_001"
#     }
#     ```
#     """
#     global _current_session_id
#     try:
#         # 将 API 请求的消息格式转换为内部 Message 格式
#         messages: list[Message] = []
#         for msg in request.conversation:
#             messages.append(
#                 Message(
#                     role=msg.role,
#                     content=msg.content,
#                 )
#             )
        
#         # 决定 session_id：start_new=True 或尚无 session 时生成新的，否则沿用
#         current_timestamp = int(time.time() * 1000)
#         if request.start_new or _current_session_id is None:
#             session_id = f"session_{current_timestamp}"
#             _current_session_id = session_id
#         else:
#             session_id = _current_session_id
#             current_timestamp = int(time.time() * 1000)
        
#         # 调用 add_to_memory 函数
#         add_to_memory(
#             messages,  # 位置参数
#             collection_name="SGM",  # 默认记忆库名称
#             user_id=request.user_id,
#             default_assistant_id="小途助手",  # 默认助手ID
#             session_id=session_id,  # 自动生成的会话ID
#         )
        
#         response = AddMemoryResponse(
#             success=True,
#             message="对话已成功添加到记忆库",
#             session_id=session_id,
#             timestamp=current_timestamp,
#         )
#         logger.info(
#             "memory/add success | user_id=%s start_new=%s session_id=%s timestamp=%s msg_count=%s",
#             request.user_id,
#             request.start_new,
#             session_id,
#             current_timestamp,
#             len(request.conversation),
#         )
#         return response
    
#     except Exception as e:
#         logger.exception(
#             "memory/add failed | user_id=%s start_new=%s error=%s",
#             request.user_id,
#             request.start_new,
#             str(e),
#         )
#         raise HTTPException(status_code=500, detail=f"添加记忆失败: {str(e)}")


# @app.post("/memory/retrieve", response_model=MemoryResponse)
# async def retrieve_memory(request: SearchMemory) -> MemoryResponse:
#     """
#     记忆检索
    
#     请求体为 JSON，字段说明：
#     - **collection_name**（可选）：记忆库名称，默认 "SGM"
#     - **project_name**（可选）：项目名，默认 "default"
#     - **query**（可选）：搜索语句，用于语义匹配；不传则按 filter 条件按时间返回
#     - **limit**（可选）：返回条数，默认 10，范围 [1, 5000]
#     - **filter**（必填）：过滤条件对象
#       - **memory_type**（必填）：记忆类型，字符串或字符串数组，如 `["profile_v1", "steward_note_book"]`
#       - **user_id**（可选）：用户 ID，字符串或字符串数组
    
#     示例请求体：
#     ```json
#     {
#       "collection_name": "SGM",
#       "query": "回家",
#       "limit": 10,
#       "filter": {
#         "memory_type": ["profile_v1", "profile_location_v1", "steward_note_book"],
#         "user_id": "user_01"
#       }
#     }
#     ```
    
#     返回 retrieval 中的 MemoryResponse（code、message、data.result_list 等）。
#     """
#     try:
#         return await asyncio.to_thread(search_memory, request)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"记忆检索失败: {str(e)}")


# @app.post("/memory/delete", response_model=DeleteByUserResponse)
# async def delete_by_user(request: DeleteMemoryRequest) -> DeleteByUserResponse:
#     """
#     按 user_id 删除该用户在该记忆库中的全部事件记忆与画像记忆。

#     - **user_id**（必填）：要清空记忆的用户 ID
#     - **collection_name**（可选）：记忆库名称，默认 "SGM"

#     示例请求体：
#     ```json
#     { "user_id": "user_01" }
#     ```
#     """
#     try:
#         event_req = BatchDeleteEvent(
#             collection_name=request.collection_name,
#             filter=BatchDeleteEventFilter(user_id=request.user_id),
#         )
#         profile_req = BatchDeleteProfile(
#             collection_name=request.collection_name,
#             filter=BatchDeleteProfileFilter(user_id=request.user_id),
#         )
#         event_rsp = await asyncio.to_thread(batch_delete_event, event_req)
#         profile_rsp = await asyncio.to_thread(batch_delete_profile, profile_req)
#         success = event_rsp.code == 0 and profile_rsp.code == 0
#         message = (
#             "event 与 profile 均已删除"
#             if success
#             else f"event: {event_rsp.message}; profile: {profile_rsp.message}"
#         )
#         return DeleteByUserResponse(
#             success=success,
#             message=message,
#             event=event_rsp,
#             profile=profile_rsp,
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"删除记忆失败: {str(e)}")

       
_GLOBAL_CHAT_ID = "aipfox_global"
_global_agent = SGMAgent.create(chat_id=_GLOBAL_CHAT_ID)


@app.post("/v1/sgm_processor")
async def sgm_processor(request: SGMProcessorRequest = Body(..., description="SGM处理器请求数据")):
    """直接调用本地 SGMAgent，将 StreamChunk 映射到 ProcessorResponse 格式输出。"""
    agent_req = AgentDoStreamRequest(
        chat_id=_GLOBAL_CHAT_ID,
        question_id=request.question_id or _GLOBAL_CHAT_ID,
        query=request.query,
        intent_type=request.intent_type or "复杂推理",
        car_info=request.car_info or {},
    )
    agent = _global_agent

    async def stream():
        try:
            async for chunk in agent.astream(agent_req):
                # rc=0 初始化包，直接透传
                if chunk.rc == 0:
                    #yield _sse_chunk(chunk.model_dump(exclude_none=True))
                    continue

                # 模型文字流：组装 complex_result 发给下游
                if chunk.tts_text and chunk.rc == 1:
                    payload = Payload(
                        isEnd=(chunk.rc == 2),
                        instructions=[],
                        query=request.query,
                        reject=False,
                        content=chunk.content,
                        ttsText=chunk.tts_text,
                    )
                    yield _sse_chunk(ProcessorResponse(
                        payload=payload,
                        type="complex_result",
                        requestId=request.request_id,
                    ).model_dump(exclude_none=True))
                if chunk.plugin_name == "poi_result":
                    try:
                        obs_data = json.loads(chunk.observation) if isinstance(chunk.observation,
                                                                               str) else chunk.observation
                    except (json.JSONDecodeError, TypeError):
                        obs_data = chunk.observation
                    payload = Payload(
                        isEnd=(chunk.rc == 2),
                        query=request.query,
                        observation=obs_data,
                        reject=False,
                        content=chunk.content,
                        ttsText=chunk.tts_text,
                    )
                    print(payload)

                    yield _sse_chunk(ProcessorResponse(
                        payload=payload,
                        type="poi_result",
                        requestId=request.request_id,
                    ).model_dump(exclude_none=True))

                if chunk.plugin_name == "function_call" and chunk.observation:
                    try:
                        obs = json.loads(chunk.observation)
                
                        # 需要设置 domain="app" 的 function_code 列表
                        APP_DOMAIN_FUNCTIONS = {
                            "指定应用开关",
                            "指定应用主页面返回",
                            "指定应用移动",
                            "指定应用全屏",
                            "影视剧搭子开关",
                            "浏览器搜索",
                            "浏览器搜索取消",
                            "指定模式开关",
                        }
                
                        # 需要设置 domain="call" 的 function_code 列表
                        CALL_DOMAIN_FUNCTIONS = {
                            "拨号页面开关",
                            "拨号控制",
                            "联系人增删改",
                            "同步通讯录",
                            "同步通话记录",
                            "通讯页面开关",
                            "发送短信",
                            "拨打电话",
                            "紧急呼救",
                            "号码查询",
                        }
                
                        # 需要设置 domain="media" 的 function_code 列表
                        MEDIA_DOMAIN_FUNCTIONS = {
                            "音乐歌曲播放",
                            "音乐歌单播放",
                            "有声音频播放",
                            "网络电台播放",
                            "本地电台播放",
                            "收音机频率扫描",
                            "影视剧视频播放",
                            "新闻播放",
                            "媒体列表播放",
                            "影音推荐",
                            "音乐歌曲搜索",
                            "有声音频搜索",
                            "影视剧视频搜索",
                            "音乐预约",
                            "歌词开关",
                            "悬浮歌词开关",
                            "悬浮歌词移动",
                            "视频画质设置",
                            "音质设置",
                            "播放速度设置",
                            "播放切换",
                            "播放进度快进退",
                            "播放状态设置",
                            "播放模式设置",
                            "视频屏幕切换",
                            "音乐歌单开关",
                            "播放列表开关",
                            "媒体列表开关",
                            "K 歌应用开关",
                            "K 歌模式切换",
                            "K 歌歌曲点播",
                            "K 歌歌曲预约",
                            "媒体收藏",
                            "媒体点赞",
                            "评论开关",
                            "博主关注",
                        }
                
                        # 需要设置 domain="navigation" 的 function_code 列表
                        NAVIGATION_DOMAIN_FUNCTIONS = {
                            "导航操作",
                            "单目的地导航",
                            "多目的地导航",
                            "一般地点检索",
                            "地点切换",
                            "途经点搜索",
                            "途经点新增",
                            "途经点删除",
                            "途经点查看",
                            "导航路线切换",
                            "导航避开限行开关",
                            "自定义路线调整",
                            "路线刷新",
                            "目的地切换",
                            "导航路线设置页面",
                            "导航状态主辅路切换",
                            "导航状态桥上下切换",
                            "全览模式开关",
                            "概览模式切换",
                            "跟随模式开关",
                            "巡航模式开关",
                            "AR 模式开关",
                            "位置复位",
                            "路况显示开关",
                            "卫星图显示开关",
                            "地点详情显示开关",
                            "车道级导航开关",
                            "轻导航开关",
                            "导航电量接续算路开关",
                            "地图移动",
                            "地图放大缩小",
                            "导航自动比例尺开关",
                            "地图视角切换",
                            "导航播报模式调节",
                            "导航路况播报开关",
                            "导航提醒播报开关",
                            "导航电子眼播报开关",
                            "导航红绿灯播报开关",
                            "导航限行提醒开关",
                            "播报模式设置页面",
                            "常用地址设置",
                            "常用地址删除",
                            "地址收藏",
                            "收藏地址删除",
                            "收藏地址查看",
                            "导航搜索记录操作",
                            "地址设置页面",
                            "路线偏好设置",
                            "导航设置页面",
                            "队伍创建",
                            "队伍加入",
                            "队伍退出",
                            "组队出行设置页面",
                            "导航路线查询",
                            "导航距离查询",
                            "导航时长查询",
                            "导航目的地查询",
                            "导航到达时间查询",
                            "路线路况查询",
                            "限速查询",
                            "限行查询",
                        }
                
                        # 需要设置 domain="vehicle" 的 function_code 列表（车辆控制相关）
                        VEHICLE_DOMAIN_FUNCTIONS = {
                            "空调开关", "空调温度调节", "空调风量调节", "空调自动风量模式调节", "空调风向调节",
                            "空调出风口模式设置", "空调同步开关", "空调内外循环控制", "空调空气净化开关",
                            "空调空气净化档位调节", "空调除雾除霜开关", "空调舒适性关窗提醒开关", "空调负离子开关",
                            "空调监测开关", "空调空气质量 AQS 灵敏度设置", "空调设置页面", "香氛开关", "香氛浓度调节",
                            "香氛设置页面", "座椅前后调节", "座椅高度调节", "座椅腰托开关", "座椅腰托高度调节",
                            "座椅腰托前后调节", "座椅肩部前后调节", "座椅腿托开关", "座椅腿托前后调节",
                            "座椅腿托高度调节", "座椅腿托加热开关", "座椅腿托加热档位调节", "座椅脚托开关",
                            "座椅脚托高度调节", "座椅脚托加热开关", "座椅脚托加热档位调节", "座椅侧翼开关",
                            "座椅侧翼高度调节", "座椅坐垫角度调节", "座椅坐垫高度调节", "座椅坐垫前后调节",
                            "座椅靠背角度调节", "座椅折叠展开", "座椅方便进出开关", "零重力座椅开关",
                            "座椅一键躺平开关", "座椅一键舒适开关", "座椅一键复位开关", "座椅记忆开关",
                            "座椅记忆调节", "座椅记忆保存", "座椅头枕高度调节", "座椅头枕前后调节",
                            "座椅按摩开关", "座椅按摩力度调节", "座椅按摩模式调节", "座椅加热通风开关",
                            "座椅加热通风档位调节", "座椅设置页面", "车窗开关", "车窗亮度自动调节开关",
                            "锁车自动关窗开关", "车窗设置页面", "车窗隐私模式开关", "天窗开关", "天窗起翘开关",
                            "天窗亮度调节", "天窗自动亮度开关", "锁车天窗自动遮光开关", "天窗设置页面",
                            "遮阳帘开关", "外后视镜折叠开关", "外后视镜自动折叠开关", "外后视镜位置调节",
                            "后视镜亮度模式设置", "后视镜亮度调节", "外后视镜自动下翻开关", "外后视镜加热开关",
                            "外后视镜防炫目开关", "后视镜设置页面", "后视镜临时视野开关", "车门开关", "车门设置页面",
                            "车窗上锁开关", "靠近解锁开门开关", "两步解锁开关", "离车落锁开关", "车门锁开关",
                            "童锁开关", "寻车模式开关", "寻车模式设置", "驻车解锁开关", "车锁设置页面",
                            "氛围灯开关", "氛围灯亮度调节", "氛围灯颜色调节", "阅读灯开关", "阅读灯亮度调节",
                            "化妆镜灯开关", "自动礼貌灯开关", "脚底灯开关", "车内灯开关", "车外灯开关",
                            "驻车灯开关", "全气候灯开关", "延时照明开关", "延时照明时长设置", "档位照明灯开关",
                            "弯道照明灯开关", "迎宾灯开关", "迎宾灯时长设置", "迎宾灯样式设置", "迎宾光毯开关",
                            "迎宾光毯时长设置", "迎宾光毯主题设置", "接近照明灯开关", "远近灯光开关",
                            "远近灯光高度调节", "远近灯光颜色调节", "远近灯光自动切换开关", "随动转向大灯开关",
                            "示廓灯开关", "雾灯开关", "转向灯开关", "危险警示灯开关", "车外灯光秀开关",
                            "智能激光大灯开关", "尾灯开关", "尾门灯开关", "倒车灯开关", "日间行车灯开关",
                            "制动灯开关", "logo 灯自动开关", "表情灯开关", "场景灯开关", "车灯设置页面",
                            "喇叭控制", "方向盘助力调节", "方向盘与驾驶模式联动开关", "方向盘位置调节",
                            "方向盘加热开关", "方向盘加热调节", "方向盘自定义按键设置", "方向盘设置页面",
                            "档位切换", "自动换档开关", "电子手刹开关", "制动踏板脚感设置", "驾驶模式设置",
                            "动力性能设置", "尾翼开关", "尾翼高度调节", "电子稳定系统开关", "电子稳定系统调节",
                            "牵引力控制系统开关", "牵引力控制系统调节", "轻松通过开关", "悬架方便上下车开关",
                            "悬架轻松载物开关", "陡坡缓降开关", "单踏板模式开关", "自动驻车开关",
                            "舒适停车开关", "悬架阻尼设置", "悬架高度设置", "悬架维修模式开关",
                            "滑行能量回收开关", "滑行能量回收调节", "自动启停开关", "安全气囊开关",
                            "安全带开关", "后排安全带未系提醒开关", "行车密码开关", "一键弹射开关",
                            "疲劳提醒开关", "驾驶员监测系统灵敏度设置", "驾驶习惯设置", "驾驶设置页面",
                            "辅助驾驶开关", "定速巡航开关", "自适应巡航开关", "智能巡航开关",
                            "高速领航辅助开关", "城市领航辅助开关", "巡航车距调节", "巡航设置页面",
                            "雷达开关", "倒车雷达开关", "前方安全辅助开关", "前向碰撞预警开关",
                            "前向碰撞制动开关", "前方横向来车预警开关", "前方横向来车制动开关",
                            "后方安全辅助开关", "后向碰撞预警开关", "后方横向来车预警开关",
                            "后方横向来车制动开关", "碰撞预警灵敏度调节", "碰撞预警设置页面",
                            "开门预警开关", "车辆换道", "转弯方式切换", "窄道通行辅助开关", "倒车侧向辅助开关",
                            "车道偏离辅助开关", "车道偏离预警开关", "车道偏离预警灵敏度调节",
                            "车道偏离预警方式设置", "车道保持辅助开关", "车道控制辅助开关",
                            "应急车道占用提醒开关", "智慧躲闪辅助开关", "变道舒适性模式调节",
                            "盲区监测预警开关", "盲区监测预警方式设置", "变道危险预警开关",
                            "变道危险预警方式设置", "车道辅助设置页面", "车速控制", "限速识别提醒开关",
                            "限速偏差设置", "限速识别提醒方式设置", "智能限速调节开关", "紧急转向辅助开关",
                            "紧急转向辅助方式设置", "转向灯控制变道开关", "转向图像辅助开关", "爆胎辅助开关",
                            "交通灯识别开关", "驾驶员状态监测开关", "生命探测功能开关", "雨天影像辅助模式开关",
                            "智驾低功耗模式开关", "语音控制辅助驾驶开关", "自动驾驶开关",
                            "自动驾驶防误接管开关", "自动驾驶新手引导开关", "领航辅助驾驶风格设置",
                            "开放道路自学习开关", "辅助驾驶提示方式开关", "自动避障辅助开关",
                            "语音控制自动驾驶开关", "自动驾驶风格设置", "自动驾驶设置页面", "自动泊车开关",
                            "泊入泊出", "泊入泊出位置调节", "泊入车位选择", "靠边停车", "靠边操作", "原路倒车",
                            "倒车操作", "记忆泊车开关", "记忆泊车常用停车场主动学习开关",
                            "记忆泊车主动推荐开关", "记忆泊车地图主动分享开关", "抬头显示开关",
                            "抬头显示亮度调节", "抬头显示高度调节", "抬头显示方向调节", "抬头显示角度调节",
                            "抬头显示位置记忆调节", "抬头显示模式设定", "抬头显示信息设置",
                            "抬头显示智驾场景重构开关", "抬头显示智驾视角显示设置", "抬头显示报警提示开关",
                            "抬头显示设置页面", "抬头显示投屏开关", "仪表视图显示设置", "哨兵模式开关",
                            "哨兵模式长期有效开关", "哨兵模式循环录像开关", "哨兵模式后视镜折叠开关",
                            "哨兵模式停车拍照开关", "哨兵模式照片视频操作", "哨兵模式设置页面",
                            "行车记录仪开关", "行车记录仪录音开关", "行车记录仪拍照开关",
                            "行车记录仪录像控制", "行车记录照片视频操作", "事故处理一键上报",
                            "前方违章车辆一键上报", "行车记录仪设置页面", "车内外摄像头开关",
                            "车内外录像静音开关", "车内外摄像头功能调节", "车内外延时摄影开关",
                            "延时摄影速率调节", "延时摄影时长调节", "OMS 摄像头开关", "OMS 摄像查看开关",
                            "车内外摄像头照片视频操作", "手机遗忘提醒开关", "人脸识别开关", "全景影像开关",
                            "全景影像视图调节", "透明车模开关", "车模透明度调节", "全景影像设置页面",
                            "充电开关", "充电电流设定", "充电限额设定", "预约充电开关", "预约充电时间设置",
                            "预约充电频次设置", "波谷充电开关", "波谷充电时间设置", "插枪维温开关",
                            "充电状态指示灯开关", "充电状态音效设置", "充电插座照明灯开关", "智能保电模式开关",
                            "智能保电 SOC 设置", "充电口盖板开关", "充电端口锁开关", "充电设置页面",
                            "一键上下电", "能量管理设置页面", "加油口盖板开关", "燃油补电开关",
                            "手机无线充电开关", "放电开关", "放电类型设置", "放电量设置",
                            "放电综合里程保护开关", "放电综合里程保护设置", "放电设置页面", "电池预热开关",
                            "电池预热等级设置", "预约出行开关", "预约出行时间设置", "预约空调开关",
                            "预约出行页面", "化妆镜开关", "储物箱开关", "前备箱开关", "后备箱开关调节",
                            "后备箱设置页面", "手套箱开关", "手套箱 PIN 码开关", "扶手箱开关", "杯托架开关",
                            "雨刮开关", "雨刮速度调节", "雨刮灵敏度调节", "雨刮按次刮刷", "玻璃喷水清洗",
                            "雨刮设置页面", "雨刮维修模式开关", "雨刮关联倒车开关", "车载冰箱电源开关",
                            "车载冰箱开关", "车载冰箱温度调节", "车载冰箱设置页面开关", "车载冰箱模式设置",
                            "车载冰箱儿童锁开关", "UI 换肤", "屏保开关", "整车背光调节", "屏幕亮度控制",
                            "屏幕自动亮度开关", "昼夜模式切换", "壁纸设置", "系统壁纸扩展", "壁纸动感场景开关",
                            "分屏开关", "屏幕锁开关", "屏幕清洁模式开关", "侧边栏开关", "车机屏幕开关",
                            "屏幕角度调节", "车机快速启动模式开关", "屏幕显示设置页面",
                            "续航里程显示模式调节", "续航显示设置页面", "屏幕勿扰模式开关", "屏幕镜像开关",
                            "车速音量补偿开关", "车速音量补偿模式调节", "倒车降低音量开关",
                            "开门降低音量开关", "音量调节", "静音开关", "音量平衡设置", "触摸屏声音设置",
                            "导航混音调节", "低速行人提示音开关", "低速行人提示音调节", "车门提示音调节",
                            "迎宾欢送音开关", "车内扬声器升降开关", "车外音乐播放开关", "车内音调调节",
                            "车内音效设置", "车外交互音效设置", "头枕音响模式调节", "环绕音设置",
                            "环绕音强度设置", "无麦 k 歌音效设置", "均衡器音效设置", "最佳听音位设置",
                            "模拟声浪音效设置", "车外喇叭开关", "声音设置页面", "音效设置页面",
                            "行车娱乐限制开关", "时间格式设置", "时间格式自动开关", "蓝牙开关",
                            "蓝牙名称设置", "蓝牙电话开关", "蓝牙耳机开关", "蓝牙连接断开", "蓝牙删除",
                            "始终播放手机音频开关", "蓝牙可被发现开关", "蓝牙设置页面", "热点开关",
                            "热点连接断开", "热点编辑", "热点频段调节", "热点设置页面", "移动网络开关",
                            "移动网络设置页面", "网络重启", "WIFI 开关", "WIFI 连接断开", "WIFI 添加",
                            "WIFI 网络设置页面", "连接设置页面", "系统语音语言设置", "语音唤醒开关",
                            "语音免唤醒开关", "语音 oneshot 开关", "多音区模式切换", "音区锁定开关",
                            "语音延时聆听设置", "自定义唤醒词设置", "所见即可说开关", "车外语音开关",
                            "语音播报速度设置", "播报风格调整", "发音人音色设置", "发音人语种设置",
                            "问候语设置", "语音授权开关", "语音设置页面", "智能通话免打扰开关",
                            "遗留物品检测开关", "一键隐私开关", "手势识别开关", "车机开关", "消息通知开关",
                            "账号登录", "账号切换", "账号退出", "系统升级", "系统恢复出厂设置",
                            "驾驶室过热保护开关", "系统设置页面开关", "车辆设置页面开关", "推荐中心页面开关",
                            "个人中心页面开关", "豆包设置页面开关", "特殊设置页面开关", "返回设置",
                            "退出语音", "页面关闭", "页面切换", "长期记忆操作",
                        }
                
                        instructions = []
                        for f in obs.get("functions", []):
                            function_code = f["function_code"]
                            # 根据 function_code 设置对应的 domain
                            if function_code in VEHICLE_DOMAIN_FUNCTIONS:
                                domain = "vehicle_control"
                            elif function_code in NAVIGATION_DOMAIN_FUNCTIONS:
                                domain = "navigation"
                            elif function_code in MEDIA_DOMAIN_FUNCTIONS:
                                domain = "media"
                            elif function_code in CALL_DOMAIN_FUNCTIONS:
                                domain = "call"
                            elif function_code in APP_DOMAIN_FUNCTIONS:
                                domain = "app"
                            else:
                                domain = "vehicle_control"
                
                            # 处理 params：过滤掉值为"空"的字段
                            raw_params = f.get("params", [])
                            cleaned_params = []
                            for param_dict in raw_params:
                                if isinstance(param_dict, dict):
                                    # 过滤掉值为"空"的键值对
                                    filtered_param = {
                                        k: v for k, v in param_dict.items()
                                        if v != "空"
                                    }
                                    cleaned_params.append(filtered_param)
                                else:
                                    # 如果不是 dict，保持原样
                                    cleaned_params.append(param_dict)
                
                            instructions.append(
                                Instruction(
                                    function_code=function_code,
                                    params=cleaned_params,
                                    domain=domain
                                )
                            )
                
                        payload = Payload(
                            isEnd=(chunk.rc == 2),
                            instructions=instructions,
                            query=request.query,
                            reject=False,
                        )
                        yield _sse_chunk(ProcessorResponse(
                            payload=payload,
                            type="function_call",
                            requestId=request.request_id,
                        ).model_dump(exclude_none=True))
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.error("解析 observation 失败：%s, observation: %s", e, chunk.observation)

                # 终止包
                if chunk.rc == 2:
                    payload = Payload(
                        isEnd=True,
                        query=request.query,
                        reject=False,
                        content=chunk.content,
                        ttsText=chunk.tts_text,
                    )
                    yield _sse_chunk(ProcessorResponse(
                        payload=payload,
                        type="complex_result",
                        requestId=request.request_id,
                    ).model_dump())
                    return

        except Exception as e:
            logger.exception("SGMAgent stream error: %s", e)
            yield _sse_chunk({"rc": 2, "error_code": 500, "stage": "done"})
        finally:
            await HttpClient.close_for_current_loop()

    return StreamingResponse(stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
