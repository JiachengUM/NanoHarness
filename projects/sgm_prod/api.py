import logging
import os
import json
import time
import uuid
import asyncio
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import Body, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from projects.sgm_prod.core import AgentDoStreamRequest as CoreAgentDoStreamRequest
from projects.sgm_prod.core import StreamChunk as CoreStreamChunk
from projects.sgm_prod.classification import arbitrate_simple_complex_decision
from projects.sgm_prod.classification.assets import UnknownRouterProjectError
from projects.sgm_prod.classification.normalize import normalize_query

# 与火山 TLS 采集路径 /var/logs/sgm_api/*.log 对齐
LOG_DIR = "/var/logs/sgm_api"
LOG_FILE = os.path.join(LOG_DIR, "sgm_api.log")


class VolcTlsLineFormatter(logging.Formatter):
    """
    行格式与火山「单行完整正则」采集一致，例如：
    ^\\[(?<timestamp>...)\\] \\[(?<level>\\w+)\\] \\[(?<module>[^\\]]+)\\] \\[(?<sub_module>[^\\]]+)\\]
    \\[(?<line>\\d+)\\] \\[(?<trace_id>[0-9a-f]{32})\\]:\\s*(?<message>[\\s\\S]*)$
    """

    def format(self, record: logging.LogRecord) -> str:
        local = time.localtime(record.created)
        ts = time.strftime("%Y-%m-%d %H:%M:%S", local) + f",{int(record.msecs):03d}"
        trace_raw = getattr(record, "trace_id", None)
        if trace_raw is None:
            trace_s = "0" * 32
        else:
            trace_s = str(trace_raw).lower()
            if len(trace_s) != 32 or any(c not in "0123456789abcdef" for c in trace_s):
                trace_s = "0" * 32
        return (
            f"[{ts}] [{record.levelname}] [{record.name}] "
            f"[{record.funcName}] [{record.lineno}] [{trace_s}]: {record.getMessage()}"
        )


def _setup_logging() -> None:
    """配置日志"""
    # 尝试创建日志目录；失败时降级为仅控制台日志，不中断服务启动。
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass
    logger = logging.getLogger("sgm_api")
    # DEBUG：本 logger 的 debug/info 都会输出；异常仍用 logger.exception 带完整栈。
    logger.setLevel(logging.DEBUG)
    # 避免在热重载或重复导入时反复添加 handler，导致日志重复输出。
    if not logger.handlers:
        fmt = VolcTlsLineFormatter()
        # 文件日志使用滚动策略：单文件 10MB，最多保留 5 个备份。
        try:
            fh = RotatingFileHandler(LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass
        # 无论文件日志是否成功，都保留控制台日志，便于本地/容器排障。
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)


_setup_logging()
logger = logging.getLogger("sgm_api")

app = FastAPI(
    title="SGM API",
    description="SGM复杂推理服务",
    version="1.0.0",
)
# 全局 manager 负责本地会话锁；
# 真正的对话状态持久化在 Redis。
_manager: Any | None = None


def _get_manager() -> Any:
    global _manager
    if _manager is None:
        from projects.sgm_prod.session import AgentManager

        _manager = AgentManager()
    return _manager


