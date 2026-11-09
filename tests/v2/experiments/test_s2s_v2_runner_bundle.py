import sys
import types

from aicore.v2.experiments.task_cancel_tool import TaskCancelWorker


class FakeUserData:
    async def __call__(self):
        if False:
            yield ""


def _install_fake_pyaudio(monkeypatch) -> None:
    if "pyaudio" in sys.modules:
        return
    monkeypatch.setitem(
        sys.modules,
        "pyaudio",
        types.SimpleNamespace(
            paInt16=8,
            paFloat32=1,
            PyAudio=object,
        ),
    )


def _install_fake_s2s_ui_modules(monkeypatch) -> None:
    if "projects.experiments.s2s.s2s_tui_agent_app" not in sys.modules:
        monkeypatch.setitem(
            sys.modules,
            "projects.experiments.s2s.s2s_tui_agent_app",
            types.SimpleNamespace(
                AudioFilePlaybackMode=str,
                MicMode=str,
                QueueUserDataSource=FakeUserData,
                S2SAgentAppConfig=object,
                S2STUIAgentApp=object,
            ),
        )

    if "projects.experiments.s2s.tui" not in sys.modules:
        def build_s2s_event_client(**_):
            return lambda event: None

        monkeypatch.setitem(
            sys.modules,
            "projects.experiments.s2s.tui",
            types.SimpleNamespace(
                ReActTUIApp=object,
                V1_TUI_EVENT_PROFILE=object(),
                V2_TUI_EVENT_PROFILE=object(),
                build_s2s_event_client=build_s2s_event_client,
            ),
        )


def test_s2s_v2_runner_bundle_wires_cancel_tool_to_runtime_state(monkeypatch):
    _install_fake_pyaudio(monkeypatch)
    _install_fake_s2s_ui_modules(monkeypatch)
    from projects.experiments.s2s.s2s_tui_agent_app_main import (
        build_v2_runner_bundle,
    )

    runner, agent = build_v2_runner_bundle(
        user_data=FakeUserData(),
        on_text_start=lambda: None,
        on_text_delta=lambda _: None,
        on_text_done=lambda: None,
    )

    tools = agent.context.tools or []
    cancel_tool = next(
        (tool for tool in tools if tool.name == "cancel_task"),
        None,
    )

    assert cancel_tool is not None
    cancel_inner_tool = getattr(cancel_tool, "inner_tool", cancel_tool)
    cancel_worker = getattr(cancel_inner_tool, "worker", None)
    assert isinstance(cancel_worker, TaskCancelWorker)
    assert cancel_worker._task_manager is runner.task_manager
    assert not hasattr(cancel_worker, "_service")
    assert not hasattr(runner, "task_runner")

    assert agent.context.ambient_context_provider is None
    assert "cancel_task" in agent.context.system_prompt
    assert "占位回执" in agent.context.system_prompt
    assert "根据对应占位回执找到 task_id" in agent.context.system_prompt
    assert "call_id" not in agent.context.system_prompt
