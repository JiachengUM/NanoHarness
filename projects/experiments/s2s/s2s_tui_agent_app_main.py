from __future__ import annotations

# S2STUIAgentApp + ReActTUIApp 入口。多轮边界（静音超时 / 关键字 ``SESSION_RESET_INPUT``）依赖
# Runner 侧用 SessionResetInterceptAgent 包裹内层 Agent；本文件 build_v1_runner_bundle 已包裹，
# build_v2_runner_bundle 默认未包裹——若要在 v2-tui 上使用多轮重置，需同样在 v2 agent 外再包一层拦截器。

import argparse
import asyncio
from functools import partial
from typing import Any, Callable

from projects.experiments.s2s.s2s_tui_agent_app import (
    AudioFilePlaybackMode,
    MicMode,
    QueueUserDataSource,
    S2SAgentAppConfig,
    S2STUIAgentApp,
)
from projects.experiments.s2s.tui import (
    ReActTUIApp,
    V1_TUI_EVENT_PROFILE,
    V2_TUI_EVENT_PROFILE,
    build_s2s_event_client,
)


def build_v1_runner_bundle(
    *,
    user_data: QueueUserDataSource,
    on_text_start: Callable[[], None],
    on_text_delta: Callable[[str], None],
    on_text_done: Callable[[], None],
    tui_app: ReActTUIApp | None = None,
) -> tuple[Any, Any]:
    from aicore.simulation.agent_runner import AgentRunnerBase
    from projects.experiments.s2s.session_runner import SessionResetInterceptAgent
    from projects.sgm_prod.v1 import create_agent

    client = build_s2s_event_client(
        tui_app=tui_app,
        profile=V1_TUI_EVENT_PROFILE,
        on_text_start=on_text_start,
        on_text_delta=on_text_delta,
        on_text_done=on_text_done,
    )

    agent = create_agent(chat_id="test_v1_chat")
    # 使得 App 投递的 SESSION_RESET_INPUT 在 astream 入口被吞并转为 new_session，而非进模型。
    intercept = SessionResetInterceptAgent(agent)
    runner = AgentRunnerBase(user_data=user_data, agent=intercept, client=client)
    return runner, agent


def build_v2_runner_bundle(
    *,
    user_data: QueueUserDataSource,
    on_text_start: Callable[[], None],
    on_text_delta: Callable[[str], None],
    on_text_done: Callable[[], None],
    tui_app: ReActTUIApp | None = None,
) -> tuple[Any, Any]:
    from aicore.models.credentials import ModelName
    from aicore.runtime.task import TaskManager
    from aicore.v2.agent_runner import AgentRunner
    from aicore.v2.experiments.react_agent_with_task_runner import (
        create_react_agent_with_task_runner,
    )
    from aicore.v2.experiments.task_cancel_tool import create_task_cancel_tool
    from projects.experiments.s2s.s2s_agent_config import build_v2_s2s_system_prompt

    client = build_s2s_event_client(
        tui_app=tui_app,
        profile=V2_TUI_EVENT_PROFILE,
        on_text_start=on_text_start,
        on_text_delta=on_text_delta,
        on_text_done=on_text_done,
    )
    from projects.mind.toolset.experiments.async_task_tools import get_async_task_tools

    task_manager = TaskManager()
    tools = [
        *get_async_task_tools(chat_id="CHAT_ID", task_manager=task_manager),
        create_task_cancel_tool(task_manager=task_manager),
    ]
    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_1_8_251228,
        tools=tools,
        system_prompt=build_v2_s2s_system_prompt(),
    )
    # 注意：此处 agent 未被 SessionResetInterceptAgent 包裹时，App 侧的 multiturn 哨兵无法满足「new_session」语义。
    runner = AgentRunner(
        user_data=user_data,
        agent=agent,
        task_manager=task_manager,
        client=client,
    )
    return runner, agent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the reusable S2S TUI agent app demo.")
    parser.add_argument(
        "--agent-version",
        choices=("v1-terminal", "v1-tui", "v2-terminal", "v2-tui"),
        default="v2-tui",
        help="Demo runner/agent factory and display mode to use.",
    )
    parser.add_argument(
        "--mic-mode",
        choices=("space_gate", "continuous"),
        default="space_gate",
        help="Use space-gated microphone input or continuous microphone streaming.",
    )
    return parser.parse_args()


