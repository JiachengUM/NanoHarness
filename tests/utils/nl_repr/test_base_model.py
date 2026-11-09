"""BaseModel相关测试模块"""

import pytest
from pydantic import BaseModel, Field

from aicore.utils.nl_repr import nl_repr
from aicore.utils.nl_repr.basemodel import nl_repr_base_model, nl_repr_base_model_type

class User(BaseModel):
    name: str = Field(title="用户名", description="用户名。")
    email: str = Field(title="邮箱", description="邮箱。")
    password: str = Field(title="密码", repr=False)
    age: int = Field(title="年龄", description="年龄。")
    secret_key: str = Field(repr=False)


def test_base_model_repr_field():
    """测试BaseModel中repr=False字段的处理"""

    user = User(name="张三", email="zhangsan@example.com", password="REDACTED", age=25, secret_key="REDACTED")

    result = nl_repr_base_model(user, nl_repr)

    # 验证包含的字段
    assert "用户名: 张三" in result
    assert "邮箱: zhangsan@example.com" in result
    assert "年龄: 25" in result

    # 验证不包含的字段
    assert "密码" not in result
    assert "secret123" not in result
    assert "secret_key" not in result
    assert "very_secret_key" not in result


def test_base_model_repr_field_with_none():
    """测试repr=False的字段即使有值也被跳过"""
    from pydantic import BaseModel, Field

    class Config(BaseModel):
        api_key: str = Field(title="API密钥", repr=False)
        debug: bool = Field(title="调试模式")
        timeout: int = Field(title="超时时间", repr=False)

    config = Config(api_key="REDACTED", debug=True, timeout=30)

    result = nl_repr_base_model(config, nl_repr)

    # 验证只包含debug字段
    assert "调试模式: True" in result
    assert "API密钥" not in result
    assert "REDACTED" not in result
    assert "超时时间" not in result
    assert "30" not in result


def test_base_model_repr_field_mixed():
    """测试混合情况：有些字段repr=False，有些字段有None值"""
    from pydantic import BaseModel, Field

    class MixedModel(BaseModel):
        public_field: str = Field(title="公开字段")
        private_field: str = Field(title="私有字段", repr=False)
        optional_field: str | None = Field(title="可选字段", default=None)
        hidden_optional: str | None = Field(title="隐藏可选", repr=False, default=None)
        visible_field: int = Field(title="可见数字")

    model = MixedModel(
        public_field="公开值",
        private_field="私有值",
        optional_field=None,
        hidden_optional="隐藏值",
        visible_field=42,
    )

    result = nl_repr_base_model(model, nl_repr)

    # 验证包含的字段
    assert "公开字段: 公开值" in result
    assert "可见数字: 42" in result

    # 验证不包含的字段
    assert "私有字段" not in result
    assert "私有值" not in result
    assert "可选字段" not in result
    assert "隐藏可选" not in result
    assert "隐藏值" not in result


def test_base_model_no_title_field():
    """测试没有title的字段应该直接显示字段值而不显示字段名"""
    from pydantic import BaseModel, Field

    class ModelWithNoTitle(BaseModel):
        name: str = Field(title="用户姓名")
        age: int = Field(title="用户年龄")
        description: str
        score: float
        is_active: bool = Field(title="是否激活")

    model = ModelWithNoTitle(
        name="张三",
        age=25,
        description="这是一个测试描述",
        score=95.5,
        is_active=True,
    )

    result = nl_repr_base_model(model, nl_repr)

    # 验证有title的字段显示为 "title: value" 格式
    assert "用户姓名: 张三" in result
    assert "用户年龄: 25" in result
    assert "是否激活: True" in result

    # 验证没有title的字段直接显示值，不显示字段名
    assert "这是一个测试描述" in result
    assert "95.5" in result
    assert "description" not in result
    assert "score" not in result

    # 验证结果格式：应该是换行分隔的格式
    lines = result.split("\n")
    assert len(lines) == 5
    assert "用户姓名: 张三" in lines
    assert "用户年龄: 25" in lines
    assert "这是一个测试描述" in lines
    assert "95.5" in lines
    assert "是否激活: True" in lines


def test_base_model_mixed_title_no_title():
    """测试混合情况：有些字段有title，有些字段没有title"""
    from pydantic import BaseModel, Field

    class MixedTitleModel(BaseModel):
        title_field: str = Field(title="有标题的字段")
        no_title_field: str
        another_title: int = Field(title="另一个标题")
        plain_field: bool

    model = MixedTitleModel(
        title_field="标题字段的值",
        no_title_field="无标题字段的值",
        another_title=42,
        plain_field=True,
    )

    result = nl_repr_base_model(model, nl_repr)

    # 验证有title的字段
    assert "有标题的字段: 标题字段的值" in result
    assert "另一个标题: 42" in result

    # 验证没有title的字段直接显示值
    assert "无标题字段的值" in result
    assert "True" in result

    # 验证不显示字段名
    assert "no_title_field" not in result
    assert "plain_field" not in result


