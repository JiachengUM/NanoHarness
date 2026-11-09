"""
自然语言表示模块 (Natural Language Representation)

这个模块提供了将Python对象转换为自然语言表示的功能，主要用于生成人类可读的文本输出。

主要功能：
1. 类型转换：支持基本类型（str, int, float, bool）、容器类型（list, dict）、Pydantic模型等
2. 自定义处理器：通过装饰器注册特定类型的转换处理器
3. 格式化配置：支持列表和字典的格式化参数配置
4. 错误处理：提供详细的错误信息和安全模式

核心函数：
- nl_repr(obj): 将对象转换为自然语言表示
- nl_repr_safe(obj): 安全版本，转换失败时返回str(obj)
- register(type): 注册特定类型的自定义处理器
- set_bool_texts(): 设置布尔值的显示文本
- set_list_params(): 设置列表的格式化参数

使用示例：
    # 基本使用
    nl_repr([1, 2, 3])  # "1. 1\n2. 2\n3. 3"
    nl_repr({"name": "张三", "age": 25})  # "name: 张三\nage: 25"
    
    # 复杂列表示例
    students = ["张三", "李四", "王五"]
    nl_repr(students)  # "1. 张三\n2. 李四\n3. 王五"
    
    # 嵌套列表
    nested_data = [["数学", "语文"], ["英语", "物理"]]
    nl_repr(nested_data)
    # "1. \n1. 数学\n2. 语文\n2. \n1. 英语\n2. 物理"
    
    # 列表格式化配置
    set_list_params(separator="、", numbering="({i}) ", use_numbering=True)
    nl_repr(students)  # "(1) 张三、(2) 李四、(3) 王五"
    
    # 局部参数覆盖
    nl_repr(students, separator=" | ", use_numbering=False)  # "张三 | 李四 | 王五"
    
    # BaseModel示例
    from pydantic import BaseModel, Field
    
    class Student(BaseModel):
        name: str = Field(..., title="姓名")
        age: int = Field(..., title="年龄")
        subjects: list[str] = Field(..., title="科目(共{len_list}门)")
        is_graduated: bool = Field(False, title="是否毕业")
    
    student = Student(
        name="张三", 
        age=20, 
        subjects=["数学", "英语", "物理"],
        is_graduated=False
    )
    nl_repr(student)
    # "姓名: 张三\n年龄: 20\n科目(共3门): \n1. 数学\n2. 英语\n3. 物理\n是否毕业: False"
    
    # 嵌套BaseModel
    class Course(BaseModel):
        title: str = Field(..., title="课程名称")
        teacher: Student = Field(..., title="授课教师")
        students: list[Student] = Field(..., title="学生名单")
    
    course = Course(
        title="Python编程",
        teacher=Student(name="李老师", age=35, subjects=["Python"]),
        students=[student]
    )
    nl_repr(course)
    # "课程名称: Python编程\n授课教师: \n姓名: 李老师\n年龄: 35\n科目(共1门): \n1. Python\n是否毕业: False\n学生名单: \n1. \n姓名: 张三\n年龄: 20\n科目(共3门): \n1. 数学\n2. 英语\n3. 物理\n是否毕业: False"
    
    # 自定义处理器
    @register(MyClass)
    def my_handler(obj):
        return f"自定义: {obj.value}"
    
    # 布尔值文本配置
    set_bool_texts("是", "否")
    nl_repr(True)  # "是"
    nl_repr(False)  # "否"
    
    # 字典格式化
    data = {"用户": "张三", "状态": None, "权限": ["读取", "写入"]}
    nl_repr(data)
    # "用户: 张三\n状态: 无\n权限: \n1. 读取\n2. 写入"

设计特点：
- 基于协议的设计：对象可实现__nl_repr__方法自定义转换
- 类型注册机制：支持为特定类型注册转换处理器
- 递归处理：支持嵌套对象的转换
- 错误追踪：提供详细的错误信息便于调试
- 配置灵活：支持全局和局部参数配置
"""

from typing import Any, Callable, Protocol

from pydantic import BaseModel

__all__ = [
    "nl_repr",
    "nl_repr_safe",
    "set_bool_texts",
    "set_list_params",
    "register",
]


class NLReprHandler(Protocol):
    """nl_repr处理器的协议类型"""

    def __call__(self, obj: Any, **kwargs) -> str:
        """将对象转换为自然语言表示
        
        Args:
            obj: 要转换的对象
            **kwargs: 额外的参数
            
        Returns:
            对象的自然语言表示字符串
        """
        ...


# 类型注册表
_type_registry: dict[type, NLReprHandler] = {}


