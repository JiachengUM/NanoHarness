"""Voice Test 浏览器协议 schema：共用枚举、WS 入站/出站、HTTP body。"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.test_backend.enums.task import AgentType
from projects.voice_test.config.adapter_config import TtsVoice


# ---------- 共用枚举 ----------


class BatchPace(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class JudgeStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_RUN = "not_run"


class VoiceTestTarget(StrEnum):
    """WS agent_type 取值；须与前端 / AgentType 字符串一致。"""

    VOICE = "voice"
    AGENT_V1 = AgentType.AGENT_V1.value  # "AgentV1"
    OLD_COMPLEX = "OldComplex"


class WsPhase(StrEnum):
    """WebSocket PhaseEvent 下发给前端的相位（不含内部 closed）。"""

    IDLE = "idle"
    SPEAKING = "speaking"
    LISTENING = "listening"


# ---------- WebSocket 入站共用运行参数 ----------


_REPEAT_N_MAX = 50


class VoiceTestWsRunParams(BaseModel):
    """WebSocket start / start_batch 共用的运行参数。"""

    model_config = ConfigDict(extra="ignore")

    enable_judge: bool = True
    # 单 case / 批跑每条 case 重复次数；默认 1=旧行为。不改库表，批跑仅多写 item。
    repeat_n: int = Field(default=1, ge=1, le=_REPEAT_N_MAX)
    adapter_config: dict[str, object] | None = None
    agent_type: Annotated[
        VoiceTestTarget,
        Field(
            default=VoiceTestTarget.VOICE,
            description="见 GET /voice_test/agent_options",
        ),
    ]

    @field_validator("agent_type", mode="before")
    @classmethod
    def validate_agent_type(cls, raw: object) -> VoiceTestTarget:
        # 懒加载，避免 browser_schemas ↔ catalog ↔ adapters 循环导入
        from projects.voice_test.adapter.browser_agent_catalog import parse_voice_test_target

        return parse_voice_test_target(raw)


# ---------- WebSocket 入站 ----------


class WsStartMessage(VoiceTestWsRunParams):
    """单条 case：type=start。"""

    type: Literal["start"] = "start"
    case: TestCase


class WsStartBatchMessage(VoiceTestWsRunParams):
    """数据集批跑：type=start_batch。"""

    type: Literal["start_batch"] = "start_batch"
    dataset_id: str = Field(min_length=1)
    batch_pace: BatchPace = BatchPace.AUTO

    @field_validator("dataset_id")
    @classmethod
    def strip_dataset_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("dataset_id 不能为空")
        return stripped


class WsControlMessage(BaseModel):
    """无载荷控制命令（type 用 Literal，供 discriminator 分流）。"""

    model_config = ConfigDict(extra="ignore")

    type: Literal[
        "next_case",
        "skip_case",
        "stop",
        "playback_drained",
        "pause",
    ]


class WsResumeConfirmMessage(BaseModel):
    """续跑确认：前端选择 continue 续跑 PAUSED 任务。有载荷，没法放进 WsControlMessage，只能放在单独消息。"""

    type: Literal["resume_confirm"] = "resume_confirm"
    task_run_id: str = Field(min_length=1)
    action: Literal["continue"]


BrowserWsInboundMessage = Annotated[
    WsStartMessage | WsStartBatchMessage | WsControlMessage | WsResumeConfirmMessage,
    Field(discriminator="type"),
]

_INBOUND_ADAPTER = TypeAdapter(BrowserWsInboundMessage)


def parse_browser_ws_inbound(
    data: object,
) -> WsStartMessage | WsStartBatchMessage | WsControlMessage:
    return _INBOUND_ADAPTER.validate_python(data)


# ---------- WebSocket 出站（Adapter → 前端） ----------


class ReadyEvent(BaseModel):
    type: Literal["ready"] = "ready"
    input_sample_rate: int
    output_sample_rate: int
    output_format: str


class ReadyTextEvent(BaseModel):
    """文本模式就绪（无音频参数）。"""

    type: Literal["ready_text"] = "ready_text"


class PhaseEvent(BaseModel):
    type: Literal["phase"] = "phase"
    phase: WsPhase


class AwaitPlaybackDrainEvent(BaseModel):
    """S2S PCM 已全部下发，等待浏览器本地播放队列播完。"""

    type: Literal["await_playback_drain"] = "await_playback_drain"


class AsrDeltaEvent(BaseModel):
    type: Literal["asr_delta"] = "asr_delta"
    text: str


class AsrFinalEvent(BaseModel):
    type: Literal["asr_final"] = "asr_final"
    text: str


class ListenTimeoutEvent(BaseModel):
    """等外部回复超时：替换前端「识别中…」占位。"""

    type: Literal["listen_timeout"] = "listen_timeout"
    message: str
    # 当前第几次尝试 / 上限（含首次；与框架 external_api_max_retries+1 对齐）
    attempt: int | None = None
    max_attempts: int | None = None


class UserQueryEvent(BaseModel):
    type: Literal["user_query"] = "user_query"
    text: str
    mode: str
    wake_up_word: str = ""
    session_id: str | None = None


class LogEvent(BaseModel):
    type: Literal["log"] = "log"
    message: str


class CountdownWaitEvent(BaseModel):
    """case 内等待（如记忆提取）：前端在对话区展示倒计时气泡。"""

    type: Literal["countdown_wait"] = "countdown_wait"
    label: str
    seconds: int


class ConfigReplyEvent(BaseModel):
    """告别语等场景：不收音，直接使用 adapter 配置中的脚本回复。"""

    type: Literal["config_reply"] = "config_reply"
    text: str


class DialogueHistoryEvent(BaseModel):
    type: Literal["dialogue_history"] = "dialogue_history"
    text: str


class JudgingEvent(BaseModel):
    type: Literal["judging"] = "judging"
    message: str


class JudgeResultEvent(BaseModel):
    type: Literal["judge_result"] = "judge_result"
    is_passed: bool
    reason: str


class JudgeSkippedEvent(BaseModel):
    """对话已完成，但调用方明确关闭了自动评测。"""

    type: Literal["judge_skipped"] = "judge_skipped"
    message: str = "对话完成，本次未启用自动评测"


class BatchStartedEvent(BaseModel):
    """服务端已固定本次批量运行的数据集快照。

    total = 用例数 × repeat_n（进度槽位数）。
    case_ids 仍为去重后的用例列表；前端按 repeat_n 展开时间线条目。
    """

    type: Literal["batch_started"] = "batch_started"
    dataset_id: str
    dataset_name: str
    total: int
    enable_judge: bool
    batch_pace: BatchPace = BatchPace.AUTO
    case_ids: list[str] = Field(default_factory=list)
    repeat_n: int = 1


class BatchCaseWaitingEvent(BaseModel):
    """手动批跑：当前 case 已就绪，等待前端确认后再执行。"""

    type: Literal["batch_case_waiting"] = "batch_case_waiting"
    index: int
    total: int
    case_id: str
    repeat_index: int | None = None
    repeat_n: int | None = None


class TaskRunCreatedEvent(BaseModel):
    """本次浏览器语音批量测试已绑定到 task_run，可在历史结果页查询。"""

    type: Literal["task_run_created"] = "task_run_created"
    task_id: str
    task_run_id: str


class BatchCaseStartedEvent(BaseModel):
    type: Literal["batch_case_started"] = "batch_case_started"
    index: int
    total: int
    case_id: str
    repeat_index: int | None = None
    repeat_n: int | None = None
    run_id: str | None = None  # case 执行级 id，用于在 llm.log 中 grep 全链路日志


class BatchCaseResultEvent(BaseModel):
    type: Literal["batch_case_result"] = "batch_case_result"
    index: int
    total: int
    case_id: str
    execution_success: bool
    execution_error: str | None = None
    judge_status: JudgeStatus
    is_passed: bool | None = None
    reason: str | None = None
    repeat_index: int | None = None
    repeat_n: int | None = None
    # 首轮响应耗时（ms）：None=超时/无ASR/文本链路
    first_response_ms: float | None = None
    task_run_item_id: str | None = None


class BatchDoneEvent(BaseModel):
    type: Literal["batch_done"] = "batch_done"
    total: int
    execution_success: int
    enable_judge: bool
    judged: int
    passed: int | None = None
    pass_rate: float | None = None
    repeat_n: int = 1
    # 首轮平均响应时间（ms）：None=无有效样本
    avg_first_response_ms: float | None = None
    first_response_sample_count: int | None = None


class BatchPausedEvent(BaseModel):
    """批量测试已暂停：当前 case 跑完后挂起，等待 resume。"""

    type: Literal["batch_paused"] = "batch_paused"
    completed: int
    total: int


class BatchResumedEvent(BaseModel):
    """批量测试已继续：从暂停处恢复执行。"""

    type: Literal["batch_resumed"] = "batch_resumed"
    completed: int = 0
    total: int = 0


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


BrowserJsonEvent = Annotated[
    ReadyEvent
    | ReadyTextEvent
    | PhaseEvent
    | AwaitPlaybackDrainEvent
    | AsrDeltaEvent
    | AsrFinalEvent
    | ListenTimeoutEvent
    | UserQueryEvent
    | LogEvent
    | CountdownWaitEvent
    | ConfigReplyEvent
    | DialogueHistoryEvent
    | JudgingEvent
    | JudgeResultEvent
    | JudgeSkippedEvent
    | BatchStartedEvent
    | BatchCaseWaitingEvent
    | TaskRunCreatedEvent
    | BatchCaseStartedEvent
    | BatchCaseResultEvent
    | BatchDoneEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]

# 出站队列：JSON 事件保持 BaseModel，PCM 仍用裸 bytes（高频路径）
OutMessage = BrowserJsonEvent | bytes


# ---------- HTTP ----------


class TtsSynthesizeRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: TtsVoice

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        content = value.strip()
        if not content:
            raise ValueError("text 不能为空")
        return content


class VoiceTestHealthData(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["voice_test"] = "voice_test"
    websocket_path: str = "/voice_test/session"
