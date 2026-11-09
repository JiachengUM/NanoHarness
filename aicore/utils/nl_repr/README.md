# nl_repr - 自然语言表示模块

将 Python 对象转换为自然语言表示，生成人类可读的文本输出。

## 功能特性

- **类型转换**：支持基本类型（str, int, float, bool）、容器类型（list, dict）、Pydantic 模型等
- **自定义处理器**：通过装饰器注册特定类型的转换处理器
- **格式化配置**：支持列表和字典的格式化参数配置
- **错误处理**：提供详细的错误信息和安全模式
- **协议支持**：对象可实现 `__nl_repr__` 方法自定义转换
- **递归处理**：支持嵌套对象的转换
- **配置灵活**：支持全局和局部参数配置

## 快速开始

### 基本使用

```python
from aicore.utils.nl_repr import nl_repr

# 基本类型
nl_repr([1, 2, 3])  # "1. 1\n2. 2\n3. 3"
nl_repr({"name": "张三", "age": 25})  # "name: 张三\nage: 25"
nl_repr(True)  # "True"
nl_repr(42)  # "42"
nl_repr(3.14)  # "3.14"
```

### 列表格式化

```python
students = ["张三", "李四", "王五"]
nl_repr(students)
# "1. 张三\n2. 李四\n3. 王五"

# 自定义格式
from aicore.utils.nl_repr import set_list_params
set_list_params(separator="、", numbering="({i}) ", use_numbering=True)
nl_repr(students)
# "(1) 张三、(2) 李四、(3) 王五"

# 局部参数覆盖
nl_repr(students, separator=" | ", use_numbering=False)
# "张三 | 李四 | 王五"

# 空列表
nl_repr([])  # "无"

# 嵌套列表
nested_data = [["数学", "语文"], ["英语", "物理"]]
nl_repr(nested_data)
# "1. \n1. 数学\n2. 语文\n2. \n1. 英语\n2. 物理"
```

### 字典格式化

```python
data = {"用户": "张三", "状态": None, "权限": ["读取", "写入"]}
nl_repr(data)
# "用户: 张三\n状态: 无\n权限: \n1. 读取\n2. 写入"

# 空字典
nl_repr({})  # "无"
```

### Pydantic 模型

```python
from pydantic import BaseModel, Field

class Student(BaseModel):
    name: str = Field(..., title="姓名")
    age: int = Field(..., title="年龄")
    subjects: list[str] = Field(..., title="科目(共{len_list}门)")
    is_graduated: bool = Field(False, title="是否毕业")

student = Student(name="张三", age=20, subjects=["数学", "英语", "物理"], is_graduated=False)
nl_repr(student)
# "姓名: 张三\n年龄: 20\n科目(共3门): \n1. 数学\n2. 英语\n3. 物理\n是否毕业: False"
```

### 嵌套 Pydantic 模型

```python
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
```

### 自定义处理器

```python
from aicore.utils.nl_repr import register

class MyClass:
    def __init__(self, value):
        self.value = value

@register(MyClass)
def my_handler(obj):
    return f"自定义: {obj.value}"

nl_repr(MyClass(42))  # "自定义: 42"
```

### 协议支持

```python
class MyData:
    def __init__(self, data):
        self.data = data

    def __nl_repr__(self, **kwargs):
        return f"数据: {self.data}"

nl_repr(MyData("测试"))  # "数据: 测试"
```

### 布尔值配置

```python
from aicore.utils.nl_repr import set_bool_texts

set_bool_texts("是", "否")
nl_repr(True)  # "是"
nl_repr(False)  # "否"
```

### 异常处理

```python
from aicore.utils.nl_repr import nl_repr

try:
    nl_repr(ValueError("测试错误"))
except Exception as e:
    print(e)  # "错误: ValueError: 测试错误"
```

### 安全模式

```python
from aicore.utils.nl_repr import nl_repr_safe

nl_repr_safe({"key": "value"})  # "key: value"
nl_repr_safe(unsupported_object)  # 返回 str(unsupported_object)
```

## API 参考

### 核心函数

#### `nl_repr(obj, **kwargs) -> str`

将对象转换为自然语言表示。

**参数：**
- `obj`: 待转换的对象
- `**kwargs`: 可选的格式化参数（如 `separator`, `use_numbering` 等）

**返回：**
- 自然语言表示字符串

**异常：**
- `NLReprError`: 当转换失败时抛出

#### `nl_repr_safe(obj, **kwargs) -> str`

安全版本的 `nl_repr`，转换失败时返回 `str(obj)`。

**参数：**
- `obj`: 待转换的对象
- `**kwargs`: 可选的格式化参数

**返回：**
- 自然语言表示字符串，失败时返回 `str(obj)`

