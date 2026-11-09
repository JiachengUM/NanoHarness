from typing import Any, Callable

from aicore.utils.nl_repr.base import NLReprError

def _nl_repr_dict(
    d: dict[Any, Any],
    nl_repr_func: Callable[[Any], str],
    item_separator: str = "\n",
    key_value_separator: str = ": ",
    key_prefix: str = "",
    key_suffix: str = "",
    value_prefix: str = "",
    value_suffix: str = "",
    show_empty: bool = True,
    sort_keys: bool = True,
    none_text: str = "无",
) -> str:
    """dict类型的自然语言表示，支持自定义分隔符和前后缀，并支持value为None的情况。

    参数：
        d: 待格式化的字典
        nl_repr_func: 用于递归转换值的函数
        item_separator: 每个键值对之间的分隔符，默认为换行
        key_value_separator: 键和值之间的分隔符，默认为": "
        key_prefix: 键的前缀
        key_suffix: 键的后缀
        value_prefix: 值的前缀
        value_suffix: 值的后缀
        show_empty: 是否显示空字典的提示（如"无"），否则返回空字符串
        sort_keys: 是否对键排序（仅当所有键可比较时有效）
        none_text: 当value为None时的显示文本

    返回：
        字典的自然语言表示字符串

    示例：
        >>> _nl_repr_dict({"a": 1, "b": None}, nl_repr)
        'a: 1\nb: 无'
        >>> _nl_repr_dict({}, nl_repr, show_empty=True)
        '无'
        >>> _nl_repr_dict({}, nl_repr, show_empty=False)
        ''
    """
    if not isinstance(d, dict):
        raise NLReprError(d, f"输入必须是dict类型，实际为{type(d)}")

    if len(d) == 0:
        return "无" if show_empty else ""

    try:
        items = sorted(d.items()) if sort_keys else list(d.items())
    except Exception:
        items = list(d.items())

    lines = []
    for k, v in items:
        try:
            k_str = nl_repr_func(k)
        except NLReprError as e:
            e.reason = f"\n字典key {k!r} 发生错误: \n{e.reason}"
            raise e
        if v is None:
            v_str = none_text
        else:
            try:
                v_str = nl_repr_func(v)
            except NLReprError as e:
                e.reason = f"\n字典key {k!r} 的value发生错误: \n{e.reason}"
                raise e
        line = f"{key_prefix}{k_str}{key_suffix}{key_value_separator}{value_prefix}{v_str}{value_suffix}"
        lines.append(line)
    return item_separator.join(lines)