def test_nl_repr_base_model_type():
    """测试BaseModel类型的nl_repr"""
    print(nl_repr_base_model_type(User))


def test_pydantic_demo():
    """演示 nl_repr 对 Pydantic BaseModel 的支持，并测试 __nl_repr__ 协议优先级等边界情况"""
    from pydantic import BaseModel, Field

    # 1. 标准模型
    class User(BaseModel):
        name: str = Field(title="用户姓名")
        age: int = Field(title="用户年龄")
        email: str = Field(title="邮箱地址")
        is_active: bool = Field(title="是否激活")
        tags: list[str] = Field(title="用户标签")
        nickname: str | None = Field(title="昵称", default=None)
        bio: str | None = Field(title="个人简介", default=None)

    class Address(BaseModel):
        city: str = Field(title="城市")
        street: str = Field(title="街道")

    class Company(BaseModel):
        name: str = Field(title="公司名称")
        address: Address = Field(title="公司地址")
        employees: list[User] = Field(title="员工列表")

    print("\n" + "=" * 60)
    print("nl_repr Pydantic BaseModel 演示")
    print("=" * 60)
    user = User(
        name="张三",
        age=25,
        email="zhangsan@example.com",
        is_active=True,
        tags=["开发者", "Python"],
        nickname=None,
        bio="热爱编程的程序员",
    )
    user_with_none = User(
        name="李四", age=30, email="lisi@example.com", is_active=False, tags=["经理"], nickname=None, bio=None
    )
    address = Address(city="北京", street="中关村大街")
    company = Company(
        name="科技公司",
        address=address,
        employees=[
            User(name="李四", age=30, email="lisi@example.com", is_active=True, tags=["经理"]),
            User(name="王五", age=28, email="wangwu@example.com", is_active=False, tags=["设计师"]),
        ],
    )
    print("\n1. 简单用户模型：")
    print(nl_repr_base_model(user, nl_repr))
    print("\n2. 包含 None 值的用户模型：")
    print(nl_repr_base_model(user_with_none, nl_repr))
    print("\n3. 地址模型：")
    print(nl_repr_base_model(address, nl_repr))
    print("\n4. 复杂嵌套模型（公司）：")
    print(nl_repr_base_model(company, nl_repr))

    # 2. __nl_repr__方法返回非str类型，断言报错
    from aicore.utils.nl_repr import NLReprError

    class BadReturnType(BaseModel):
        value: int = 1

        def __nl_repr__(self, **kwargs):
            return 123

    bad = BadReturnType()
    with pytest.raises(NLReprError, match="__nl_repr__.*必须返回str"):
        nl_repr_base_model(bad, nl_repr)

    # 3. 测试 __nl_repr__ 协议优先级
    class CustomUser(BaseModel):
        name: str = Field(title="用户姓名")
        age: int = Field(title="用户年龄")

        def __nl_repr__(self, **kwargs):
            style = kwargs.get("style", "default")
            if style == "formal":
                return f"姓名：{self.name}，年龄：{self.age}岁"
            elif style == "brief":
                return f"{self.name}({self.age})"
            else:
                return f"用户{self.name}，年龄{self.age}岁"

    custom_user = CustomUser(name="张三", age=25)
    print("\n5. 自定义 __nl_repr__ 方法：")
    print("默认样式:", nl_repr(custom_user))
    print("正式样式:", nl_repr(custom_user, style="formal"))
    print("简洁样式:", nl_repr(custom_user, style="brief"))

    # 4. 测试 __nl_repr__ 方法接收参数
    class ParametricObj:
        def __init__(self, name, value):
            self.name = name
            self.value = value

        def __nl_repr__(self, **kwargs):
            prefix = kwargs.get("prefix", "")
            suffix = kwargs.get("suffix", "")
            return f"{prefix}{self.name}: {self.value}{suffix}"

    param_obj = ParametricObj("测试对象", 42)
    print("\n6. 参数化 __nl_repr__ 方法：")
    print("默认:", nl_repr(param_obj))
    print("带前缀:", nl_repr(param_obj, prefix="→ "))
    print("带后缀:", nl_repr(param_obj, suffix=" ←"))
    print("带前缀和后缀:", nl_repr(param_obj, prefix="【", suffix="】"))

    # 5. 测试 __nl_repr__ 方法不存在时的默认行为
    class NoMethodObj:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    no_method_obj = NoMethodObj("无方法对象", 100)
    with pytest.raises(NLReprError, match="对于类型.*NoMethodObj.*未实现nl_repr"):
        nl_repr(no_method_obj)

    print("\n" + "=" * 60)
    print("演示结束")
    print("=" * 60)


RUN_PYTEST = True

def main():
    pass

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        # 可以这么写，是不报错的。
        # f"no format".format(arg = 1)
        main()
