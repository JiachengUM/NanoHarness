from __future__ import annotations

from enum import StrEnum
from typing import Any, Tuple, Type, assert_never, cast

from pydantic import BaseModel, Field, create_model
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

    name: str = Field(
        ..., description="属性的名称，可以作为程序中的变量名。必须为英文小写字母。可以有下划线连接。不能有其它字符。"
    )

    type: AttributeType = Field(..., description="属性的类型。")

    title: str = Field(..., description="属性的中文名称，从name翻译而来。", repr=False)
    """它和name的语义完全相同。仅仅为了用于_nl_repr_base_model。"""

    description: str = Field(..., description="属性的描述。")

    is_required: bool = Field(..., description="是否为必需属性。缺省为True。")

    default_value: Any | None = Field(
        default=None, description="属性的缺省值。需要合理，符合常见情况。例如，年龄不能为负数。"
    )

    # TODO: 增加可选字段 typical_values: list[str]

    def __nl_repr__(self) -> str:
        # 应该为False。测试不同的nl_repr实现。
        if False:
            return _nl_repr_base_model(self)
        else:
            # 注意，这里没有使用title。
            return f"{self.name}: {self.type}={self.default_value}, 必填: {self.is_required}。{self.description}"

    def to_field(self) -> Tuple[Type[Any], FieldInfo]:
        """将属性转换为BaeModel中的字段"""
        field_type = AttributeType.to_type(self.type)

        field = Field(
            default=... if self.is_required else self.default_value,
            title=self.title,
            description=self.description,
        )

        return field_type, cast(FieldInfo, field)


class Concept(BaseModel):
    """概念模型。定义了一个概念的元数据，包含名称、定义和一组属性。"""

    name: str = Field(
        ..., title="概念名称", description="概念的名称。必须是英文，首字母大写，只包含字母、数字和下划线。"
    )
    # TODO: 需要检查合法性。

    definition: str = Field(..., title="定义", description="概念的内涵定义。")

    attributes: list[Attribute] = Field(..., title="属性列表(共{len_list}个)", description="概念的属性列表。")
    # TODO: title会被用于_nl_repr_base_model。这个写法还比较脏，但已经可以工作了。也容易泛化。

    # examples: list[str] = Field(default_factory=list, description="概念的几个实例，也就是其外延。")

    def to_pydantic_model(self) -> Type[BaseModel]:
        """使用pydantic的create_model基于此概念的模型"""
        # 添加属性字段
        fields = {}
        for attr_def in self.attributes:
            field_type, field_info = attr_def.to_field()
            fields[attr_def.name] = (field_type, field_info)

        concept_model = create_model(self.name, **fields)

        return concept_model
