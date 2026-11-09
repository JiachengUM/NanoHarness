"""通过物理语音链路执行奔驰数据集自动评测。

每轮流程：
1. 首轮朗读数据集 ``user_query_lists`` 中的第一句；
2. 通过麦克风识别外部被测设备的回复；
3. 后续由 FakePerson 根据 ``expected_script`` 生成台词并继续朗读；
4. 对完整对话执行自动评测并输出报告。

"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Callable

from rich import print

from projects.experiments.s2s.config import (
    AsrExtraModel,
    start_session_req,
    ws_connect_config,
)
from projects.experiments.s2s.realtime_dialog_client import (
    ChatTtsTextRequest,
    RealtimeClientOptions,
    RealtimeDialogClient,
    SayHelloRequest,
)
from projects.experiments.s2s.s2s_tui_agent_app import (
    QueueUserDataSource,
    S2SAgentAppConfig,
    S2STUIAgentApp,
)
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list,
)

# vad 超时时间[500ms,50s],单位ms
VAD_TIMEOUT_MS = 2000
# 唤醒词
WAKE_UP_WORD = "你好奔驰"
# 与 s2s_voice_bot 对齐：假人告别语播完后不再等车机 ASR
GOODBYE_QUERY_MARKERS = ("退下", "再见", "拜拜")
GOODBYE_ASSISTANT_REPLY = "（助手已结束会话）"
DATASET_NAMES = ["奔驰项目多轮对话测试集"]

EXTERNAL_REPLY_TIMEOUT_SEC = float(os.getenv("BENZ_EXTERNAL_REPLY_TIMEOUT_SEC", "60"))
TTS_TIMEOUT_SEC = float(os.getenv("BENZ_TTS_TIMEOUT_SEC", "90"))


def _is_goodbye_query(text: str) -> bool:
    return any(marker in text for marker in GOODBYE_QUERY_MARKERS)

REPORT_DIR = Path(__file__).resolve().parent
JUDGE_LOG_PATH = REPORT_DIR / "benz_demo_judge_log.txt"
REPORT_MD_PATH = REPORT_DIR / "benz_demo_report.md"


class ExternalReplyRunner:
    """消费麦克风 ASR，并把外部设备回复交给评测 Bot。"""

    def __init__(
        self,
        *,
        user_data: QueueUserDataSource,
        reply_queue: asyncio.Queue[str],
    ) -> None:
        self.user_data = user_data
        self.reply_queue = reply_queue
        self._agent = object()

    async def run(self) -> None:
        async for text in self.user_data():
            await self.reply_queue.put(text)


class PhysicalVoiceBridge:
    """复用 S2S 壳完成文本朗读、麦克风采集和 ASR。"""

    def __init__(self) -> None:
        self.reply_queue: asyncio.Queue[str] = asyncio.Queue()
        self.app: S2STUIAgentApp | None = None
        self.app_task: asyncio.Task[Any] | None = None
        self.lock = asyncio.Lock()
        # 评测框架 session_id；切换时重建火山 Session（每条 Session 仅可 SayHello 一次）
        self._current_session_id = ""
        self._speak_index_in_session = 0

    def _build_start_session_req(self):
        custom_req = start_session_req.model_copy(deep=True)
        custom_req.asr.extra = AsrExtraModel(
            end_smooth_window_ms=VAD_TIMEOUT_MS,
            enable_custom_vad=True,
        )
        return custom_req

    async def _ensure_framework_session(self, session_id: str) -> None:
        """framework session_id 不变则复用；切换则 close+start 重建火山 Session。"""
        if session_id == self._current_session_id:
            await self.start()
            return
        if self._current_session_id:
            print(
                f"[S2S] framework session 切换，重建语音桥接: "
                f"{self._current_session_id[:8]}… → {session_id[:8]}…"
            )
            await self.close()
        self._current_session_id = session_id
        self._speak_index_in_session = 0
        await self.start()

    def _build_runner(
        self,
        *,
        user_data: QueueUserDataSource,
        on_text_start: Callable[[], None],
        on_text_delta: Callable[[str], None],
        on_text_done: Callable[[], None],
        **_: Any,
    ) -> tuple[ExternalReplyRunner, object]:
        del on_text_start, on_text_delta, on_text_done
        runner = ExternalReplyRunner(user_data=user_data, reply_queue=self.reply_queue)
        return runner, runner._agent

    async def start(self) -> None:
        if self.app_task is not None:
            return

        custom_req = self._build_start_session_req()
        client = RealtimeDialogClient(
            options=RealtimeClientOptions(
                ws_config=ws_connect_config,
                session_id=f"benz-physical-auto-test-{int(asyncio.get_running_loop().time())}",
            ),
            start_session_req=custom_req,
        )
        self.app = S2STUIAgentApp(
            config=S2SAgentAppConfig(
                mic_mode="space_gate",
                keyboard_control="none",
                say_hello=None,
            ),
            runner_factory=self._build_runner,
            realtime_client=client,
            # server_event_printer=None,
        )
        self.app_task = asyncio.create_task(self.app.start())

        while self.app.runner_task is None:
            if self.app_task.done():
                await self.app_task
                raise RuntimeError("S2S 语音桥接启动失败")
            await asyncio.sleep(0.05)

    def _clear_replies(self) -> None:
        while not self.reply_queue.empty():
            self.reply_queue.get_nowait()

    async def _speak(self, text: str, *, use_say_hello: bool) -> None:
        assert self.app is not None
        tts_done = asyncio.Event()
        self.app._chat_tts_gate = tts_done
        self.app.state.agent_voice_only = False
        try:
            if use_say_hello:
                # 每个火山 Session 仅首轮走 SayHello 开场
                await self.app.client.send_say_hello(
                    SayHelloRequest(content=WAKE_UP_WORD + text if WAKE_UP_WORD else text)
                )
            else:
                line = text.strip()
                await self.app.client.send_chat_tts_text(
                    ChatTtsTextRequest(start=True, end=False, content=line)
                )
                await self.app.client.send_chat_tts_text(
                    ChatTtsTextRequest(start=False, end=True, content="")
                )
            await asyncio.wait_for(tts_done.wait(), timeout=TTS_TIMEOUT_SEC)
        finally:
            self.app._chat_tts_gate = None
        await self.app._await_assistant_speaker_audio_queue_drained()

    def _prepare_tts_state_after_goodbye(self) -> None:
        assert self.app is not None
        self.app._cancel_tts_stream_end_debounce()
        self.app.state.agent_voice_only = False

    async def speak_and_listen(self, text: str, session_id: str) -> str:
        async with self.lock:
            await self._ensure_framework_session(session_id)
            assert self.app is not None

            use_say_hello = self._speak_index_in_session == 0
            self._clear_replies()
            mode = "SayHello" if use_say_hello else "ChatTTSText"
            print(f"[假人朗读/{mode}] {text}")
            await self._speak(text, use_say_hello=use_say_hello)
            self._speak_index_in_session += 1

            if _is_goodbye_query(text):
                self._prepare_tts_state_after_goodbye()
                print(f"[告别语] 跳过等待外部回复，直接返回: {GOODBYE_ASSISTANT_REPLY}")
                return GOODBYE_ASSISTANT_REPLY

            self._clear_replies()
            if not self.app.open_microphone_for_user_input(source="auto-test"):
                raise RuntimeError("朗读结束后无法打开麦克风")
            print("[等待外部回复]")
            try:
                deadline = asyncio.get_running_loop().time() + EXTERNAL_REPLY_TIMEOUT_SEC
                reply = ""
                while self.app.state.is_running:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        reply = await asyncio.wait_for(
                            self.reply_queue.get(),
                            timeout=min(0.2, remaining),
                        )
                        break
                    except TimeoutError:
                        continue
                else:
                    raise KeyboardInterrupt
            finally:
                if self.app is not None and self.app.state.is_running:
                    self.app.close_microphone_after_user_input(source="auto-test")
            print(f"[外部回复] {reply}")
            return reply

    async def close(self) -> None:
        if self.app is not None:
            self.app.stop()
        if self.app_task is not None:
            await asyncio.gather(self.app_task, return_exceptions=True)
        self.app = None
        self.app_task = None
        self._current_session_id = ""
        self._speak_index_in_session = 0
        self._clear_replies()


class PhysicalVoiceBot:
    """AnyBotToTest：用户侧由假人朗读，助手侧来自外部设备语音。"""

    _bridge = PhysicalVoiceBridge()

    def __init__(self, context_config: dict[str, Any]) -> None:
        self.context_config = dict(context_config)
        self.session_id = ""
        self.query = ""
        self.answer = ""
        self.turn_records: list[dict[str, str]] = []
        self.state_trace: list[dict[str, str]] = []

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        self.context_config.update(context_config)

    async def achat(self, query: str, session_id: str) -> str:
        if self.session_id and self.session_id != session_id:
            self.turn_records = []
            self.state_trace = []
        self.session_id = session_id
        self.query = query
        self.answer = await self._bridge.speak_and_listen(query, session_id)
        self.turn_records.extend(
            [
                {"role": "user", "content": query},
                {"role": "assistant", "content": self.answer},
            ]
        )
        self.state_trace.append({"query": query, "answer": self.answer})
        return self.answer

    async def adump_history(self) -> list[dict[str, str]]:
        return list(self.turn_records)

    async def adump_state_trace(self) -> dict[str, Any]:
        """每轮只返回当前轮的 query/answer/events，不携带历史轮次累积数据。"""
        query = self.query or ""
        answer = self.answer or ""
        round_events: list[dict[str, str]] = []
        if query:
            round_events.append({"type": "physical_voice.user_query", "text": query})
        if answer:
            round_events.append(
                {"type": "physical_voice.assistant_reply", "text": answer}
            )
        return {
            "system_prompt": None,
            "session_id": self.session_id or "",
            "query": query,
            "answer": answer,
            "traces": round_events,
            "metadata": {"mode": "physical_voice_bridge"},
        }

    @classmethod
    def create(
        cls,
        context_config: dict[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> "PhysicalVoiceBot":
        del args
        return cls({**context_config, **kwargs})

    @classmethod
    async def aclean_memory_for_users(
        cls,
        user_ids: list[str],
        *,
        context_config: dict[str, Any] | None = None,
        except_skills: bool = False,
    ) -> None:
        del user_ids, context_config, except_skills
        # 用例切换时释放语音桥接，下一轮 achat 会自动重建
        await cls._bridge.close()

    @classmethod
    async def close_bridge(cls) -> None:
        await cls._bridge.close()

from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.mem.volc_api import Message
example_case1  = TestCase(
    id = "example_case1",
    case_id="example_case1",
    context_config={},
    max_round=5,
    user_query_lists=[[Message(role="user", content="打开前排车窗，并播放音乐")]],
    expected_script="""
    用户：打开前排的车窗，并播放音乐
    助手：好的，正在打开前排车窗，并播放音乐。
    用户：后排车窗也打开吧。
    助手：好的xxxx。
    """,
    nl_assertion=[
        "考察智能体是否能正确理解车主的需求解决问题。",
    ],
    case_description="这是一个考察智能体是否能正确理解车主的需求解决问题的case。"
)

async def main() -> None:
    # 已入库的case
    cases = await get_dataset_list(DATASET_NAMES)

    # cases = [example_case1]
    cases = cases[:2]

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=PhysicalVoiceBot,
        memory_test_cases=cases,
        show_progress=False,
        log_dialogue=True,
        verbose=True,
    )

    run_result: RunAllCasesResult | None = None
    try:
        async for item in auto_test.arun_full_auto_judge_test(
            concurrency_mode=False,
            concurrency_num=1,
            pause_mode=False,
            memory_reset_mode=False,
            upload_history_to_volc_memory=False,
        ):
            if isinstance(item, RunCaseResult):
                print(
                    f"[完成] case_id={item.case_id}, "
                    f"execution_success={item.execution_success}, is_passed={item.is_passed}"
                )
            elif isinstance(item, RunAllCasesResult):
                run_result = item
    except KeyboardInterrupt:
        print("\n[yellow]评测已由用户中断[/yellow]")
    finally:
        await PhysicalVoiceBot.close_bridge()

    if run_result is None:
        return

    auto_test.write_test_task_judge_log(
        dataset_names=DATASET_NAMES,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        judge_result=run_result.result,
        log_file_path=str(JUDGE_LOG_PATH),
        details_result_list=run_result.details_result_list,
    )
    auto_test.write_test_task_report(
        dataset_names=DATASET_NAMES,
        result_str=run_result.result,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        report_file_path=str(REPORT_MD_PATH),
    )

    print(f"评测完成: {run_result.passed_case_num}/{run_result.total_case_num}")
    print(f"日志: {JUDGE_LOG_PATH}")
    print(f"报告: {REPORT_MD_PATH}")


if __name__ == "__main__":
    asyncio.run(main())