@app.post("/v1/sgm/stream")
async def sgm_stream(request: CoreAgentDoStreamRequest):
    """SGM Agent 流式接口，直接输出"""
    # question_id 主要用于日志与结束包标识；调用方未传时做一次兜底补全。
    if not request.question_id:
        request.question_id = request.chat_id or uuid.uuid4().hex

    logger.info(
        "sgm_stream chat_id=%s question_id=%s query=%s",
        request.chat_id,
        request.question_id,
        request.query,
        extra={"trace_id": uuid.uuid4().hex},
    )

    # 同一个 chat_id 仍然串行执行，但 agent 状态不再保存在本地内存。
    manager = _get_manager()
    entry = await manager.get_or_create(request.chat_id)

    async def stream():
        agent = None
        try:
            # 同一会话内的请求必须串行执行；
            # 否则两个并发请求会读写同一份 Redis 状态，导致上下文错乱。
            async with entry.lock:
                agent = await manager.load_agent(request.chat_id)
                async for chunk in agent.astream_chunks(request):
                    yield chunk.model_dump_json(exclude_none=True) + "\n"
        except Exception as e:
            logger.exception("SGMAgent stream error: %s", e)
            # 兜底返回一个 rc=2 的错误结束包，避免客户端一直等待流结束。
            yield CoreStreamChunk(
                error_code=1,
                rc=2,
                debug_info={"error": str(e)},
                log_id=request.question_id,
                intent_type=request.intent_type,
            ).model_dump_json(exclude_none=True) + "\n"
        finally:
            if agent is not None:
                await manager.save_agent(request.chat_id, agent)

    return StreamingResponse(stream(), media_type="text/event-stream")


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
    content: str | None = Field(default=None)
    ttsText: str | None = Field(default=None)
    observation: Optional[Any] = Field(default=None)


class ProcessorResponse(BaseModel):
    payload: Payload
    type: str = Field(default="")
    requestId: str


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


def _domain_for_function(function_code: str) -> str:
    if function_code in NAVIGATION_DOMAIN_FUNCTIONS:
        return "navigation"
    if function_code in MEDIA_DOMAIN_FUNCTIONS:
        return "media"
    if function_code in CALL_DOMAIN_FUNCTIONS:
        return "call"
    if function_code in APP_DOMAIN_FUNCTIONS:
        return "app"
    return "vehicle_control"


def _instructions_from_observation(observation: str) -> list[Instruction]:
    obs = json.loads(observation)
    instructions = []
    for function_item in obs.get("functions", []):
        function_code = function_item["function_code"]
        raw_params = function_item.get("params", [])
        cleaned_params = []
        for param_dict in raw_params:
            if isinstance(param_dict, dict):
                cleaned_params.append({k: v for k, v in param_dict.items() if v != "空"})
            else:
                cleaned_params.append(param_dict)

        instructions.append(
            Instruction(
                function_code=function_code,
                params=cleaned_params,
                domain=_domain_for_function(function_code),
            )
        )
    return instructions


