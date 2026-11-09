from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Sequence
from typing import Any

from aicore.agents.plan.core import astream_plact
from aicore.agents.plan.judge import PlanJudge
from aicore.agents.plan.events import PlActEvent, PlActFinishEvent
from aicore.agents.plan.criterion import KIND_JQ, bind_criterion
from aicore.agents.plan.experiment.plan_schema_v1 import plan_spec_v1
from aicore.agents.plan.plan_spec import PlanSpec
from aicore.events.agent import (
    AgentOutEvent,
    AgentOutTextDeltaEvent,
    AgentOutTextDoneEvent,
    AgentOutTextStartEvent,
)
from aicore.models.credentials import ModelName
from aicore.models.model_api import (
    AssistantMessage,
    ModelAPI,
    ModelMessage,
    SystemMessage,
    UserMessage,
    create_model_api,
)
from aicore.tools import TaskToolProtocolGeneral
from projects.mind.toolset.dag import get_default_tools

type PlActStreamFactory = Callable[..., AsyncGenerator[PlActEvent, None]]
type PlActFrontendEvent = PlActEvent | AgentOutEvent


class PlActFrontendAgent:
    def __init__(
        self,
        *,
        model_api: ModelAPI[Any],
        tools: Sequence[TaskToolProtocolGeneral],
        spec: PlanSpec[Any] = plan_spec_v1,
        max_turns: int = 5,
        plact_stream: PlActStreamFactory = astream_plact,
        judge: PlanJudge | None = None,
    ) -> None:
        self._model_api = model_api
        self._tools = list(tools)
        self._spec = spec
        self._max_turns = max_turns
        self._plact_stream = plact_stream
        self._judge = judge
        self._history: list[ModelMessage] = []

    @property
    def history(self) -> list[ModelMessage]:
        return list(self._history)

    @property
    def tools(self) -> list[TaskToolProtocolGeneral]:
        return list(self._tools)

    async def astream(
        self,
        input: str,
        /,
        **kwargs: Any,
    ) -> AsyncGenerator[PlActFrontendEvent, None]:
        if not isinstance(input, str):
            raise TypeError("PlActFrontendAgent accepts text input only")

        # 判据形态由注入的把控决定（无把控 → jq）；预建的 planning state 必须用同一个形态，
        # 否则提示词要求的判据形态与校验/验收用的形态不一致。
        criterion = self._judge.criterion if self._judge is not None else KIND_JQ
        prompt_spec = bind_criterion(self._spec, criterion)
        planning_state = self._model_api.state_from_history(
            [
                SystemMessage(text=prompt_spec.build_sys_prompt(self._tools)),
                *self._history,
            ]
        )
        answer_state = self._model_api.state_from_history(self._history)
        final_response: str | None = None

        async for event in self._plact_stream(
            input,
            model_api=self._model_api,
            state=answer_state,
            plan_state=planning_state,
            tools=self._tools,
            spec=self._spec,
            max_turns=self._max_turns,
            judge=self._judge,
            **kwargs,
        ):
            yield event
            if isinstance(event, PlActFinishEvent):
                final_response = str(event.response or "")
                yield AgentOutTextStartEvent()
                yield AgentOutTextDeltaEvent(delta=final_response)
                yield AgentOutTextDoneEvent()

        if final_response is not None:
            self._history.extend(
                [
                    UserMessage(text=input),
                    AssistantMessage(text=final_response),
                ]
            )


def create_plact_frontend_agent(
    *,
    chat_id: str,
    model: str = ModelName.SEED_2_0_PRO_260215,
) -> PlActFrontendAgent:
    return PlActFrontendAgent(
        model_api=create_model_api(backend="responses", model=model),
        tools=get_default_tools(chat_id),
    )
