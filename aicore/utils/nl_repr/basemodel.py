from typing import Any, Callable

from pydantic import BaseModel

from aicore.utils.nl_repr.base import NLReprError

__all__ = [
    "nl_repr_base_model",
    "nl_repr_base_model_type",
]


def nl_repr_base_model(obj: BaseModel, nl_repr_func: Callable[[Any], str]) -> str:
    """将 Pydantic BaseModel 对象转换为自然语言表示
    
    实现原理：
    1. 获取模型的所有字段定义 (model_fields)
    2. 遍历每个字段，跳过 repr=False 的字段和 None 值
    3. 对每个字段值调用 nl_repr_func() 进行递归转换
    4. 根据字段是否有 title 属性决定显示格式：
       - 有 title：显示为 "title: value" 格式
       - 无 title：只显示 value
    5. 将所有字段用换行符连接
    
    特殊处理：
    - 如果字段值是列表且 title 包含 {len_list}，会自动替换为列表长度
    - 支持嵌套的 BaseModel 和复杂数据类型
    - 错误处理会提供详细的字段级错误信息
    
    典型实例：
    
    实例1 - 简单模型：
    >>> from pydantic import BaseModel, Field
    >>> class User(BaseModel):
    ...     name: str = Field(..., title="姓名")
    ...     age: int = Field(..., title="年龄")
    ...     email: str | None = Field(None, title="邮箱")
    >>> user = User(name="张三", age=25)
    >>> nl_repr(user)
    '姓名: 张三\n年龄: 25'
    
    实例2 - 复杂模型（包含列表和嵌套）：
    >>> class Course(BaseModel):
    ...     title: str = Field(..., title="课程名称")
    ...     students: list[str] = Field(..., title="学生名单(共{len_list}人)")
    ...     teacher: User = Field(..., title="授课教师")
    >>> course = Course(
    ...     title="Python编程",
    ...     students=["张三", "李四", "王五"],
    ...     teacher=User(name="李老师", age=35)
    ... )
    >>> nl_repr(course)
    '课程名称: Python编程\n学生名单(共3人): \n1. 张三\n2. 李四\n3. 王五\n授课教师: \n姓名: 李老师\n年龄: 35'
    """
    fields = obj.__class__.model_fields
    formatted_fields: list[str] = []
    
    for field_name, field_info in fields.items():
        if not field_info.repr:
            continue

        value = getattr(obj, field_name)
        if value is None:
            continue

        try:
            field_value = nl_repr_func(value)
        except NLReprError as e:
            e.reason = f"\n字段{field_name}发生错误: \n{e.reason}"
            raise e

        

        if field_info.title:
            # TODO: 下面的type error是真的有问题的。需要处理。
            if not isinstance(field_info.title, str): # type: ignore
                raise NLReprError(
                    field_info.title,
                    f"title must be str, got {type(field_info.title)} with value {field_info.title}",
                )

            label_name = field_info.title

            if isinstance(value, list):
                # 这里假设label_name可以被format，包含{len_list}，用于替换为列表长度。这是非常骚包的做法。是有问题的。
                label_name = label_name.format(len_list=len(value))  # type: ignore

            formatted_fields.append(f"{label_name}: {field_value}")
        else:
            formatted_fields.append(field_value)

    return "\n".join(formatted_fields)


def nl_repr_base_model_type(cls: type[BaseModel]) -> str:
    assert issubclass(cls, BaseModel), f"cls必须是BaseModel的子类, 不能是{type(cls)}"

    lines: list[str] = []
    for field_name, field_info in cls.model_fields.items():
        if not field_info.repr:
            continue
        ann = field_info.annotation
        type_str = getattr(ann, "__name__", str(ann)) if ann is not None else "Any"
        lines.append(f"{field_name} ({type_str}): {field_info.description}")

    return "\n".join(lines)
