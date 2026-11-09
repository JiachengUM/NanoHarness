from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
import traceback
from typing import Any, Literal

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import DataTable, Footer, Header, RichLog, Static
from rich.text import Text
from pydantic import BaseModel

from aicore.agents.experiments.memory import (
    MemoryAddCompletedEvent,
    MemoryAddFailedEvent,
    MemoryAddPendingEvent,
    MemoryAddProcessingEvent,
)
from aicore.events.agent import (
    AgentOutEvent,
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.events.react import (
    ReActErrorEvent,
    ReActFinishEvent,
    ReActStartEvent,
    ReActTextDeltaEvent,
    ReActTextDoneEvent,
    ReActTextStartEvent,
    TaskToolDoneEvent,
    ToolCallStartEvent,
    ToolCallsDoneEvent,
)
from aicore.events.task import (
    TaskCancelledEvent,
    TaskCreatedEvent,
    TaskEvent,
    TaskFailureEvent,
    TaskProgressEvent,
    TaskStartEvent,
    TaskSuccessEvent,
)
from aicore.utils.nl_repr import nl_repr_safe

__all__ = [
    "AgentTextEvent",
    "ReActTUIApp",
    "S2STUIEventProfile",
    "TUIEventClient",
    "V1_TUI_EVENT_PROFILE",
    "V1TUIEventClient",
    "V2_TUI_EVENT_PROFILE",
    "build_s2s_event_client",
    "extract_v1_agent_text_event",
    "extract_v2_agent_text_event",
]


TOOL_DISPLAY_NAMES = {
    "weather": "天气查询工具",
    "poi_search": "地点查询工具",
    "websearch": "网页搜索工具",
    "navigation": "导航工具",
    "car_control": "车控工具",
    "media": "媒体控制工具",
    "music_search": "音乐查询工具",
}


ChatRole = Literal["user", "assistant"]
AgentTextEventKind = Literal["start", "delta", "done"]


@dataclass(frozen=True)
class AgentTextEvent:
    kind: AgentTextEventKind
    text: str = ""


@dataclass(frozen=True)
class S2STUIEventProfile:
    make_tui_client: Callable[[ReActTUIApp], Callable[[Any], None]]
    extract_agent_text_event: Callable[[Any], AgentTextEvent | None]


@dataclass
class ChatMessage:
    role: ChatRole
    text: str
    timestamp: str
    avatar: str
    style: str


@dataclass
class TaskRecord:
    task_id: str
    name: str = "unknown"
    display_name: str = "未知任务"
    arguments: dict[str, Any] = field(default_factory=dict)
    argument_summary: str = ""
    status: str = "created"
    progress: str | None = None
    result_summary: str | None = None
    error_summary: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    event_count: int = 0
    raw_result: Any = None
    raw_error: Any = None

    @property
    def title(self) -> str:
        if self.argument_summary:
            return f"{self.display_name}: {self.argument_summary}"
        return self.display_name


TASK_STATUS_LABELS = {
    "created": "已创建",
    "running": "执行中",
    "cancelling": "取消中",
    "succeeded": "成功",
    "failed": "失败",
    "cancelled": "取消",
}


TASK_STATUS_STYLES = {
    "created": "bold white on blue",
    "running": "bold black on yellow",
    "cancelling": "bold black on orange1",
    "succeeded": "bold white on green",
    "failed": "bold white on red",
    "cancelled": "bold black on orange3",
}


class ReActTUIApp(App[None]):
    """v2 ReAct 演示用 Textual UI。"""

    CSS = """
    #main-container {
        layout: vertical;
        height: 1fr;
    }


    #user-asr-top {
        height: 8;
    }

    #chat-block {
        height: 2fr;
    }

    #main-container > Container:last-child {
        layout: horizontal;
        height: 2fr;
    }

    #main-container > Container:last-child > Vertical {
        width: 1fr;
    }

    RichLog {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }

    #user-text {
        height: 4;
    }

    DataTable {
        height: 1fr;
        border: round $primary;
    }

    .window-title {
        color: $primary;
        border-bottom: solid $primary;
        margin-bottom: 1;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("h", "show_help", "帮助"),
        Binding("space", "open_microphone", "开麦"),
        Binding("enter,n", "play_next_audio_file", "下一句"),
        Binding("q,escape", "quit", "退出"),
    ]

    def __init__(self, runner: Callable[[], Awaitable[None]] | None = None) -> None:
        super().__init__()
        self._runner = runner
        self._open_microphone: Callable[[], bool] | None = None
        self._play_next_audio_file: Callable[[], bool] | None = None
        self._chat_messages: list[ChatMessage] = []
        self._streaming_buffer = ""
        self._agent_stream_timestamp = ""
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = Lock()
        # 顶部仅展示实时 ASR delta；final 用户语进入真正的聊天流。
        self._asr_interim_text: str = ""

    def set_runner(self, runner: Callable[[], Awaitable[None]]) -> None:
        self._runner = runner

    def set_microphone_opener(self, opener: Callable[[], bool]) -> None:
        self._open_microphone = opener

    def set_next_audio_file_player(self, player: Callable[[], bool]) -> None:
        self._play_next_audio_file = player

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with Vertical(id="user-asr-top"):
                yield Static("语音识别输入", classes="window-title")
                yield RichLog(id="user-text", auto_scroll=True)
            with Vertical(id="chat-block"):
                yield Static("聊天", classes="window-title")
                yield RichLog(id="chat", auto_scroll=True)
            with Container():
                with Vertical():
                    yield Static("事件和推理轨迹", classes="window-title")
                    yield RichLog(id="log", auto_scroll=True)
                with Vertical():
                    yield Static("任务和工具调用", classes="window-title")
                    yield DataTable(id="tasks")
        yield Footer()

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def on_mount(self) -> None:
        self.run_worker(self._run_runner(), name="runner")

    async def _run_runner(self) -> None:
        if self._runner is None:
            self.write_log("Runner 未设置")
            return

        try:
            self.write_log("Runner 启动")
            await self._runner()
            self.write_log("Runner 结束")
        except Exception:
            self.write_log("Runner 异常退出")
            self.write_log(traceback.format_exc())

    def write_log(self, message: str) -> None:
        log_widget = self.query_one("#log", RichLog)
        log_widget.write(f"[{self._now()}] {message}")

    def start_agent_message(self) -> None:
        '''加锁清空当前轮 assistant streaming，并记下本轮时间。'''
        with self._lock:
            self._streaming_buffer = ""
            self._agent_stream_timestamp = self._now()
        self._render_chat()

    def append_agent_delta(self, delta: str) -> None:
        '''加锁追加 assistant delta 到 streaming。'''
        with self._lock:
            self._streaming_buffer += delta
        self._render_chat()

    def finish_agent_message(self) -> None:
        '''加锁追加 assistant streaming 到聊天历史，清空 streaming_buffer。'''
        with self._lock:
            message = self._streaming_buffer.strip()
            if message != "":
                self._chat_messages.append(
                    self._make_chat_message(
                        "assistant",
                        message,
                        timestamp=self._agent_stream_timestamp or self._now(),
                    )
                )
            self._streaming_buffer = ""
            self._agent_stream_timestamp = ""

        self._render_chat()

    def append_user_message(self, text: str) -> None:
        """ASR final：写入统一聊天流，并清掉顶部实时识别行。"""
        line = text.strip()
        if line == "":
            return
        self._asr_interim_text = ""
        with self._lock:
            self._chat_messages.append(self._make_chat_message("user", line))
        self._render_user_asr_column()
        self._render_chat()

    def _render_user_asr_column(self) -> None:
        log = self.query_one("#user-text", RichLog)
        log.clear()
        if self._asr_interim_text != "":
            log.write(Text(f"🎙️... {self._asr_interim_text}", style="yellow"))

    def _make_chat_message(
        self,
        role: ChatRole,
        text: str,
        *,
        timestamp: str | None = None,
    ) -> ChatMessage:
        if role == "user":
            return ChatMessage(
                role=role,
                text=text,
                timestamp=timestamp or self._now(),
                avatar="🧑",
                style="bright_cyan",
            )
        return ChatMessage(
            role=role,
            text=text,
            timestamp=timestamp or self._now(),
            avatar="🤖",
            style="bright_green",
        )

    def _chat_message_text(self, message: ChatMessage, *, streaming: bool = False) -> Text:
        suffix = "▌" if streaming else ""
        return Text(
            f"[{message.timestamp}] {message.avatar} {message.text}{suffix}",
            style=message.style,
        )

    def _chat_message_renderable(self, message: ChatMessage, *, streaming: bool = False) -> Text:
        return self._chat_message_text(message, streaming=streaming)

    def _render_chat(self) -> None:
        '''清空 #chat，逐条写用户/助手消息；若助手正在 streaming，再写一行光标态。'''
        chat_widget = self.query_one("#chat", RichLog)
        chat_widget.clear()
        with self._lock:
            messages = self._chat_messages.copy()
            streaming_text = self._streaming_buffer
            streaming_timestamp = self._agent_stream_timestamp
        for msg in messages:
            chat_widget.write(self._chat_message_renderable(msg))
        if streaming_text != "":
            streaming_message = self._make_chat_message(
                "assistant",
                streaming_text,
                timestamp=streaming_timestamp or self._now(),
            )
            chat_widget.write(self._chat_message_renderable(streaming_message, streaming=True))

    def _summarize_value(self, value: Any, *, max_length: int = 80) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            summary = value
        else:
            summary = nl_repr_safe(value)
        if len(summary) <= max_length:
            return summary
        return f"{summary[: max_length - 1]}…"

    def _summarize_sequence_result(self, values: list[Any], *, max_length: int = 80) -> str:
        if not values:
            return "无结果"
        first = self._summarize_success_payload(values[0], max_length=max_length)
        return self._summarize_value(f"{len(values)}项 | {first}", max_length=max_length)

    def _summarize_base_model_result(self, value: BaseModel, *, max_length: int = 80) -> str:
        message = getattr(value, "message", None)
        message_text = message.strip() if isinstance(message, str) else ""
        list_fields = [
            getattr(value, field_name)
            for field_name in value.__class__.model_fields
            if isinstance(getattr(value, field_name), list)
        ]
        for list_value in list_fields:
            if list_value:
                return self._summarize_sequence_result(list_value, max_length=max_length)
        if list_fields:
            return self._summarize_value(message_text or "无结果", max_length=max_length)
        if message_text:
            return self._summarize_value(message_text, max_length=max_length)

        has_title = any(field_info.title for field_info in value.__class__.model_fields.values())
        if has_title:
            return self._summarize_value(value, max_length=max_length)
        return self._summarize_value(value.model_dump(exclude_none=True), max_length=max_length)

    def _summarize_success_payload(self, value: Any, *, max_length: int = 80) -> str:
        if isinstance(value, list):
            return self._summarize_sequence_result(value, max_length=max_length)
        if isinstance(value, BaseModel):
            return self._summarize_base_model_result(value, max_length=max_length)
        return self._summarize_value(value, max_length=max_length)

    def _summarize_result(self, result: Any) -> str:
        is_success = getattr(result, "is_success", None)
        if is_success is False:
            nl_repr_method = getattr(result, "nl_repr", None)
            if callable(nl_repr_method):
                summary = nl_repr_method()
                if isinstance(summary, str):
                    return self._summarize_value(summary)
            error = getattr(result, "error", None)
            if error is not None:
                return self._summarize_value(error)
        if is_success is True and hasattr(result, "data"):
            return self._summarize_success_payload(getattr(result, "data"))
        return self._summarize_success_payload(result)

    def _summarize_arguments(self, arguments: dict[str, Any]) -> str:
        if not arguments:
            return ""
        if "query" in arguments:
            return self._summarize_value(arguments["query"])
        return self._summarize_value(arguments)

    def _duration_text(self, task: TaskRecord) -> str:
        if task.finished_at is None:
            return ""
        start = task.started_at or task.created_at
        if start is None:
            return "-"
        elapsed = (task.finished_at - start).total_seconds()
        return f"{elapsed:.1f}s"

    def _task_status_text(self, task: TaskRecord) -> Text:
        label = TASK_STATUS_LABELS.get(task.status, task.status)
        style = TASK_STATUS_STYLES.get(task.status, "white")
        return Text(label, style=style)

    def _task_table_row(self, task: TaskRecord) -> tuple[Text, str, str, str, str]:
        detail = task.error_summary or task.result_summary or ""
        return (
            self._task_status_text(task),
            task.display_name,
            task.argument_summary,
            self._duration_text(task),
            detail,
        )

    def _task_table_columns(self) -> list[tuple[str, int]]:
        return [
            ("状态", 4),
            ("工具", 12),
            ("参数", 20),
            ("耗时", 8),
            ("结果/错误", 32),
        ]

    def _render_tasks(self) -> None:
        task_widget = self.query_one("#tasks", DataTable)
        task_widget.clear(columns=True)
        for label, width in self._task_table_columns():
            task_widget.add_column(label, width=width)
        for task in self._tasks.values():
            task_widget.add_row(*self._task_table_row(task), key=task.task_id)

    def _ensure_task_record(self, task_id: str) -> TaskRecord:
        current = self._tasks.get(task_id)
        if current is None:
            current = TaskRecord(task_id=task_id)
            self._tasks[task_id] = current
        return current

    def _set_task_status(self, task_id: str, status: str) -> TaskRecord:
        current = self._ensure_task_record(task_id)
        current.status = status
        current.event_count += 1
        self._tasks[task_id] = current
        return current

    def task_title(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        return task.title if task is not None else task_id

    def show_task_created(self, event: TaskCreatedEvent) -> None:
        current = self._ensure_task_record(event.task_id)
        current.name = event.name
        current.display_name = TOOL_DISPLAY_NAMES.get(event.name, event.name)
        current.arguments = event.arguments
        current.argument_summary = self._summarize_arguments(event.arguments)
        current.created_at = current.created_at or datetime.now()
        current.event_count += 1
        self._render_tasks()

    def show_task_start(self, event: TaskStartEvent) -> None:
        current = self._set_task_status(event.task_id, "running")
        current.started_at = current.started_at or datetime.now()
        self._render_tasks()

    def show_task_progress(self, event: TaskProgressEvent[Any]) -> None:
        current = self._set_task_status(event.task_id, "running")
        current.progress = self._summarize_value(event.progress)
        current.started_at = current.started_at or datetime.now()
        self._render_tasks()

    def show_task_success(self, event: TaskSuccessEvent[Any]) -> None:
        current = self._set_task_status(event.task_id, "succeeded")
        current.raw_result = event.result
        current.result_summary = self._summarize_result(event.result)
        current.finished_at = datetime.now()
        self._render_tasks()

    def show_task_failure(self, event: TaskFailureEvent[Any]) -> None:
        current = self._set_task_status(event.task_id, "failed")
        current.raw_error = event.error
        current.error_summary = self._summarize_value(event.error)
        current.finished_at = datetime.now()
        self._render_tasks()

    def show_task_cancelled(self, event: TaskCancelledEvent) -> None:
        reason = event.reason or "无"
        current = self._set_task_status(event.task_id, "cancelled")
        current.error_summary = reason
        current.finished_at = datetime.now()
        self._render_tasks()

    def action_show_help(self) -> None:
        controls = ["h 帮助"]
        if self._open_microphone is not None:
            controls.append("空格开麦")
        if self._play_next_audio_file is not None:
            controls.append("Enter/n 播放下一句")
        controls.append("q/ESC 退出")
        self.write_log(f"快捷键: {', '.join(controls)}")
        return

    def action_play_next_audio_file(self) -> None:
        if self._play_next_audio_file is None:
            return
        if self._play_next_audio_file():
            self.write_log("播放下一句预设语音")

    def action_open_microphone(self) -> None:
        if self._open_microphone is not None:
            self._open_microphone()

    def show_microphone_opened(self) -> None:
        self.write_log("麦克风已打开")

    def show_microphone_closed(self) -> None:
        self.write_log("麦克风已关闭")

    def show_asr_delta(self, text: str) -> None:
        self._asr_interim_text = text.strip()
        self._render_user_asr_column()

    async def action_quit(self) -> None:
        self.exit()


class V1TUIEventClient:
    """把 v1 ReAct/Task/Memory 事件映射到共享 Textual UI。"""

    def __init__(self, app: ReActTUIApp):
        self.app = app
        self._pending_tool_task_ids: list[str] = []
        self._runner_task_id_map: dict[str, str] = {}
        self._tool_task_index = 0

    def _pop_first_pending_tool_id(self) -> str | None:
        if not self._pending_tool_task_ids:
            return None
        return self._pending_tool_task_ids.pop(0)

    def _bind_runner_task_id(self, runner_task_id: str) -> str | None:
        if runner_task_id in self._runner_task_id_map:
            return self._runner_task_id_map[runner_task_id]
        ui_task_id = self._pop_first_pending_tool_id()
        if ui_task_id is None:
            return None
        self._runner_task_id_map[runner_task_id] = ui_task_id
        return ui_task_id

    def _resolve_runner_task_id(self, runner_task_id: str) -> str | None:
        return self._runner_task_id_map.get(runner_task_id)

    def _pop_runner_task_id(self, runner_task_id: str) -> str | None:
        return self._runner_task_id_map.pop(runner_task_id, None)

    def __call__(self, event: Any) -> None:
        match event:
            case ReActStartEvent() | ToolCallsDoneEvent():
                return
            case ReActTextStartEvent():
                self.app.start_agent_message()
                self.app.write_log("助手回复开始")
            case ReActTextDeltaEvent():
                self.app.append_agent_delta(event.delta)
            case ReActTextDoneEvent():
                self.app.finish_agent_message()
                self.app.write_log("助手回复结束")
            case ToolCallStartEvent():
                self._tool_task_index += 1
                task_id = f"round-{event.round}-{self._tool_task_index}-{event.name}"
                self._pending_tool_task_ids.append(task_id)
                trans_event = TaskCreatedEvent(
                    task_id=task_id,
                    name=event.name,
                    arguments=event.arguments,
                )
                self.app.show_task_created(trans_event)
                self.app.write_log(f"工具调用创建: {self.app.task_title(task_id)}")
            case TaskToolDoneEvent():
                return
            case ReActFinishEvent():
                self.app.write_log("ReAct 完成")
            case ReActErrorEvent():
                self.app.write_log(f"ReAct 失败: {event.reason}")
            case TaskStartEvent():
                sid = self._bind_runner_task_id(event.task_id)
                if sid is None:
                    return
                self.app.show_task_start(TaskStartEvent(task_id=sid))
            case TaskProgressEvent():
                sid = self._resolve_runner_task_id(event.task_id)
                if sid is None:
                    return
                self.app.show_task_progress(
                    TaskProgressEvent[Any](task_id=sid, progress=event.progress)
                )
            case TaskSuccessEvent():
                sid = self._pop_runner_task_id(event.task_id)
                if sid is None:
                    return
                self.app.show_task_success(TaskSuccessEvent(task_id=sid, result=event.result))
            case TaskFailureEvent():
                sid = self._pop_runner_task_id(event.task_id)
                if sid is not None:
                    self.app.show_task_failure(TaskFailureEvent(task_id=sid, error=event.error))
                    self.app.write_log(f"任务失败: {self.app.task_title(sid)}")
                else:
                    self.app.show_task_failure(event)
                    self.app.write_log(f"任务失败: {self.app.task_title(event.task_id)}")
            case TaskCancelledEvent():
                sid = self._pop_runner_task_id(event.task_id)
                if sid is not None:
                    self.app.show_task_cancelled(
                        TaskCancelledEvent(task_id=sid, reason=event.reason)
                    )
                else:
                    self.app.show_task_cancelled(event)
            case MemoryAddPendingEvent():
                self.app.write_log(f"Memory 待处理: {event.pending_count}/{event.session_size}")
            case MemoryAddProcessingEvent():
                self.app.write_log(f"Memory 写入中: {event.processed_count}")
            case MemoryAddCompletedEvent():
                self.app.write_log(f"Memory 完成: {event.session_id}")
            case MemoryAddFailedEvent():
                self.app.write_log(f"Memory 失败: {event.error}")
            case _:
                self.app.write_log(str(event))


class TUIEventClient:
    """把 v2 Agent/Task 事件映射到 Textual UI。"""

    def __init__(self, app: ReActTUIApp):
        self.app = app

    def __call__(self, event: AgentOutEvent | TaskEvent) -> None:
        match event:
            case AgentOutTextStartEvent():
                self.app.start_agent_message()
                self.app.write_log("助手回复开始")
            case AgentOutTextDeltaEvent():
                self.app.append_agent_delta(event.delta)
            case AgentOutTextDoneEvent():
                self.app.finish_agent_message()
                self.app.write_log("助手回复结束")
            case TaskCreatedEvent():
                self.app.show_task_created(event)
                self.app.write_log(f"工具调用创建: {self.app.task_title(event.task_id)}")
            case TaskStartEvent():
                self.app.show_task_start(event)
            case TaskProgressEvent():
                self.app.show_task_progress(event)
            case TaskSuccessEvent():
                self.app.show_task_success(event)
            case TaskFailureEvent():
                self.app.show_task_failure(event)
                self.app.write_log(f"任务失败: {self.app.task_title(event.task_id)}")
            case TaskCancelledEvent():
                self.app.show_task_cancelled(event)


def extract_v1_agent_text_event(event: Any) -> AgentTextEvent | None:
    match event:
        case ReActTextStartEvent():
            return AgentTextEvent("start")
        case ReActTextDeltaEvent():
            return AgentTextEvent("delta", event.delta)
        case ReActTextDoneEvent():
            return AgentTextEvent("done")
        case _:
            return None


def extract_v2_agent_text_event(event: Any) -> AgentTextEvent | None:
    match event:
        case AgentOutTextStartEvent():
            return AgentTextEvent("start")
        case AgentOutTextDeltaEvent():
            return AgentTextEvent("delta", event.delta)
        case AgentOutTextDoneEvent():
            return AgentTextEvent("done")
        case _:
            return None


def build_s2s_event_client(
    *,
    tui_app: ReActTUIApp | None,
    profile: S2STUIEventProfile,
    on_text_start: Callable[[], None],
    on_text_delta: Callable[[str], None],
    on_text_done: Callable[[], None],
) -> Callable[[Any], None]:
    tui_client = profile.make_tui_client(tui_app) if tui_app is not None else None

    def client(event: Any) -> None:
        if tui_client is not None and tui_app is not None:
            tui_app.call_later(lambda e=event: tui_client(e))

        text_event = profile.extract_agent_text_event(event)
        if text_event is None:
            return
        match text_event.kind:
            case "start":
                on_text_start()
            case "delta":
                on_text_delta(text_event.text)
            case "done":
                on_text_done()

    return client


V1_TUI_EVENT_PROFILE = S2STUIEventProfile(
    make_tui_client=V1TUIEventClient,
    extract_agent_text_event=extract_v1_agent_text_event,
)
V2_TUI_EVENT_PROFILE = S2STUIEventProfile(
    make_tui_client=TUIEventClient,
    extract_agent_text_event=extract_v2_agent_text_event,
)