def _sse_chunk(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"



_GLOBAL_CHAT_ID = "aipfox_global"
_global_agent: Any | None = None
_global_agent_lock = asyncio.Lock()


def _get_global_agent() -> Any:
    global _global_agent
    if _global_agent is None:
        from projects.sgm_prod.v1 import create_agent as create_v1_agent

        _global_agent = create_v1_agent(chat_id=_GLOBAL_CHAT_ID)
    return _global_agent


@app.post("/v1/sgm_processor")
async def sgm_processor(request: SGMProcessorRequest = Body(..., description="SGM处理器请求数据")):
    """直接调用本地 SGMAgent，将 StreamChunk 映射到 ProcessorResponse 格式输出。"""
    from projects.sgm_prod.v1 import AgentDoStreamRequest as V1AgentDoStreamRequest
    from projects.sgm_prod.v1 import HistoryItem as V1HistoryItem

    question_id = request.question_id or _GLOBAL_CHAT_ID
    history_v1 = [V1HistoryItem(q=h.q, a=h.a) for h in request.history]
    agent_req = V1AgentDoStreamRequest(
        chat_id=_GLOBAL_CHAT_ID,
        question_id=question_id,
        query=request.query,
        history=history_v1,
        intent_type=request.intent_type or "复杂推理",
        car_info=request.car_info or {},
    )
    logger.info(
        "sgm_processor request_id=%s question_id=%s query=%s",
        request.request_id,
        question_id,
        request.query,
        extra={"trace_id": uuid.uuid4().hex},
    )

    async def stream():
        try:
            async with _global_agent_lock:
                agent = _get_global_agent()
                async for chunk in agent.astream_chunks(agent_req):
                    if chunk.rc == 0:
                        continue

                    if chunk.tts_text and chunk.rc == 1:
                        payload = Payload(
                            isEnd=False,
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

                    if chunk.plugin_name == "poi_result" and chunk.observation:
                        try:
                            obs_data = json.loads(chunk.observation)
                        except (json.JSONDecodeError, TypeError):
                            obs_data = chunk.observation
                        payload = Payload(
                            isEnd=False,
                            query=request.query,
                            observation=obs_data,
                            reject=False,
                            content=chunk.content,
                            ttsText=chunk.tts_text,
                        )
                        yield _sse_chunk(ProcessorResponse(
                            payload=payload,
                            type="poi_result",
                            requestId=request.request_id,
                        ).model_dump(exclude_none=True))

                    if chunk.plugin_name == "function_call" and chunk.observation:
                        try:
                            instructions = _instructions_from_observation(chunk.observation)
                            payload = Payload(
                                isEnd=False,
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

    return StreamingResponse(stream(), media_type="text/event-stream")


# 简单/复杂意图仲裁接口
class SimpleComplexArbitrationRequest(BaseModel):
    query: str = Field(..., min_length=1, description="当前轮用户 query")
    chat_id: str = Field(..., min_length=1, description="会话ID")
    question_id: str = Field(..., min_length=1, description="本轮对话请求ID")
    project: str = Field(default="default", description="业务项目配置名")
    history: List[QAPair] = Field(default_factory=list, description="用户历史，按时间正序")
    debug: bool = Field(default=False, description="是否返回调试 trace")
    use_exact_match: bool = Field(default=True, description="是否启用 data/simple.csv 与 data/complex.csv 的 exact 命中；默认开启")
    simple: List[str] | None = Field(default=None, description="自定义 simple 精准匹配集，替代默认配置；不传时使用默认配置")
    complex: List[str] | None = Field(default=None, description="自定义 complex 精准匹配集，替代默认配置；不传时使用默认配置")
    prompt: str | None = Field(default=None, description="自定义 LLM fallback 提示词，替代默认配置；不传时使用默认配置")


class SimpleComplexArbitrationResponse(BaseModel):
    errno: int = Field(default=0)
    msg: str = Field(default="success")
    data: str
    source: str
    trace: Dict[str, Any] | None = None


@app.post("/v1/simple_complex_arbitration", response_model=SimpleComplexArbitrationResponse)
async def simple_complex_arbitration(request: SimpleComplexArbitrationRequest):
    """简单/复杂意图仲裁接口。"""
    logger.info(
        "simple_complex_arbitration chat_id=%s question_id=%s project=%s query=%s",
        request.chat_id,
        request.question_id,
        request.project,
        request.query,
        extra={"trace_id": uuid.uuid4().hex},
    )
    history = [item.model_dump() for item in request.history]
    simple_fs = frozenset(normalize_query(q) for q in request.simple) if request.simple else None
    complex_fs = frozenset(normalize_query(q) for q in request.complex) if request.complex else None
    try:
        decision = await arbitrate_simple_complex_decision(
            request.query,
            project=request.project,
            history=history,
            use_exact_match=request.use_exact_match,
            simple_queries=simple_fs,
            complex_queries=complex_fs,
            llm_prompt=request.prompt,
        )
    except UnknownRouterProjectError as exc:
        logger.warning(
            "simple_complex_arbitration unknown project chat_id=%s question_id=%s project=%s",
            request.chat_id,
            request.question_id,
            request.project,
        )
        return SimpleComplexArbitrationResponse(
            errno=400,
            msg=str(exc),
            data="",
            source="config_error",
            trace=None,
        )
    logger.info(
        "simple_complex_arbitration result chat_id=%s question_id=%s project=%s label=%s source=%s history=%s",
        request.chat_id,
        request.question_id,
        request.project,
        decision.label,
        decision.source,
        history,
    )
    return SimpleComplexArbitrationResponse(
        data=decision.label,
        source=decision.source,
        trace=decision.trace.model_dump() if request.debug else None,
    )


@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
