from __future__ import annotations

import asyncio
from typing import Any, Callable

from projects.experiments.s2s.s2s_tui_agent_app import (
    QueueUserDataSource,
    S2SAgentAppConfig,
    S2STUIAgentApp,
)
from projects.experiments.s2s.tui import (
    ReActTUIApp,
    V2_TUI_EVENT_PROFILE,
    build_s2s_event_client,
)
from projects.experiments.s2s.config import (
    AsrExtraModel,
    start_session_req,
    ws_connect_config,
)
from projects.experiments.s2s.realtime_dialog_client import (
    RealtimeDialogClient,
    RealtimeClientOptions,
)
# vad 等待时间，单位毫秒[500ms,50s]
VAD_TIMEOUT = 5000

SYSTEM_PROMPT = """你现在是专业的车载AI车控测试工程师，请围绕【车控、多媒体、导航、端状态、记忆功能、定时任务】六大模块，分别按照简单场景、复杂场景、边缘异常场景三类维度生成用户交互Query指令。 
所有语句开头必须加上唤醒词：你好奔驰 
【语音回复规范】你的回复会被转换为语音播放，因此： 
- 每条指令控制在15字以内，最多不超过30字 
要求： 
1. 覆盖常规指令、模糊指令、方言指令、歧义指令、连续多指令组合； 
2. 指令风格贴近真实车主口语，包含明确指令、模糊指代、趣味/非常规请求； 
3. 分类清晰，每个模块下区分简单、复杂、边缘场景，批量输出可直接用于语音播放测试的语料； 
4. 参考示例：你好奔驰，播放周杰伦的《青花瓷》、你好奔驰，打开车窗。 
约束：一次只回复一句!！！！！其他无关信息不要输出！"""

def build_benz_runner_bundle(
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
        render_active_task_context,
    )

    client = build_s2s_event_client(
        tui_app=tui_app,
        profile=V2_TUI_EVENT_PROFILE,
        on_text_start=on_text_start,
        on_text_delta=on_text_delta,
        on_text_done=on_text_done,
    )
    task_manager = TaskManager()

    agent = create_react_agent_with_task_runner(
        model=ModelName.SEED_1_8_251228,
        tools=[],
        system_prompt=SYSTEM_PROMPT,
        ambient_context_provider=lambda: render_active_task_context(task_manager),
    )

    runner = AgentRunner(
        user_data=user_data,
        agent=agent,
        task_manager=task_manager,
        client=client,
    )
    return runner, agent


async def run_plain(factory: Callable[..., tuple[Any, Any]]) -> None:
    custom_req = start_session_req.model_copy()
    custom_req.asr.extra = AsrExtraModel(
        end_smooth_window_ms=VAD_TIMEOUT,
        enable_custom_vad=True,
    )
    
    client = RealtimeDialogClient(
        options=RealtimeClientOptions(
            ws_config=ws_connect_config,
            session_id=f"benz-demo-{int(asyncio.get_event_loop().time())}",
        ),
        start_session_req=custom_req,
    )
    
    app = S2STUIAgentApp(
        config=S2SAgentAppConfig(mic_mode="continuous", say_hello=None),
        runner_factory=factory,
        realtime_client=client,
    )
    await app.start()


def main() -> None:
    asyncio.run(run_plain(build_benz_runner_bundle))


if __name__ == "__main__":
    main()
