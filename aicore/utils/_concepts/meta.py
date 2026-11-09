from __future__ import annotations

from enum import StrEnum
from typing import Any, Optional, Tuple, Type, cast

from pydantic import BaseModel, Field, create_model, model_validator, ConfigDict
from pydantic.fields import FieldInfo


# ============================================================================
# 属性类型枚举
# ============================================================================


class PrimitiveAttributeType(StrEnum):
    """原始属性类型枚举

    定义了概念模型中属性可用的基本数据类型。
    使用字符串作为枚举值以便于序列化和反序列化。
    """

    STRING = "string"  # 字符串类型
    INTEGER = "integer"  # 整数类型
    FLOAT = "float"  # 浮点数类型
    BOOLEAN = "boolean"  # 布尔类型

    @classmethod
    def to_type(cls, attr_type: PrimitiveAttributeType) -> Type[Any]:
        _map: dict[PrimitiveAttributeType, Type[Any]] = {
            cls.STRING: str,
            cls.INTEGER: int,
            cls.FLOAT: float,
            cls.BOOLEAN: bool,
        }
        return _map[attr_type]


# ============================================================================
# 属性模型
# ============================================================================


class _AttributeBase(BaseModel):
    """属性基类，包含所有属性共有的字段。"""

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ..., description="属性的名称。英文小写字母，可用下划线、点号(.)和方括号([])连接。"
    )

    title: str = Field(..., description="属性的中文名称，从name翻译而来。", repr=False)
    """它和name的语义完全相同。仅仅为了用于_nl_repr_base_model。"""

    description: str = Field(..., description="属性的描述。")

    is_required: bool = Field(..., description="是否为必需属性。缺省为True。")

    default_value: Any | None = Field(
        default=None, description="属性的缺省值。需要合理，符合常见情况。例如，年龄不能为负数。"
    )

    # TODO: 增加可选字段 typical_values: list[str]


class PrimitiveAttribute(_AttributeBase):
    """简单属性

    只支持原始类型（string, integer, float, boolean），不支持嵌套和数组。
    用于 SimpleConcept。
    """

    type: PrimitiveAttributeType = Field(..., description="属性的类型。")

    @model_validator(mode='after')
    def check_default_value_type(self) -> PrimitiveAttribute:
        if self.default_value is not None:
            if not isinstance(self.default_value, PrimitiveAttributeType.to_type(self.type)):
                raise TypeError(
                    f'default_value({self.default_value})的类型错误。'
                    f'应该为{self.type}:{PrimitiveAttributeType.to_type(self.type)}，'
                    f'但实际为{type(self.default_value)}'
                )
        return self

    def __nl_repr__(self) -> str:
        return f"{self.name}: {self.type}={self.default_value}, 必填: {self.is_required}。{self.description}"

    def to_field(self, enforce_none_type: bool = False) -> Tuple[Type[Any], FieldInfo]:
        """将属性转换为 BaseModel 中的字段。PrimitiveAttribute 只有标量，无嵌套。"""
        if enforce_none_type:
            field_type = Optional[PrimitiveAttributeType.to_type(self.type)]
        else:
            field_type = PrimitiveAttributeType.to_type(self.type)

        field = Field(
            default=... if self.is_required else self.default_value,
            title=self.title,
            description=self.description,
        )

        return field_type, cast(FieldInfo, field)


class Attribute(_AttributeBase):
    """复合属性

    支持原始类型、对象类型和数组类型。
    用于 Concept。

    Attribute 只描述“字段”本身的元数据；结构信息都收敛到 type:
    - PrimitiveAttributeType.STRING  → str
    - ObjectType(properties=[...])    → nested BaseModel
    - ArrayType(item_type=...)        → list[item_type]
    """

    type: ValueType = Field(..., description="属性的类型。")

    @model_validator(mode='after')
    def _validate_invariants(self) -> Attribute:
        """校验 default_value 与 ValueType 是否一致。"""
        if self.default_value is not None:
            _validate_default_value(self.type, self.default_value, path=self.name)

        return self

    def __nl_repr__(self) -> str:
        return f"{self.name}: {self.type}={self.default_value}, 必填: {self.is_required}。{self.description}"

    def to_field(self, enforce_none_type: bool = False) -> Tuple[Type[Any], FieldInfo]:
        """将属性转换为 BaseModel 中的字段。

        委托给模块级 _attribute_to_field()，支持嵌套对象和数组的完整递归构建。
        """
        return _attribute_to_field(self, enforce_none_type)


class ObjectType(BaseModel):
    """对象类型。

    对象类型通过 properties 递归包含 Attribute，从而表达嵌套结构。
    """

    model_config = ConfigDict(frozen=True)

    properties: list[Attribute] = Field(
        ..., description="对象属性列表，用于描述嵌套结构。"
    )


class ArrayType(BaseModel):
    """数组类型。item_type 描述数组元素类型。"""

    model_config = ConfigDict(frozen=True)

    item_type: ValueType = Field(..., description="数组元素类型。")


type ValueType = PrimitiveAttributeType | ObjectType | ArrayType


ObjectType.model_rebuild()
ArrayType.model_rebuild()
Attribute.model_rebuild()