### 配置函数

#### `set_bool_texts(true_text: str, false_text: str) -> None`

设置布尔值的显示文本。

**参数：**
- `true_text`: `True` 的显示文本
- `false_text`: `False` 的显示文本

#### `set_list_params(**kwargs) -> None`

设置列表的全局格式化参数。

**参数：**
- `separator`: 列表项之间的分隔符
- `numbering`: 编号格式模板，使用 `{i}` 作为占位符
- `use_numbering`: 是否使用编号
- `start`: 编号起始值
- `prefix`: 每个列表项的前缀
- `suffix`: 每个列表项的后缀

### 装饰器

#### `@register(type)`

注册特定类型的自定义处理器。

**参数：**
- `type`: 要注册的 Python 类型

**示例：**
```python
@register(MyClass)
def my_handler(obj, **kwargs):
    return f"自定义: {obj.value}"
```

## 格式化参数

### 列表格式化参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `separator` | `"\n"` | 列表项之间的分隔符 |
| `numbering` | `"{i}. "` | 编号格式模板，`{i}` 为占位符 |
| `use_numbering` | `True` | 是否使用编号 |
| `start` | `1` | 编号起始值 |
| `prefix` | `""` | 每个列表项的前缀 |
| `suffix` | `""` | 每个列表项的后缀 |

**示例：**
```python
# 自定义编号格式
set_list_params(numbering="第{i}项: ")
nl_repr(["A", "B", "C"])
# "第1项: A\n第2项: B\n第3项: C"

# 添加前后缀
set_list_params(prefix="【", suffix="】")
nl_repr(["A", "B", "C"])
# "1. 【A】\n2. 【B】\n3. 【C】"
```

### 字典格式化参数

字典格式化支持以下参数（通过 `nl_repr` 传递）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `item_separator` | `"\n"` | 每个键值对之间的分隔符 |
| `key_value_separator` | `": "` | 键和值之间的分隔符 |
| `key_prefix` | `""` | 键的前缀 |
| `key_suffix` | `""` | 键的后缀 |
| `value_prefix` | `""` | 值的前缀 |
| `value_suffix` | `""` | 值的后缀 |
| `show_empty` | `True` | 是否显示空字典的提示 |
| `sort_keys` | `True` | 是否对键排序 |
| `none_text` | `"无"` | 当 value 为 None 时的显示文本 |

**示例：**
```python
data = {"name": "张三", "age": 25, "city": "北京"}
nl_repr(data, item_separator=" | ", key_value_separator=" = ")
# "name = 张三 | age = 25 | city = 北京"
```

## 设计特点

### 协议支持

对象可实现 `__nl_repr__` 方法自定义转换逻辑：

```python
class MyData:
    def __nl_repr__(self, **kwargs):
        return f"数据: {self.data}"
```

### 类型注册

支持为特定类型注册转换处理器：

```python
@register(MyClass)
def my_handler(obj, **kwargs):
    return f"自定义: {obj.value}"
```

### 递归处理

支持嵌套对象的自动递归转换：

```python
nested = {"users": [{"name": "张三", "age": 20}, {"name": "李四", "age": 25}]}
nl_repr(nested)
# "users: \n1. name: 张三\nage: 20\n2. name: 李四\nage: 25"
```

### 配置灵活

支持全局配置和局部参数覆盖：

```python
# 全局配置
set_list_params(separator="、")

# 局部覆盖
nl_repr(["A", "B", "C"], separator=" | ")
```

### 错误追踪

提供详细的错误信息便于调试：

```python
try:
    nl_repr(unsupported_object)
except NLReprError as e:
    print(e)  # "nl_repr转换失败, 输入: ...，原因: ..."
```

## 支持的类型

| 类型 | 说明 |
|------|------|
| `str` | 直接返回字符串 |
| `int`, `float` | 转换为字符串 |
| `bool` | 可自定义显示文本 |
| `list` | 支持编号和自定义格式 |
| `dict` | 支持键值对格式化 |
| `BaseModel` | 使用 Field 的 title 作为标签 |
| `Exception` | 显示错误类型和消息 |
| 自定义类型 | 通过 `@register` 或 `__nl_repr__` 支持 |

## 最佳实践

1. **为 Pydantic 模型添加 title**：使用 `Field(title="...")` 为字段添加可读的标签
2. **使用列表长度占位符**：在 title 中使用 `{len_list}` 自动显示列表长度
3. **注册常用类型**：为项目中常用的自定义类型注册处理器
4. **使用安全模式**：在不确定对象类型时使用 `nl_repr_safe`
5. **全局配置 + 局部覆盖**：设置合理的全局默认值，在需要时局部覆盖
