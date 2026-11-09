from __future__ import annotations

from functools import partial

from aicore.v2.experiments.tui import ReActTUIApp

from aicore.agents.experiments.volc_memory_store import batch_clear_volc_memory_for_users
from projects.experiments.s2s.tts_client import TextTurn, build_audio_file_list
from projects.experiments.s2s.s2s_tui_agent_app import (
    AudioFilePlaybackMode,
    S2SAgentAppConfig,
    S2STUIAgentApp,
)
from projects.experiments.s2s.s2s_tui_agent_app_main import build_v1_runner_bundle
from projects.mind.mem.volc_api import CollectionID
from projects.sgm_prod import v1 as sgm_v1

# 只需要改 ACTIVE_CASE_NAME 切换 demo case。
# main() 在每次进入 run_tui 前会清空与 create_agent 默认一致的 Volc 记忆（clear_demo_volc_memory_before_case）。
# ── 多轮机制与本 demo 的对应关系 ─────────────────────────────────────
# - 静音与「退下」：与 ``s2s_tui_agent_app_main.run_tui`` 一致；本 demo 额外设置
#   ``multiturn_idle_anchor_after_react_turn_only=True``（在 ``S2SAgentAppConfig`` 中，不由 main 传入）。
#   * 静音 20s：在 **本条 ASR 对应的 ReAct 已 Finish**（多工具/多段文本时不会在首段 TTS 后就计时）且
#     **尾段 chat_tts 播完** 后起算；若用户再无 ASR finalize，则先播告别语再
#     ``SESSION_RESET_INPUT`` → ``new_session``（见 SessionResetInterceptAgent）。
#   * 关键字「退下」：本条话仍照常进模型生成回复；随后队列追加哨兵触发 ``new_session``，进入下一轮。
# - 音频段间较长的 ``delay_after_sec``（如下方 17s）常用于在上一段 TTS 结束后人为拉长静音段，触发空闲告别。
# delay 会写进该轮音频开头静音；
# 自动播放场景中，原来的段后等待已经合并到下一轮 delay。
# 多轮会话：两段 finalized ASR 之间静音超过 5s 会先播报助手告别语再 new_session；
# 文案含「退下」时本轮仍会交给 Agent 回复，回复结束后再 new_session。
DEMO_CASES: dict[str, list[TextTurn]] = {
    # 1、简单解释CASE，一句话解释所有case
    # 2、开始演示第一个case，先解释演示界面
    # 3、agent工作的静默期演讲者要增加一下内容缓解
    "单任务，极速车控": [
        TextTurn(
            "打开空调",
            0.5,
        )
    ],
    "多任务处理": [
        TextTurn(
            "帮我看看上海今天的天气怎么样，找一家上海徐汇区西岸凤巢的咖啡店，再推荐一首张学友的歌",
            delay=0.5,
        )
    ],
    "工具失败/超时": [
        TextTurn(
            "搜一搜上海有什么展会可以看？",
            0.5,
        )
    ],
    "记忆1-基础生产+消费case": [
        TextTurn("记住，我家住在浦江镇", 0),
        TextTurn("退下", 0),
        # 结束一次多轮对话
        # 新的一次多轮对话
        TextTurn("回家", 0),
    ],
    "记忆2-记忆生产，更新，消费": [
        TextTurn("记住，我住浦江镇浦江智汇园。", 0),
        TextTurn("退下", 0),
        # 结束一次多轮对话
        # 新的一次多轮对话
        TextTurn("记住，我搬到汤臣一品了。", 0),
        TextTurn("退下", 0),
        # 结束一次多轮对话
        # 新的一次多轮对话
        TextTurn("回家。", 0),
        # 超时自然结束
    ]
}

# ACTIVE_CASE_NAME = "单任务，极速车控"
# ACTIVE_CASE_NAME = "多任务处理"
# ACTIVE_CASE_NAME = "工具失败/超时"
# ACTIVE_CASE_NAME = "记忆1-基础生产+消费case"
ACTIVE_CASE_NAME = "记忆2-记忆生产，更新，消费"
TEXT_TURNS = DEMO_CASES[ACTIVE_CASE_NAME]


def clear_demo_volc_memory_before_case(*, case_label: str) -> None:
    """
    与 ``projects.sgm_prod.v1.create_agent`` 默认记忆参数对齐，清空该用户在目标库下的
    全部事件记忆与画像记忆（单次批量 filter，避免高并发删除）。
    """
    collection_id = CollectionID(
        collection_name=sgm_v1.MEMORY_COLLECTION_NAME,
        project_name="default",
    )
    batch_clear_volc_memory_for_users(
        collection_id,
        [sgm_v1.DEFAULT_MEMORY_USER_ID],
        sgm_v1.TEST_ASSISTANT_ID,
        mode="all",
    )
    print(
        f"[DEMO] case「{case_label}」开始前：已清空 Volc 记忆 "
        f"(user_id={sgm_v1.DEFAULT_MEMORY_USER_ID!r}, "
        f"collection={sgm_v1.MEMORY_COLLECTION_NAME!r}, assistant={sgm_v1.TEST_ASSISTANT_ID!r})"
    )


def _run_tui_v1_replay_demo(
    *,
    audio_file_list: list[tuple[str, float]] | None,
    audio_file_playback_mode: AudioFilePlaybackMode = "auto",
    multiturn_session_idle_sec: float | None,
    multiturn_session_end_keyword: str | None,
) -> None:
    """与 ``s2s_tui_agent_app_main.run_tui`` 实质相同，但多一份 ``multiturn_idle_anchor_after_react_turn_only``（不经过 main）。"""
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
        tui_app.call_later(lambda t=line: tui_app.write_log(t))

    def synthetic_assistant_to_chat(text: str) -> None:
        def _apply(t: str = text) -> None:
            tui_app.start_agent_message()
            tui_app.append_agent_delta(t)
            tui_app.finish_agent_message()

        tui_app.call_later(_apply)

    bound_factory = partial(build_v1_runner_bundle, tui_app=tui_app)
    use_files = bool(audio_file_list)
    app = S2STUIAgentApp(
        config=S2SAgentAppConfig(
            mic_mode="space_gate",  
            keyboard_control="external",
            input_source="audio_files" if use_files else "microphone",
            audio_file_list=audio_file_list if use_files else [],
            audio_file_playback_mode=audio_file_playback_mode,
            say_hello=None,
            multiturn_session_idle_sec=multiturn_session_idle_sec,
            multiturn_session_end_keyword=multiturn_session_end_keyword,
            multiturn_idle_anchor_after_react_turn_only=True,
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
    print(
        "[MULTITURN] demo_replay_v1_agent：请在控制台查找前缀为 [MULTITURN] 的日志，"
        "以确认「第N次多轮对话开始/结束」。"
    )
    clear_demo_volc_memory_before_case(case_label=ACTIVE_CASE_NAME)
    audio_file_list = build_audio_file_list(TEXT_TURNS)
    _run_tui_v1_replay_demo(
        audio_file_list=audio_file_list,
        audio_file_playback_mode="auto",
        multiturn_session_idle_sec=20.0,
        multiturn_session_end_keyword="退下",
    )


if __name__ == "__main__":
    main()