def register(cls_type: type) -> Callable[[NLReprHandler], NLReprHandler]:
    """注册特定类型的nl_repr处理器装饰器

    Args:
        cls_type: 要注册的类型

    Returns:
        装饰器函数，接受一个处理器函数并返回该函数

    Example:
        @register(MyCustomClass)
        def custom_handler(obj: MyCustomClass, **kwargs) -> str:
            return f"Custom: {obj.value}"
    """

    def decorator(handler: NLReprHandler) -> NLReprHandler:
        _type_registry[cls_type] = handler
        return handler

    return decorator


# 全局bool文本
_bool_true_text = "True"
_bool_false_text = "False"


def register_bool_texts(true_text: str, false_text: str) -> None:
    """注册自定义的bool文本输出。"""
    global _bool_true_text, _bool_false_text
    _bool_true_text = true_text
    _bool_false_text = false_text


def set_bool_texts(true_text: str, false_text: str) -> None:
    """设置自定义的bool文本输出。"""
    global _bool_true_text, _bool_false_text
    _bool_true_text = true_text
    _bool_false_text = false_text


class ListFormatParams:
    """List格式化参数配置类"""

    def __init__(self):
        self.separator: str = "\n"
        self.numbering: str = "{i}. "
        self.use_numbering: bool = True
        self.start: int = 1
        self.prefix: str = ""
        self.suffix: str = ""


# 全局list格式化参数
_default_list_params = ListFormatParams()


def register_list_params(**kwargs) -> None:
    """全局注册list格式化参数。

    参数：
        separator: 列表项之间的分隔符
        numbering: 编号格式模板，使用 {i} 作为占位符
        use_numbering: 是否使用编号
        start: 编号起始值
        prefix: 每个列表项的前缀
        suffix: 每个列表项的后缀
    """
    for key, value in kwargs.items():
        if hasattr(_default_list_params, key):
            setattr(_default_list_params, key, value)
        else:
            raise ValueError(f"未知的list格式化参数: {key}")


def set_list_params(**kwargs) -> None:
    """设置list格式化参数。

    参数：
        separator: 列表项之间的分隔符
        numbering: 编号格式模板，使用 {i} 作为占位符
        use_numbering: 是否使用编号
        start: 编号起始值
        prefix: 每个列表项的前缀
        suffix: 每个列表项的后缀
    """
    for key, value in kwargs.items():
        if hasattr(_default_list_params, key):
            setattr(_default_list_params, key, value)
        else:
            raise ValueError(f"未知的list格式化参数: {key}")


class NLReprError(Exception):
    """nl_repr错误。"""

    def __init__(self, obj: Any, reason: str):
        """obj: 待转换的对象。reason: 错误原因。"""
        self.obj = obj
        self.reason = reason
        # 不在这里生成消息，而是在__str__中动态生成

    def __str__(self) -> str:
        return f"nl_repr转换失败, 输入: {self.obj}，原因: {self.reason}"