def _value_type_to_python_type(
    value_type: ValueType,
    *,
    model_name: str,
    enforce_none_type: bool,
) -> Type[Any]:
    """递归将 ValueType 转换为 Python/Pydantic 类型。"""
    if isinstance(value_type, PrimitiveAttributeType):
        return PrimitiveAttributeType.to_type(value_type)

    if isinstance(value_type, ObjectType):
        child_fields = {}
        for child in value_type.properties:
            child_type, child_info = _attribute_to_field(child, enforce_none_type)
            child_fields[child.name] = (child_type, child_info)
        return create_model(model_name, **child_fields)  # type: ignore[return-value]

    if isinstance(value_type, ArrayType):
        item_type = _value_type_to_python_type(
            value_type.item_type,
            model_name=model_name,
            enforce_none_type=enforce_none_type,
        )
        return list[item_type]  # type: ignore[return-value, valid-type]

    raise TypeError(f"不支持的 ValueType: {value_type!r}")


def _validate_default_value(value_type: ValueType, value: Any, *, path: str) -> None:
    """严格校验 default_value，避免 Pydantic 默认宽松转换掩盖类型错误。"""
    if isinstance(value_type, PrimitiveAttributeType):
        expected_type = PrimitiveAttributeType.to_type(value_type)
        if not isinstance(value, expected_type):
            raise TypeError(
                f'属性 "{path}": default_value({value})的类型错误。'
                f'应该为{value_type}:{expected_type}，但实际为{type(value)}'
            )
        return

    if isinstance(value_type, ArrayType):
        if not isinstance(value, list):
            raise TypeError(
                f'属性 "{path}": ArrayType 的 default_value 必须为 list，'
                f'但实际为 {type(value)}'
            )
        for index, item in enumerate(value):
            _validate_default_value(
                value_type.item_type,
                item,
                path=f"{path}[{index}]",
            )
        return

    if isinstance(value_type, ObjectType):
        if not isinstance(value, dict):
            raise TypeError(
                f'属性 "{path}": ObjectType 的 default_value 必须为 dict，'
                f'但实际为 {type(value)}'
            )
        for prop in value_type.properties:
            if prop.name in value:
                _validate_default_value(
                    prop.type,
                    value[prop.name],
                    path=f"{path}.{prop.name}",
                )
            elif prop.is_required and prop.default_value is None:
                raise TypeError(
                    f'属性 "{path}": default_value 缺少必填子属性 "{prop.name}"'
                )
        return

    raise TypeError(f"不支持的 ValueType: {value_type!r}")


def _attribute_to_field(
    attr: Attribute, enforce_none_type: bool = False
) -> Tuple[Type[Any], FieldInfo]:
    """递归构建字段定义。统一处理标量、数组、嵌套对象、对象数组。

    这是 Attribute → Pydantic 字段的唯一入口，
    Attribute.to_field() 和 Concept.to_pydantic_model() 均通过此函数构建。
    """
    field_type: Any = _value_type_to_python_type(
        attr.type,
        model_name=attr.name.capitalize(),
        enforce_none_type=enforce_none_type,
    )

    if enforce_none_type:
        field_type = Optional[field_type]

    field = Field(
        default=... if attr.is_required else attr.default_value,
        title=attr.title,
        description=attr.description,
        validate_default=True,
    )
    return field_type, cast(FieldInfo, field)


# ============================================================================
# 概念模型
# ============================================================================


class _ConceptBase(BaseModel):
    """概念基类，包含所有概念共有的字段。"""

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ..., title="概念名称", description="概念的名称。必须是英文，首字母大写，只包含字母、数字和下划线。"
    )
    # TODO: 需要检查合法性。

    definition: str = Field(..., title="定义", description="概念的内涵定义。")


class SimpleConcept(_ConceptBase):
    """简单概念模型

    使用 PrimitiveAttribute（仅原始类型），不支持嵌套结构。
    适用于扁平化的数据描述场景。
    """

    attributes: list[PrimitiveAttribute] = Field(
        ..., title="属性列表(共{len_list}个)", description="概念的属性列表。"
    )

    def to_pydantic_model(self, enforce_none_type: bool = False) -> Type[BaseModel]:
        """构造相应的 pydantic BaseModel。所有字段均为原始类型。"""
        fields = {}
        for attr_def in self.attributes:
            field_type, field_info = attr_def.to_field(enforce_none_type)
            fields[attr_def.name] = (field_type, field_info)

        return create_model(self.name, **fields)  # type: ignore


class Concept(_ConceptBase):
    """复合概念模型

    使用 Attribute，支持 ObjectType 嵌套和 ArrayType 数组。
    适用于需要表达层次化数据结构的场景。
    """

    attributes: list[Attribute] = Field(
        ..., title="属性列表(共{len_list}个)", description="概念的属性列表。"
    )

    def to_pydantic_model(self, enforce_none_type: bool = False) -> Type[BaseModel]:
        """构造相应的 pydantic BaseModel。

        通过 _attribute_to_field() 递归构建，支持嵌套对象和数组。

        enforce_none_type: 是否强制将字段的 type 设置为 Optional[type]。缺省为 False。
        这也是概念上正确的行为。
        问题在于，当该 BaseModel 用于 LLM 的结构化输出时，即使用户未提供信息，
        LLM 都会输出该字段（通常为 0 或者空字符串），这反而不符合用户意图。
        此时如果允许字段的 type 为 None，LLM 的行为反而更为正确。
        为了纠正"字段 type 不应为 None 但被设置为 None"的语义错误，需要利用 is_required。
        如果 is_required 为 True，但字段的值为 None，则可以判断"根据用户的信息构造字段失败"。
        参见 InfoAgent。
        """
        fields = {}
        for attr_def in self.attributes:
            field_type, field_info = _attribute_to_field(attr_def, enforce_none_type)
            fields[attr_def.name] = (field_type, field_info)

        return create_model(self.name, **fields)  # type: ignore
