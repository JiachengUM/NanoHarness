from __future__ import annotations

from projects.experiments.s2s.tui import V1TUIEventClient

__all__ = ["V1TUIEventClient"]


if __name__ == "__main__":
    from aicore.models.credentials import ModelName
    from aicore.simulation.user_env.data_source import UserDataMocked
    from aicore.v1.experiments.agent import create_agent
    from aicore.v1.simulation.runner import Runner
    from projects.experiments.s2s.tui import ReActTUIApp
    from projects.mind.toolset import get_default_tools

    agent = create_agent(
        model=ModelName.SEED_1_8_251228,
        tools=get_default_tools("v1_tui_demo"),
    )

    app = ReActTUIApp()

    runner = Runner(
        user_data=UserDataMocked(["请查香港今天的天气，找一家酒店，再推荐一首张学友的歌"]),
        agent=agent,
        client=V1TUIEventClient(app),
    )

    app.set_runner(runner.run)
    app.run()
