import pytest
from pydantic import BaseModel

from nanoai.utils._concept_meta import Attribute, AttributeType, Concept
from nanoai.utils.nl_repr import nl_repr

person_concept = Concept(
    name="Person",
    definition="一个人的基本信息",
    attributes=[
        Attribute(
            name="id",
            type=AttributeType.STRING,
            title="标志符",
            description="唯一标识符",
            is_required=True,
        ),
        Attribute(
            name="name",
            type=AttributeType.STRING,
            title="姓名",
            description="姓名",
            is_required=True,
        ),
        Attribute(
            name="gender",
            type=AttributeType.STRING,
            title="性别",
            description="性别",
            is_required=True,
        ),
        Attribute(
            name="date_of_birth",
            type=AttributeType.STRING,
            title="出生日期",
            description="出生日期",
            is_required=True,
        ),
        Attribute(
            name="contact_info",
            type=AttributeType.STRING,
            title="联系信息",
            description="联系信息",
            is_required=True,
        ),
        Attribute(
            name="education",
            type=AttributeType.STRING,
            title="教育程度",
            description="教育程度",
            is_required=False,
            default_value="unknown",
        ),
        Attribute(
            name="occupation",
            type=AttributeType.STRING,
            title="职业",
            description="职业",
            is_required=False,
            default_value="unknown",
        ),
        Attribute(
            name="marital_status",
            type=AttributeType.STRING,
            title="婚姻状况",
            description="婚姻状况",
            is_required=False,
            default_value="unknown",
        ),
    ],
)


def test_concept_to_pydantic_model_runs():
    """测试Concept.to_pydantic_model方法能否正常运行"""
    model = person_concept.to_pydantic_model()

    # 基本类型检查
    assert issubclass(model, BaseModel)
    assert model.__name__ == "Person"

    # 检查所有必需字段是否存在
    required_fields = ["id", "name", "gender", "date_of_birth", "contact_info"]
    for field_name in required_fields:
        assert field_name in model.model_fields, f"必需字段 {field_name} 不存在"
        field = model.model_fields[field_name]
        assert field.is_required(), f"字段 {field_name} 应该是必需的"

    # 检查可选字段是否存在且设置了默认值
    optional_fields = ["education", "occupation", "marital_status"]
    for field_name in optional_fields:
        assert field_name in model.model_fields, f"可选字段 {field_name} 不存在"
        field = model.model_fields[field_name]
        assert not field.is_required(), f"字段 {field_name} 不应该是必需的"
        assert field.default == "unknown", f"字段 {field_name} 的默认值应该是 'unknown'"

    # 检查字段类型
    assert model.model_fields["id"].annotation == str, "id字段应该是str类型"
    assert model.model_fields["name"].annotation == str, "name字段应该是str类型"
    assert model.model_fields["gender"].annotation == str, "gender字段应该是str类型"
    assert model.model_fields["date_of_birth"].annotation == str, "date_of_birth字段应该是str类型"
    assert model.model_fields["contact_info"].annotation == str, "contact_info字段应该是str类型"
    assert model.model_fields["education"].annotation == str, "education字段应该是str类型"
    assert model.model_fields["occupation"].annotation == str, "occupation字段应该是str类型"
    assert model.model_fields["marital_status"].annotation == str, "marital_status字段应该是str类型"

    # 测试模型实例化
    # 测试必需字段的实例化
    person_data = {
        "id": "12345",
        "name": "张三",
        "gender": "男",
        "date_of_birth": "1990-01-01",
        "contact_info": "13800138000",
    }
    person = model(**person_data)
    # 使用getattr来避免类型检查错误
    assert getattr(person, "id") == "12345"
    assert getattr(person, "name") == "张三"
    assert getattr(person, "gender") == "男"
    assert getattr(person, "date_of_birth") == "1990-01-01"
    assert getattr(person, "contact_info") == "13800138000"

    # 测试可选字段的默认值
    assert getattr(person, "education") == "unknown"
    assert getattr(person, "occupation") == "unknown"
    assert getattr(person, "marital_status") == "unknown"

    # 测试可选字段的自定义值
    person_data_with_optional = {**person_data, "education": "本科", "occupation": "工程师", "marital_status": "未婚"}
    person_with_optional = model(**person_data_with_optional)
    assert getattr(person_with_optional, "education") == "本科"
    assert getattr(person_with_optional, "occupation") == "工程师"
    assert getattr(person_with_optional, "marital_status") == "未婚"

    # 测试缺少必需字段时应该抛出异常
    incomplete_data = {
        "id": "12345",
        "name": "张三",
        # 缺少其他必需字段
    }
    with pytest.raises(Exception):  # 应该抛出验证异常
        model(**incomplete_data)


def test_nl_repr_runs():
    """测试nl_repr能否正常运行"""
    result = nl_repr(person_concept)
    print(result)

    model = person_concept.to_pydantic_model()
    person_data = {
        "id": "12345",
        "name": "张三",
        "gender": "男",
        "date_of_birth": "1990-01-01",
        "contact_info": "13800138000",
    }
    person = model(**person_data)
    result = nl_repr(person)
    print(result)


def test_attribute_and_concept_basic():
    attr_name = Attribute(
        name="name",
        type=AttributeType.STRING,
        title="姓名",
        description="姓名",
        is_required=True,
        default_value = "张三"
    )

    print(attr_name)
    print(nl_repr(attr_name))

    with pytest.raises(Exception):
        # 不能修改Attribute实例
        attr_name.default_value = "李四"

    with pytest.raises(TypeError):
        attr_name = Attribute(
            name="age",
            type=AttributeType.INTEGER,
            title="年龄",
            description="年龄",
            is_required=True,
            default_value = "20"  # 类型错误。应该为int
        )

    concept = Concept(
        name="Person",
        definition="一个人的基本信息",
        attributes=[attr_name]
    )
    print(concept)
    print(nl_repr(concept))

    with pytest.raises(Exception):
        # 不能修改Concept实例
        concept.name = "Person2"
    

RUN_PYTEST = False

if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        # test_nl_repr_runs()
        test_attribute_and_concept_basic()
