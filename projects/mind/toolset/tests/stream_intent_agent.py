"""基于 mlx-community/Qwen3-0.6B-4bit 的流式车载意图识别。

输入：ASROutput(text, language)
输出：IntentResult(intent: bool, text: str, language: str)
调度：anyio.create_memory_object_stream 串接 ASR → 意图 → 下游消费
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------- 常量 ----------

MODEL_ID: str = "mlx-community/Qwen3-0.6B-4bit"

INTENT_CATEGORIES: tuple[str, ...] = (
    # 出行/导航
    "导航", "找地点", "查路况", "查限行", "查天气", "查油价", "查停车场", "查充电桩",
    # 控车
    "控空调", "控座椅", "控车窗", "控灯光", "控驾驶模式", "控后视镜", "控雨刷",
    # 媒体
    "播放音乐", "切歌", "调音量", "电台", "有声书", "视频",
    # 通讯
    "打电话", "发消息", "查联系人",
    # 提醒/日程
    "设提醒", "日程", "闹钟",
    # 问答/闲聊
    "知识问答", "闲聊", "情感倾诉", "开玩笑", "吐槽", "驾驶陪伴",
    # 推荐
    "美食推荐", "购物推荐", "景点推荐", "酒店推荐",
    # 车辆
    "车辆故障", "保养", "油量", "胎压", "充电",
)

INTENT_SYSTEM_PROMPT: str = (
    "车载场景意图分类器。"
    "判 true：用户的话包含车内场景的具体诉求（控车、播放/搜索音乐、导航、找地点、问知识、打电话、设提醒、查天气/油价/限行等），且能映射到下方工具或具体业务需求。"
    "判 false：仅含语气词、填充词、思考停顿（嗯、啊、对呀、好、那个、哎、想一下等），无具体诉求；"
    "对系统本身的元指令（调提示、改prompt、演示意图、测试系统、调速度等），判 false；"
    "或为乱码、随机字符、非人类语言。"
    "可用工具（用户的话能对应到这些工具的，应判 true）：\n"
    "- CarControl: 车控指令执行。输出：执行状态\n"
    "- AudioPlay: 媒体控制播放器，播放内容：歌曲名称（song_name）/歌单名称（dissname）/专辑名称（album_name）等音频内容。输出：执行状态\n"
    "- MemoryRecall: 记忆召回工具：根据步骤目标从后台记忆数据中召回用户偏好。输出：记忆实体\n"
    "- Navigate: 导航工具：路线规划与导航执行（目的地、出发地、出发时间、路线偏好）。输出：导航执行状态\n"
    "- SongSearch: 单曲搜索工具。输出：单曲结果列表\n"
    "- PlaylistSearch: 歌单搜索工具。输出：歌单结果列表\n"
    "- AlbumSearch: 专辑搜索工具。输出：专辑结果列表\n"
    "- POISearch: poi周边检索、poi关键词搜索。输出：POI名称、离中心点距离(米)、POI类型、详细地址、所属省份、所属城市、所属区县、"
    "所属商圈、评分、人均消费、今日营业时间、每周营业时间、联系电话、"
    "POI别名、特色内容、停车场类型（地下、地面、路边）、楼层、室内地图标志\n"
    "- WebSearch: 网页搜索输出，支持多种搜索类型，可作为general search工具，当用户查询意图/信息无法通过其它search类工具获取时启用。输出：通用搜索结果列表\n"
    "只输出 true 或 false。"
)


# ---------- I/O 模型 ----------

class ASROutput(BaseModel):
    """ASR worker 输出，意图流水线的入参。"""

    text: str = Field(..., description="ASR 转写文本")
    language: str = Field(default="unknown", description="ASR 文本语言")


class IntentResult(BaseModel):
    """意图识别终态。"""

    intent: bool = Field(..., description="是否与车载场景需求相关")
    text: str = Field(..., description="原始 ASR 文本")
    language: str = Field(default="unknown", description="ASR 文本语言（由流水线透传）")


class IntentStreamChunk(BaseModel):
    """流式生成 chunk。"""

    delta: str = Field(default="", description="本次新增 token 文本")
    finished: bool = Field(default=False, description="是否生成结束")
    result: IntentResult | None = Field(default=None, description="finished=True 时填入")


class IntentInput(BaseModel):
    """意图识别输入。业务方法挂在本 BaseModel 上：Input → Stream[Chunk] → Result。"""

    text: str = Field(..., description="ASR 文本")

    async def astream(self, model: "IntentModel") -> AsyncIterator[IntentStreamChunk]:
        """流式分类 self.text。每产出一个 token yield 一个 unfinished chunk，结束时 yield finished + result。"""
        from mlx_lm import stream_generate  # type: ignore[import-not-found]

        prompt = _build_prompt(self.text, model.tokenizer)
        accumulated = ""

        for token in stream_generate(
            model.model,
            model.tokenizer,
            prompt,
            max_tokens=4,
        ):
            # mlx_lm.stream_generate 在不同版本上 yield str 或 GenerationResponse，统一取 .text。
            text = getattr(token, "text", None) or str(token)
            accumulated += text
            yield IntentStreamChunk(delta=text, finished=False)

        intent = _parse_intent(accumulated)
        yield IntentStreamChunk(
            delta="",
            finished=True,
            result=IntentResult(intent=intent, text=self.text),
        )

    async def aclassify(self, model: "IntentModel") -> IntentResult:
        """非阻塞单次分类，把同步 classify 丢到线程池。"""
        return await anyio.to_thread.run_sync(self.classify, model)

    def classify(self, model: "IntentModel") -> IntentResult:
        """同步单次分类。供 anyio.to_thread.run_sync 调用，不阻塞事件循环。"""
        from mlx_lm import stream_generate  # type: ignore[import-not-found]

        prompt = _build_prompt(self.text, model.tokenizer)
        accumulated = ""
        for token in stream_generate(
            model.model,
            model.tokenizer,
            prompt,
            max_tokens=4,
        ):
            text = getattr(token, "text", None) or str(token)
            accumulated += text
        intent = _parse_intent(accumulated)
        return IntentResult(intent=intent, text=self.text)


# ---------- 模型加载（基础设施，非业务逻辑） ----------

class IntentModel:
    """mlx-community/Qwen3-0.6B-4bit 的单例状态持有者。懒加载一次。"""

    def __init__(self, model_id: str = MODEL_ID) -> None:
        self._model_id = model_id
        self._model = None
        self._tokenizer = None

    def ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from mlx_lm import load  # type: ignore[import-not-found]

        resolved_id = resolve_local_path(self._model_id)
        logger.info("loading intent model: %s", resolved_id)
        # mlx_lm.load 在不同版本上返回 2-tuple 或 3-tuple（多模态模型多 processor），按长度解构。
        loaded = load(resolved_id)
        if len(loaded) == 3:
            self._model, self._tokenizer, _ = loaded
        else:
            self._model, self._tokenizer = loaded
        logger.info("intent model loaded")

    @property
    def model(self):
        self.ensure_loaded()
        return self._model

    @property
    def tokenizer(self):
        self.ensure_loaded()
        return self._tokenizer


_intent_model = IntentModel()


def get_intent_model() -> IntentModel:
    """获取全局单例意图模型。"""
    return _intent_model


# ---------- 纯工具函数 ----------

def resolve_local_path(repo_id: str) -> str:
    """优先返回 HF 缓存中的本地路径；缓存 miss 时返回原 repo_id 触发下载。

    mlx_lm.load / mlx_audio.*.utils.load_model 都接受 repo_id 与本地路径，
    本地命中省去远端下载 + 校验，启动从几十秒降到秒级。
    """
    try:
        from huggingface_hub import snapshot_download  # type: ignore[import-not-found]
        local_path = snapshot_download(repo_id, local_files_only=True)
        logger.info("model local cache hit: %s -> %s", repo_id, local_path)
        return local_path
    except Exception as e:
        logger.info("model not in local cache, will download: %s (%s)", repo_id, e.__class__.__name__)
        return repo_id


def _build_prompt(text: str, tokenizer) -> str:
    """组装 chat 模板 prompt。tokenizer 无 chat template 时降级为简单拼接。"""
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    apply = getattr(tokenizer, "apply_chat_template", None)
    if apply is None:
        return f"{INTENT_SYSTEM_PROMPT}\n\n{text}\n答案："
    return apply(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )


def _parse_intent(raw: str) -> bool:
    """从生成文本中解析二分类结果。保守处理：未明确 false。"""
    normalized = raw.strip().lower()
    true_markers = ("true", "yes", "是", "相关")
    false_markers = ("false", "no", "否", "不相关")
    if any(marker in normalized for marker in true_markers):
        return True
    if any(marker in normalized for marker in false_markers):
        return False
    return False


# ---------- 编排（anyio 流水线） ----------

async def run_intent_pipeline(
    input_recv: MemoryObjectReceiveStream[str],
    output_send: MemoryObjectSendStream[IntentResult],
    model: IntentModel | None = None,
) -> None:
    """从 input_recv 消费 ASR 文本，输出 IntentResult 到 output_send。

    作为 ASR 阶段的下游消费方使用，由调用方在 task group 中启动。
    空文本直接跳过。模型异常由本函数显式 log + 继续，避免断流。
    """
    intent_model = model or get_intent_model()
    async with input_recv:
        async for text in input_recv:
            if not text.strip():
                continue
            try:
                result = await IntentInput(text=text).aclassify(intent_model)
            except Exception:
                logger.exception("intent classify failed for %r", text)
                continue
            await output_send.send(result)


def create_intent_pipeline(
    buffer_size: int = 100,
) -> tuple[
    MemoryObjectSendStream[str],
    MemoryObjectReceiveStream[IntentResult],
    Callable[[], Awaitable[None]],
]:
    """建 ASR 文本入队流 + 意图结果出队流 + worker bridge 协程的便捷工厂。

    返回 (asr_text_send, intent_result_recv, _bridge)。
    调用方在 task group 内 `tg.start_soon(_bridge)` 即可挂上意图 worker。
    """
    asr_send, asr_recv = anyio.create_memory_object_stream[str](buffer_size)
    intent_send, intent_recv = anyio.create_memory_object_stream[IntentResult](buffer_size)

    async def _bridge() -> None:
        await run_intent_pipeline(asr_recv, intent_send)

    return asr_send, intent_recv, _bridge


__all__ = [
    "MODEL_ID",
    "INTENT_CATEGORIES",
    "ASROutput",
    "IntentResult",
    "IntentStreamChunk",
    "IntentInput",
    "IntentModel",
    "get_intent_model",
    "run_intent_pipeline",
    "create_intent_pipeline",
]
