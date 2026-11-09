from typing import Any, Callable

from aicore.utils.nl_repr.base import NLReprError

class ListFormatParams:
    def __init__(self):
        self.separator: str = "\n"
        self.numbering: str = "{i}. "
        self.use_numbering: bool = True
        self.start: int = 1
        self.prefix: str = ""
        self.suffix: str = ""


_default_list_params = ListFormatParams()


def set_list_params(**kwargs) -> None:
    for key, value in kwargs.items():
        if hasattr(_default_list_params, key):
            setattr(_default_list_params, key, value)
        else:
            raise ValueError(f"未知的list格式化参数: {key}")


def register_list_params(**kwargs) -> None:
    for key, value in kwargs.items():
        if hasattr(_default_list_params, key):
            setattr(_default_list_params, key, value)
        else:
            raise ValueError(f"未知的list格式化参数: {key}")


def _nl_repr_list(
    lst: list[Any],
    nl_repr_func: Callable[[Any], str],
    separator: str | None = None,
    numbering: str | None = None,
    use_numbering: bool | None = None,
    start: int | None = None,
    prefix: str | None = None,
    suffix: str | None = None,
) -> str:
    """list类型的自然语言表示，支持全局参数配置和局部参数覆盖。

    全局参数可通过 register_list_params() 设置，局部参数可通过参数传入。
    局部参数优先级高于全局参数。

    参数：
    - separator: 列表项之间的分隔符
    - numbering: 编号格式模板，使用 {i} 作为占位符
    - use_numbering: 是否使用编号
    - start: 编号起始值
    - prefix: 每个列表项的前缀
    - suffix: 每个列表项的后缀

    示例：
    >>> lst = ["apple", "banana", "cherry"]
    >>> nl_repr(lst)
    '\n1. apple\n2. banana\n3. cherry'

    >>> register_list_params(separator="、", numbering="({i}) ")
    >>> nl_repr(lst)
    '1(1) apple、2(2) banana、3(3) cherry'

    >>> nl_repr(lst, separator=" | ")  # 局部覆盖
    '1(1) apple | 2(2) banana | 3(3) cherry'

    >>> nl_repr([])  # 空列表
    '空列表'

    >>> nl_repr([42])  # 单元素列表
    '1. 42'
    """
    assert isinstance(lst, list), f"l必须是list, 不能是{type(lst)}"

    # 合并全局参数和局部参数
    separator = separator if separator is not None else _default_list_params.separator
    numbering = numbering if numbering is not None else _default_list_params.numbering
    use_numbering = use_numbering if use_numbering is not None else _default_list_params.use_numbering
    start = start if start is not None else _default_list_params.start
    prefix = prefix if prefix is not None else _default_list_params.prefix
    suffix = suffix if suffix is not None else _default_list_params.suffix

    if len(lst) == 0:
        return "无"

    # 统一处理所有非空列表（包括单元素的情况）。
    item_strs = []
    for idx, item in enumerate(lst):
        try:
            item_str = nl_repr_func(item)
        except NLReprError as e:
            e.reason = f"\n列表项{idx}发生错误: \n{e.reason}"
            raise e

        if use_numbering:
            item_str = f"{numbering.format(i=idx+start)}{prefix}{item_str}{suffix}"
        else:
            item_str = f"{prefix}{item_str}{suffix}"
        item_strs.append(item_str)

    result = separator.join(item_strs)
    if separator == "\n" and result and len(lst) > 1:
        result = "\n" + result
    return result