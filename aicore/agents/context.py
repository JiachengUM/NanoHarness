from typing import Any, Self

from pydantic import BaseModel, Field, PrivateAttr, model_validator, ConfigDict

from aicore.models.model_api import ModelAPI, ModelAPIBackend, ModelParams, create_model_api

from aicore.tools import ToolDef, ToolProtocol
# TODO: 这里的BaseTool放松为更加基础的ToolProtocol


# TODO: 去掉这里的bound，也去掉继承，依然发生退化为BaseTool的情况。彻底见了鬼了。
# class ContextBase[TT: BaseTool](BaseModel):
class ContextBase[TT: ToolProtocol[Any]](BaseModel):
    """agent上下文。和state有本质区别。
    上下文是静态的, agent创建之前就存在，通常只读不写。
    TODO: 将来需要支持通过contextvars来传递。
    """

    # model_config = ConfigDict(frozen=True)  # tool_defs不支持frozen, 其它字段也可能被修改。算了。
    # 允许任意类型，方便扩展和继承
    model_config = ConfigDict(arbitrary_types_allowed=True)

    system_prompt: Any = Field(..., description="系统提示词")
    """如此重要的字段，目前的形式是相当原始的。后续可能会改变。类型定义为Any是希望支持任意使用方式。"""

    model_params: ModelParams = Field(..., description="模型配置")

    model_api_backend: ModelAPIBackend = Field(
        default="chat",
        description="模型 API 适配器后端：chat 或 responses",
    )

    react_max_turns: int = Field(default=3, description="react最大轮次")

    # tools: list[Annotated[TT, SerializeAsAny()]] | None = Field(default=None, description="推理工具", exclude=True)
    tools: list[TT] | None = Field(default=None, description="推理工具", exclude=True)
    """SerializeAsAny的作用是，在序列化/验证时, 使用TT的实际类型，不要退化成BaseTool
    但实际上，并没有作用。参考test_misc中的示例。将TT约束为bound=BaseTool，并不应该影响在运行时传入的tools的真实类型。
    但事实上就是会退化为BaseTool。先把bound去掉吧。
    """

    tool_defs: list[ToolDef] | None = Field(
        default=None, description="推理工具定义", init=False
    )
    """完全依赖于tools。只读。本来可以为computed_field，但由于需要被反序列化并用于创建tools，所以实现为现在这样。"""

    _model_api: ModelAPI[Any] | None = PrivateAttr(default=None)

    @property
    def model_api(self) -> ModelAPI[Any]:
        if self._model_api is None:
            self._model_api = create_model_api(
                backend=self.model_api_backend,
                model=self.model_params.model,
            )
        return self._model_api

    @model_validator(mode="after")
    def add_tool_defs(self) -> Self:
        if self.tools:
            self.tool_defs = [
                ToolDef(name=tool.name, description=tool.description)
                for tool in self.tools
            ]

        return self
