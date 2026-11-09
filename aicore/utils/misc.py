from typing import Any

from pydantic import BaseModel

def safe_update(d1: dict[Any, Any], d2: dict[Any, Any]) -> None:
    """
    # 使用示例
    d1 = {'x': 1}
    d2 = {'y': 2}
    safe_update(d1, d2)  # 成功
    # safe_update(d1, {'x': 3})  # 抛出 KeyError
    """
    common = d1.keys() & d2.keys()
    if common:
        raise KeyError(f"无法更新：存在重复键 {common}")
    d1.update(d2)

def model_to_dict(input_model: BaseModel, recurse: bool = False) -> dict[str, Any]:
    if recurse:
        # model_dump 模式是递归转成 dict
        return input_model.model_dump()

    result: dict[str, Any] = {}
    model_cls = type(input_model)
    for field_name, field_info in model_cls.model_fields.items():
        # 如果定义了别名，就用别名作为 key，否则用变量名
        key = field_info.alias if field_info.alias else field_name
        result[key] = getattr(input_model, field_name)
    return result