def _nl_repr_list(
    lst: list[Any],
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
            item_str = nl_repr(item)
        except NLReprError as e:
            # 补充错误信息，方便调试。
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


def _nl_repr_dict(  # noqa: C901
    d: dict[Any, Any],
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
        >>> _nl_repr_dict({"a": 1, "b": None})
        'a: 1\nb: 无'
        >>> _nl_repr_dict({}, show_empty=True)
        '无'
        >>> _nl_repr_dict({}, show_empty=False)
        ''
    """
    if not isinstance(d, dict):
        raise NLReprError(d, f"输入必须是dict类型，实际为{type(d)}")

    if len(d) == 0:
        return "无" if show_empty else ""

    # 尝试排序，若失败则按原顺序
    try:
        items = sorted(d.items()) if sort_keys else list(d.items())
    except Exception:
        items = list(d.items())

    lines = []
    for k, v in items:
        try:
            k_str = nl_repr(k)
        except NLReprError as e:
            e.reason = f"\n字典key {k!r} 发生错误: \n{e.reason}"
            raise e
        if v is None:
            v_str = none_text
        else:
            try:
                v_str = nl_repr(v)
            except NLReprError as e:
                e.reason = f"\n字典key {k!r} 的value发生错误: \n{e.reason}"
                raise e
        line = f"{key_prefix}{k_str}{key_suffix}{key_value_separator}{value_prefix}{v_str}{value_suffix}"
        lines.append(line)
    return item_separator.join(lines)


# TODO: tuple, set, ...


def _nl_repr_base_model(obj: BaseModel) -> str:
    """将 Pydantic BaseModel 对象转换为自然语言表示
    
    实现原理：
    1. 获取模型的所有字段定义 (model_fields)
    2. 遍历每个字段，跳过 repr=False 的字段和 None 值
    3. 对每个字段值调用 nl_repr() 进行递归转换
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
    # 获取模型的所有字段定义
    fields = obj.__class__.model_fields
    formatted_fields = []
    
    # 遍历每个字段
    for field_name, field_info in fields.items():
        # 跳过 repr=False 的字段（这些字段不参与字符串表示）
        if not field_info.repr:
            continue

        # 获取字段值
        value = getattr(obj, field_name)
        # 跳过 None 值（不显示空字段）
        if value is None:
            continue

        try:
            # 递归调用 nl_repr 处理字段值
            # TODO: 这里可以完全的定制化。检查field_info中是否用registered nl_repr handler。如果有则调用。
            field_value = nl_repr(value)
        except NLReprError as e:
            # 补充错误信息，方便调试
            e.reason = f"\n字段{field_name}发生错误: \n{e.reason}"
            raise e

        # 根据字段是否有 title 决定显示格式
        if field_info.title:
            # 验证 title 是字符串类型
            if not isinstance(field_info.title, str):
                raise NLReprError(
                    field_info.title,
                    f"title must be str, got {type(field_info.title)} with value {field_info.title}",  # noqa
                )

            label_name = field_info.title

            # 特殊处理：如果字段值是列表且 title 包含 {len_list}，替换为实际长度
            if isinstance(value, list):
                # 尝试将label中的{len_list}替换为len(value)。如果失败，则不替换。不会报错。
                label_name = label_name.format(len_list=len(value))

            # 使用 "title: value" 格式
            formatted_fields.append(f"{label_name}: {field_value}")
        else:
            # 没有 title 时只显示值，不显示字段名
            formatted_fields.append(field_value)

    # 用换行符连接所有字段，形成最终的自然语言表示
    return "\n".join(formatted_fields)


def nl_repr(x, **kwargs) -> str:  # noqa: C901
    """将任意obj转换为natural language representation。
    按照如下优先级顺序检查：
    1. 基于对象的nl_repr协议:检查obj是否有__nl_repr__方法。如果有则调用。
    2. 基于类型的注册表: 检查type(obj)是否在类型注册表中。如果有则调用。
    3. 缺省实现: 根据type(obj)调用缺省实现。
    4. 抛出异常: 如果找不到实现。

    不使用singledispatch，而是自己实现基于类型的分派。
    因为第1步的实现这样写很方便。如果放在singledispatch，就必须在每个registed function中写一遍。很麻烦。
    """
    if hasattr(x, "__nl_repr__"):
        method = getattr(x, "__nl_repr__")
        if not callable(method):
            raise NLReprError(x, f"__nl_repr__ must be callable, got {type(method)}")

        # 这里允许抛出异常，让外部捕获。能更早的发现bug。不要try-except。
        result = method(**kwargs)

        if not isinstance(result, str):
            raise NLReprError(x, f"__nl_repr__()必须返回str, 不能是{type(result)}")
        return result

    # 2. 检查类型注册表（精确匹配）
    obj_type = type(x)
    if obj_type in _type_registry:
        handler = _type_registry[obj_type]
        if not callable(handler):
            raise NLReprError(x, f"registered handler must be callable, got {type(handler)}")

        # 这里允许抛出异常，让外部捕获。能更早的发现bug。不要try-except。
        result = handler(x, **kwargs)

        if not isinstance(result, str):
            raise NLReprError(x, f"registered handler must return str, got {type(result)}")
        return result

    if isinstance(x, str):
        return x
    elif isinstance(x, bool):
        return _bool_true_text if x else _bool_false_text
    elif isinstance(x, int):
        return str(x)
    elif isinstance(x, float):
        return str(x)
    elif isinstance(x, list):
        return _nl_repr_list(x, **kwargs)
    elif isinstance(x, dict):
        return _nl_repr_dict(x, **kwargs)
    elif isinstance(x, BaseModel):
        return _nl_repr_base_model(x)
    elif isinstance(x, Exception):
        return f"错误: {type(x).__name__}: {str(x)}"
    else:
        raise NLReprError(x, f"对于类型{type(x)}未实现nl_repr, 值为{x}")


def nl_repr_safe(x, **kwargs) -> str:
    """
    安全版本的nl_repr函数。
    当nl_repr抛出NLReprError时，返回str(x)。
    只捕获NLReprError，其他异常会继续抛出。

    参数：
        x: 待转换的对象
        **kwargs: 传递给nl_repr的参数
    """
    try:
        return nl_repr(x, **kwargs)
    except NLReprError:
        return str(x)