async def run_plain(factory: Callable[..., tuple[Any, Any]], mic_mode: MicMode) -> None:
    app = S2STUIAgentApp(
        config=S2SAgentAppConfig(mic_mode=mic_mode),
        runner_factory=factory,
    )
    await app.start()


def run_tui(
    factory: Callable[..., tuple[Any, Any]],
    mic_mode: MicMode,
    *,
    audio_file_list: list[tuple[str, float]] | None = None,
    audio_file_playback_mode: AudioFilePlaybackMode = "auto",
    s2s_audio_gain: float = 1.0,
    # 任选：静音超时（秒）；计时从上一轮 Agent chat_tts 播完算起，参见 s2s_tui_agent_app 模块头注释。
    multiturn_session_idle_sec: float | None = None,
    # 任选：finalized 用户文案含此子串时在正常 put 本条后再 put SESSION_RESET_INPUT。
    multiturn_session_end_keyword: str | None = None,
    multiturn_idle_session_farewell_text: str | None = None,
) -> None:
    tui_app = ReActTUIApp()

    def show_user_text(text: str, interim: bool) -> None:
        if interim:
            tui_app.call_later(lambda t=text: tui_app.show_asr_delta(t))
            return

        def _apply(t: str = text) -> None:
            tui_app.show_asr_delta("")
            tui_app.append_user_message(t)

        tui_app.call_later(_apply)

    def show_microphone_state(state: str) -> None:
        if state == "opened":
            tui_app.call_later(tui_app.show_microphone_opened)
        elif state == "closed":
            tui_app.call_later(tui_app.show_microphone_closed)

    def multiturn_log_to_ui(line: str) -> None:
        # 必须从 asyncio 线程投回 Textual 主线程，与 show_user_text / microphone 回调一致。
        tui_app.call_later(lambda t=line: tui_app.write_log(t))

    def synthetic_assistant_to_chat(text: str) -> None:
        """静音告别等：不经 Runner，与正常助手流相同写入 #chat。"""

        def _apply(t: str = text) -> None:
            tui_app.start_agent_message()
            tui_app.append_agent_delta(t)
            tui_app.finish_agent_message()

        tui_app.call_later(_apply)

    bound_factory = partial(factory, tui_app=tui_app)
    use_files = bool(audio_file_list)
    app = S2STUIAgentApp(
        config=S2SAgentAppConfig(
            mic_mode=mic_mode,
            keyboard_control="external",
            input_source="audio_files" if use_files else "microphone",
            audio_file_list=audio_file_list if use_files else [],
            audio_file_playback_mode=audio_file_playback_mode,
            s2s_audio_gain=s2s_audio_gain,
            say_hello=None,
            # 以下三项传入即启用 App 内多轮策略；完成 new_session 与否仍取决于 factory 是否提供拦截 Agent。
            multiturn_session_idle_sec=multiturn_session_idle_sec,
            multiturn_session_end_keyword=multiturn_session_end_keyword,
            multiturn_idle_session_farewell_text=multiturn_idle_session_farewell_text,
        ),
        runner_factory=bound_factory,
        user_text_client=show_user_text,
        microphone_state_client=show_microphone_state,
        multiturn_log_client=multiturn_log_to_ui,
        synthetic_assistant_text_ui_client=synthetic_assistant_to_chat,
    )
    tui_app.set_microphone_opener(lambda: app.open_microphone_for_user_input(source="tui-space"))
    if use_files and audio_file_playback_mode == "manual":
        tui_app.set_next_audio_file_player(app.request_next_audio_file)
    tui_app.set_runner(app.start)
    tui_app.run()


def main() -> None:
    args = parse_args()
    mic_mode: MicMode = args.mic_mode
    audio_file_list: list[tuple[str, float]] | None = [
        # ("projects\experiments\s2s\audio_file\example.wav", 1.0),
    ]

    if args.agent_version == "v1-terminal":
        asyncio.run(run_plain(build_v1_runner_bundle, mic_mode))
    elif args.agent_version == "v2-terminal":
        asyncio.run(run_plain(build_v2_runner_bundle, mic_mode))
    elif args.agent_version == "v1-tui":
        run_tui(build_v1_runner_bundle, mic_mode, audio_file_list=audio_file_list)
    else:
        run_tui(build_v2_runner_bundle, mic_mode, audio_file_list=audio_file_list)


if __name__ == "__main__":
    main()
