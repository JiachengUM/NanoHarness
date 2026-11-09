from __future__ import annotations

from enum import StrEnum
from typing import Any, Optional, Tuple, Type, assert_never, cast

from pydantic import BaseModel, Field, create_model, model_validator, ConfigDict
from pydantic.fields import FieldInfo

from nanoai.utils.nl_repr import _nl_repr_base_model


class AttributeType(StrEnum):
    """属性类型枚举

    定义了概念模型中属性可用的数据类型。
    使用字符串作为枚举值以便于序列化和反序列化。
    """

    STRING = "string"  # 字符串类型
    INTEGER = "integer"  # 整数类型
    FLOAT = "float"  # 浮点数类型
    BOOLEAN = "boolean"  # 布尔类型

    @classmethod
    def to_type(cls, attr_type: AttributeType) -> Type[Any]:
        if attr_type == cls.STRING:
            return str
        elif attr_type == cls.INTEGER:
            return int
        elif attr_type == cls.FLOAT:
            return float
        elif attr_type == cls.BOOLEAN:
            return bool
        else:
            assert_never(attr_type)


class Attribute(BaseModel):
    """属性模型

    表示概念的一个属性，包含名称、类型、值和其他元数据。
    支持类型验证以确保值与声明的类型匹配。
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ..., description="属性的名称，可以作为程序中的变量名。必须为英文小写字母。可以有下划线连接。不能有其它字符。"
    )

    type: AttributeType = Field(..., description="属性的类型。")

    title: str = Field(..., description="属性的中文名称，从name翻译而来。", repr=False)
    """它和name的语义完全相同。仅仅为了用于_nl_repr_base_model。"""

    description: str = Field(..., description="属性的描述。")

    is_required: bool = Field(..., description="是否为必需属性。缺省为True。")

    # TODO: 如何确保default_value的type跟type一致？
    default_value: Any | None = Field(
        default=None, description="属性的缺省值。需要合理，符合常见情况。例如，年龄不能为负数。"
    )

    # TODO: 增加可选字段 typical_values: list[str]


    @model_validator(mode='after')  # 验证实例
    def check_default_value_type(self) -> Attribute:
        if self.default_value is not None:
            if not isinstance(self.default_value, AttributeType.to_type(self.type)):
                raise TypeError(f'default_value({self.default_value})的类型错误。应该为{self.type}:{AttributeType.to_type(self.type)}，但实际为{type(self.default_value)}')

        return self

    def __nl_repr__(self) -> str:
        # 应该为False。测试不同的nl_repr实现。
        if False:
            return _nl_repr_base_model(self)
        else:
            # 注意，这里没有使用title。
            return f"{self.name}: {self.type}={self.default_value}, 必填: {self.is_required}。{self.description}"

    def to_field(self, enforce_none_type: bool = False) -> Tuple[Type[Any], FieldInfo]:
        """将属性转换为BaeModel中的字段"""
        if enforce_none_type:
            field_type = Optional[AttributeType.to_type(self.type)]
        else:
            field_type = AttributeType.to_type(self.type)

        # 当enforce_none_type=True时，缺省值按说不应该为...，因为不能强制要求模型提供缺省值。这违反了enforce_none_type为True的初衷。
        # 然而，实际中并没有问题。因为，如果用户未提供该字段信息，llm会输出None。这个语义是正确的。
        
        field = Field(
            default=... if self.is_required else self.default_value,
            title=self.title,
            description=self.description,
        )

        return field_type, cast(FieldInfo, field)


class Concept(BaseModel):
    """概念模型。定义了一个概念的元数据，包含名称、定义和一组属性。"""
    
    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ..., title="概念名称", description="概念的名称。必须是英文，首字母大写，只包含字母、数字和下划线。"
    )
    # TODO: 需要检查合法性。

    definition: str = Field(..., title="定义", description="概念的内涵定义。")

    attributes: list[Attribute] = Field(..., title="属性列表(共{len_list}个)", description="概念的属性列表。")
    # TODO: title会被用于_nl_repr_base_model。这个写法还比较脏，但已经可以工作了。也容易泛化。

    # examples: list[str] = Field(default_factory=list, description="概念的几个实例，也就是其外延。")

    def to_pydantic_model(self, enforce_none_type: bool = False) -> Type[BaseModel]:
        """构造相应的pydantic的BaseModel。
        enforce_none_type: 是否强制将字段的type设置为Optional[type]。缺省为False。这也是概念上正确的行为。
        问题在于, 当该BaseModel用于llm的结构化输出时， 即使用户未提供信息, 
        llm都会输出该字段(通常为0或者空字符串)，这反而不符合用户意图。
        此时如果允许字段的type为None, llm的行为反而更为正确。
        为了纠正“字段type不应为None但被设置为None”的语义错误，需要利用is_required。
        如果is_required为True, 但字段的值为None, 则可以判断"根据用户的信息构造字段失败"。参见InfoAgent。
        """
        # 添加属性字段
        fields = {}
        for attr_def in self.attributes:
            field_type, field_info = attr_def.to_field(enforce_none_type)
            fields[attr_def.name] = (field_type, field_info)

        concept_model = create_model(self.name, **fields)

        return concept_model
