"""FakePersonDriver：假人事件驱动器。

职责：
- 接收 FakePersonScriptEvent，解析台词（固定台词 / LLM 自主发挥）
- 产出 FakePersonSpeakOutcome
- 与数据模型 FakePerson 分离：FakePerson 仅持有角色数据，Driver 负责行为

未来扩展（详见 CONTEXT.md §7）：
- 假人动作通过 FakePersonAction discriminated union 扩展
- 当前仅 SPEAK，未来可加入 MANUAL_CONTROL（模拟手动操作车控）等
- 新增动作时在 _speak 同级加 _manual_control 等私有方法，在 drive() 中按 kind 分发
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from projects.experiments.time_travel_auto_test.fake_person.llm_prompt import (
    LLM_SPEAK_DIRECTIVES,
    FakePersonPromptTemplate,
)
from projects.experiments.time_travel_auto_test.fake_person.models import (
    FakePerson,
    FakePersonSpeakOutcome,
    FakePersonSpeakPerformAction,
    format_event_memory,
)

if TYPE_CHECKING:
    from projects.experiments.time_travel_auto_test.script_events.script_event import (
        FakePersonScriptEvent,
    )

try:
    from projects.mind.mem.auto_test_script.langchain_models import doubao_model as _default_model
except ImportError:  # pragma: no cover
    _default_model = None

_STATE_CHECK_UNSUPPORTED_MSG = (
    "假人剧本不支持 state_check：人物 state/intent 为自然语言、不可穷举亦不可可靠结构化；"
    "假人侧预期请用 nl_assertions + Judge 做自然语言断言。"
)

# 假人自主对话开场信号：对标 auto_test 的 VOICE_MODE_OPEN_SIGNAL
LLM_SPEAK_OPEN_SIGNAL = "__LLM_SPEAK_OPEN__"


class FakePersonDriver:
    """假人事件驱动器：消费剧本事件，驱动假人说出台词。

    用法：
        driver = FakePersonDriver(person, model=..., prompt_template=...)
        outcome = await driver.drive(event, session_id=..., car_info=..., ...)
    """

    def __init__(
        self,
        person: FakePerson,
        *,
        model: ChatOpenAI | None = None,
        prompt_template: FakePersonPromptTemplate | None = None,
        external_api_max_retries: int = 5,
    ) -> None:
        self._person = person
        if model is None:
            if _default_model is None:
                raise ValueError("未提供 model，且无法导入默认 doubao_model")
            model = _default_model
        self._model = model
        self._prompt_template = prompt_template or FakePersonPromptTemplate()
        self._external_api_max_retries = external_api_max_retries

        self._checkpointer = InMemorySaver()
        self._agent: CompiledStateGraph | None = None
        self._system_prompt: str = ""
        self._session_id: str | None = None

    async def drive(
        self,
        event: FakePersonScriptEvent,
        *,
        session_id: str,
        start_query: str,
        assistant_last: str = "",
        car_info: str = "无",
        text_script: str = "无",
        case_description: str = "无",
        max_round: int = 8,
        event_at: datetime | None = None,
    ) -> FakePersonSpeakOutcome:
        """执行剧本事件；对外唯一入口。

        未来扩展：新增动作种类时，按 event.action.kind 分发到对应私有方法。
        """
        if event.target != self._person.role_id:
            raise ValueError(
                f"剧本事件 target={event.target!r} 与假人 role_id={self._person.role_id!r} 不匹配",
            )

        action = event.action
        if action.action_type == "state_check":
            raise ValueError(_STATE_CHECK_UNSUPPORTED_MSG)
        if action.action_type != "perform":
            raise ValueError(f"未支持的假人 action_type={action.action_type!r}")

        # 按 kind 分发 perform 动作；当前仅 SPEAK
        if action.kind == "speak":
            return await self._speak(
                action,  # type: ignore[arg-type]
                session_id=session_id,
                assistant_last=assistant_last,
                car_info=car_info,
                start_query=start_query,
                text_script=text_script,
                case_description=case_description,
                max_round=max_round,
            )
        raise ValueError(f"未支持的假人 perform kind={action.kind!r}")

    def _render_system_prompt(
        self,
        *,
        car_info: str,
        start_query: str,
        text_script: str,
        case_description: str,
        max_round: int,
    ) -> str:
        variables = self._build_prompt_variables(
            car_info=car_info,
            start_query=start_query,
            text_script=text_script,
            case_description=case_description,
            max_round=max_round,
        )
        return self._prompt_template.render(variables)

    def _build_prompt_variables(
        self,
        *,
        car_info: str,
        start_query: str,
        text_script: str,
        case_description: str,
        max_round: int,
    ) -> dict[str, Any]:
        p = self._person
        return {
            "profile": p.profile,
            "state": p.state.description if p.state else None,
            "intent": p.intent.description if p.intent else None,
            "event_memory": format_event_memory(p.event_memory),
            "car_info": car_info,
            "text_script": text_script,
            "case_description": case_description,
            "start_query": start_query,
            "llm_speak_directives": LLM_SPEAK_DIRECTIVES if not start_query else "",
            "max_round": max_round,
        }

    async def _speak(
        self,
        action: FakePersonSpeakPerformAction,
        *,
        session_id: str,
        assistant_last: str,
        car_info: str,
        start_query: str,
        text_script: str,
        case_description: str,
        max_round: int,
    ) -> FakePersonSpeakOutcome:
        if not isinstance(action, FakePersonSpeakPerformAction):
            raise TypeError(
                f"kind=speak 时期望 FakePersonSpeakPerformAction，收到 {type(action)!r}",
            )

        args = action.args
        if args.content is not None:
            return FakePersonSpeakOutcome(
                script_content=args.content,
                utterance=args.content,
            )

        utterance = await self._llm_speak(
            assistant_last,
            session_id,
            car_info=car_info,
            start_query=start_query,
            text_script=text_script,
            case_description=case_description,
            max_round=max_round,
        )
        return FakePersonSpeakOutcome(
            script_content=None,
            utterance=utterance,
        )

    async def _llm_speak(
        self,
        assistant_last: str,
        session_id: str,
        *,
        car_info: str,
        start_query: str,
        text_script: str,
        case_description: str,
        max_round: int,
    ) -> str:
        if self._agent is None or self._session_id != session_id:
            self._begin_session(
                session_id,
                car_info=car_info,
                start_query=start_query,
                text_script=text_script,
                case_description=case_description,
                max_round=max_round,
            )

        assert self._agent is not None
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        user_input = assistant_last if assistant_last else LLM_SPEAK_OPEN_SIGNAL
        last_error: Exception | None = None
        attempts = max(1, self._external_api_max_retries + 1)
        for attempt in range(attempts):
            try:
                response = await self._agent.ainvoke(
                    {"messages": [("user", user_input)]},
                    config=config,
                )
                return response["messages"][-1].content
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                await asyncio.sleep(min(2.0 ** attempt, 30.0))
        assert last_error is not None
        raise last_error

    def _compile_agent(self) -> None:
        self._agent = create_agent(
            model=self._model,
            checkpointer=self._checkpointer,
            system_prompt=self._system_prompt,
        )

    def _begin_session(
        self,
        session_id: str,
        *,
        car_info: str,
        start_query: str,
        text_script: str,
        case_description: str,
        max_round: int,
    ) -> None:
        self._session_id = session_id
        self._system_prompt = self._render_system_prompt(
            car_info=car_info,
            start_query=start_query,
            text_script=text_script,
            case_description=case_description,
            max_round=max_round,
        )
        self._compile_agent()