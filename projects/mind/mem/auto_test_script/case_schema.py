from typing import Any, Optional, Self

from pydantic import BaseModel, Field, model_validator
from projects.mind.mem.volc_api import Message
from projects.mind.complex_reasoning.task_data.input import DialogueRoundConfig as _RealDialogueRoundConfig

DEFAULT_MEMORY_LIMIT = 10
DEFAULT_MEMORY_TYPES = ["steward_note_book"]
DEFAULT_EVENT_MEMORY_TYPES = "event_v1"
DEFAULT_EVENT_MEMORY_LIMIT = 10
DEFAULT_MAX_ROUND = 8

# 测试用例涉及记忆与模拟车况的上下文context配置可以直接引用这个
class TestCaseWithMemoryContextConfig(BaseModel):
    memory_types: Optional[list[str]] = Field(..., description=f"测试用例所需的记忆类型列表。")
    memory_limit: Optional[int] = Field(...,description=f"测试用例所需的记忆数量限制。")
    event_memory_type: Optional[str] = Field(..., description=f"测试用例所需的事件记忆类型。")
    event_memory_limit: Optional[int] = Field(..., description=f"测试用例所需的事件记忆数量限制")
    profile: str = Field(default="普通的40岁男性中年人。",description="模拟司机的人设文本，默认值为“普通的40岁男性中年人。”")
    vehicle_state: str = Field(default="无",description="车辆状态文本，默认值为“无”")

DialogueRoundConfig = _RealDialogueRoundConfig


def _reject_blank_user_message_contents(
    messages: list[Message],
    *,
    session_index: int,
    list_label: str,
) -> None:
    """role=user 的消息 content 在去空白后须仍有可读文本。"""
    for j, msg in enumerate(messages):
        if (msg.role or "").strip().lower() != "user":
            continue
        if not (msg.content or "").strip():
            loc = f"user_query_lists[{session_index}]"
            if list_label:
                loc += f".{list_label}"
            raise ValueError(
                f"{loc} 第 {j + 1} 条用户消息（role=user）的 content 不能只包含空白字符"
            )
# class DialogueRoundConfig(BaseModel):
#     """TestCase.user_query_lists 的单个元素：对应一次**独立**自动对话会话。"""
#     user_query_list: list[Message] = Field(
#         default_factory=list,
#         description=(
#             "该会话内用户消息列表；执行器仅使用第一条作为冷启动，后续轮次由自动化/FakePerson 生成。"
#             "同一自然对话内的第 2、3…轮用户台词请写在 expected_script 供演员演绎，勿在此罗列。"
#         ),
#     )
#     mock_info: dict[str, Any] = Field(
#         default_factory=dict,
#         description="该次多轮对话生效的mock上下文信息，比如car_info。会覆盖case级context_config中的同名字段。"
#     )
#     mock_time: str | None = Field(
#         default=None,
#         description="该次对话对应的模拟时间，格式为YYYY-MM-DD HH:MM:SS。用于上传记忆时转换时间戳。"
#     )

#     @field_validator("mock_time")
#     @classmethod
#     def validate_mock_time(cls, value: str | None) -> str | None:
#         if value is None:
#             return value
#         datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
#         return value


class TestCase(BaseModel):
    id: str = Field(..., description="测试用例的唯一id标识符")
    case_id: str = Field(..., description="测试用例的name")
    context_config: dict = Field(..., description="测试用例的上下文配置，非常自由，无法确定")
    max_round: int = Field(default=DEFAULT_MAX_ROUND, description=f"最大对话轮数，默认值为{DEFAULT_MAX_ROUND}")
    user_query_lists: list[list[Message] | DialogueRoundConfig] = Field(
        default_factory=list,
        description=(
            "多次「独立会话」列表：每个元素触发一整段自动多轮对话（冷启动取该元素内首条用户消息）。"
            "跨间隔记忆/跨 mock_time 场景才使用多项；单会话内多轮仅靠一项 + expected_script。"
            "元素格式：1) 旧格式 list[Message]；2) DialogueRoundConfig（mock_info/mock_time 按会话）。"
        ),
    )
    expected_script: str = Field(default="无", description="预期的多次多轮对话文本描述，描述你想象中理想的体现本用例正确的预期效果的多次多轮对话情况，供模拟人以及judge来使用以便进行模拟演绎。默认值为空字符串")
    nl_assertion: Optional[list[str]] = Field(..., description="通过标准——自然语言断言——的列表；至少一条非空字符串（全空白视为无效）。由 LLM judge 依据这些标准判定是否通过。")
    code_assertion: Optional[dict] = Field(default=None, description="通过标准——代码断言。可选，一个非常自由的dict，key是待验证的任何变量名比如car_state，value是预期的变量值。用于严格地进行验证。和自然语言断言结合使用。")
    case_description: str = Field(default="无", description="测试用例的综合描述，默认值为空字符串")
    tags: list[str] = Field(default_factory=list, description="测试用例的标签列表，默认值为空列表")

    @model_validator(mode="after")
    def validate_dialogue_rounds_and_nl_assertion(self) -> Self:
        if not self.user_query_lists:
            raise ValueError("user_query_lists 至少需要一项会话（至少一次对话）")

        for i, session in enumerate(self.user_query_lists):
            if isinstance(session, DialogueRoundConfig):
                if not session.user_query_list:
                    raise ValueError(
                        f"user_query_lists[{i}] 的 user_query_list 不能为空，至少需要一条用户消息"
                    )
                _reject_blank_user_message_contents(
                    session.user_query_list,
                    session_index=i,
                    list_label="user_query_list",
                )
            elif isinstance(session, list):
                if len(session) == 0:
                    raise ValueError(
                        f"user_query_lists[{i}] 不能为空列表，至少需要一条用户消息"
                    )
                _reject_blank_user_message_contents(
                    session,
                    session_index=i,
                    list_label="",
                )
            else:
                raise ValueError(f"user_query_lists[{i}] 类型无效: {type(session)!r}")

        if self.nl_assertion is None:
            raise ValueError("nl_assertion 不能为空，至少需要一条自然语言通过标准")
        if not any((s.strip() if isinstance(s, str) else "") for s in self.nl_assertion):
            raise ValueError(
                "nl_assertion 至少需要一条非空的自然语言通过标准（不能全为空字符串或仅有空白）"
            )

        return self


def _minimal_case_json(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "schema-test-id",
        "case_id": "schema-test-case",
        "context_config": {},
        "user_query_lists": [[{"role": "user", "content": "你好"}]],
        "nl_assertion": ["应给出合理回复"],
    }
    base.update(overrides)
    return base


if __name__ == "__main__":
    from pydantic import ValidationError

    TestCase(**_minimal_case_json())

    def _must_fail(**overrides: Any) -> None:
        try:
            TestCase(**_minimal_case_json(**overrides))
        except ValidationError:
            return
        raise AssertionError(f"expected ValidationError for overrides={overrides!r}")

    _must_fail(user_query_lists=[])
    _must_fail(user_query_lists=[[]])
    _must_fail(
        user_query_lists=[{"user_query_list": [], "mock_info": {}}],
    )
    _must_fail(nl_assertion=[])
    _must_fail(nl_assertion=None)
    _must_fail(nl_assertion=["", "   ", "\t"])
    _must_fail(
        user_query_lists=[[{"role": "user", "content": ""}]],
    )
    _must_fail(
        user_query_lists=[[{"role": "user", "content": "   \n\t"}]],
    )
    _must_fail(
        user_query_lists=[
            {"user_query_list": [{"role": "user", "content": " "}], "mock_info": {}},
        ],
    )
