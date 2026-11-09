import pytest
from pydantic import BaseModel

from aicore.utils._concepts.meta import (
    ArrayType,
    Attribute,
    Concept,
    ObjectType,
    PrimitiveAttribute,
    PrimitiveAttributeType,
    SimpleConcept,
)
from aicore.utils.nl_repr import nl_repr

person_concept = Concept(
    name="Person",
    definition="一个人的基本信息",
    attributes=[
        Attribute(
            name="id",
            type=PrimitiveAttributeType.STRING,
            title="标志符",
            description="唯一标识符",
            is_required=True,
        ),
        Attribute(
            name="name",
            type=PrimitiveAttributeType.STRING,
            title="姓名",
            description="姓名",
            is_required=True,
        ),
        Attribute(
            name="gender",
            type=PrimitiveAttributeType.STRING,
            title="性别",
            description="性别",
            is_required=True,
        ),
        Attribute(
            name="date_of_birth",
            type=PrimitiveAttributeType.STRING,
            title="出生日期",
            description="出生日期",
            is_required=True,
        ),
        Attribute(
            name="contact_info",
            type=PrimitiveAttributeType.STRING,
            title="联系信息",
            description="联系信息",
            is_required=True,
        ),
        Attribute(
            name="education",
            type=PrimitiveAttributeType.STRING,
            title="教育程度",
            description="教育程度",
            is_required=False,
            default_value="unknown",
        ),
        Attribute(
            name="occupation",
            type=PrimitiveAttributeType.STRING,
            title="职业",
            description="职业",
            is_required=False,
            default_value="unknown",
        ),
        Attribute(
            name="marital_status",
            type=PrimitiveAttributeType.STRING,
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
    assert model.model_fields["id"].annotation is str, "id字段应该是str类型"
    assert model.model_fields["name"].annotation is str, "name字段应该是str类型"
    assert model.model_fields["gender"].annotation is str, "gender字段应该是str类型"
    assert model.model_fields["date_of_birth"].annotation is str, "date_of_birth字段应该是str类型"
    assert model.model_fields["contact_info"].annotation is str, "contact_info字段应该是str类型"
    assert model.model_fields["education"].annotation is str, "education字段应该是str类型"
    assert model.model_fields["occupation"].annotation is str, "occupation字段应该是str类型"
    assert model.model_fields["marital_status"].annotation is str, "marital_status字段应该是str类型"

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
        type=PrimitiveAttributeType.STRING,
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
            type=PrimitiveAttributeType.INTEGER,
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


def test_concept_object_type_and_array_type():
    """测试 Concept 支持 ObjectType 嵌套和 ArrayType 数组。"""
    concept = Concept(
        name="SelectedPOIOutput",
        definition="动态裁剪后的 POI 输出",
        attributes=[
            Attribute(
                name="name",
                type=PrimitiveAttributeType.STRING,
                title="名称",
                description="POI名称",
                is_required=True,
            ),
            Attribute(
                name="business",
                type=ObjectType(
                    properties=[
                        Attribute(
                            name="rating",
                            type=PrimitiveAttributeType.STRING,
                            title="评分",
                            description="评分",
                            is_required=True,
                        ),
                        Attribute(
                            name="cost",
                            type=PrimitiveAttributeType.STRING,
                            title="人均消费",
                            description="人均消费",
                            is_required=False,
                        ),
                    ]
                ),
                title="商户信息",
                description="商业扩展信息",
                is_required=True,
            ),
            Attribute(
                name="tags",
                type=ArrayType(item_type=PrimitiveAttributeType.STRING),
                title="标签",
                description="标签列表",
                is_required=False,
                default_value=[],
            ),
        ],
    )

    model = concept.to_pydantic_model()
    item = model(
        name="海底捞",
        business={"rating": "4.8", "cost": "120"},
        tags=["火锅", "可预约"],
    )

    assert getattr(item.business, "rating") == "4.8"
    assert item.tags == ["火锅", "可预约"]
    assert model.model_fields["business"].annotation.__name__ == "Business"


def test_concept_array_of_objects():
    concept = Concept(
        name="SelectedMusicOutput",
        definition="动态裁剪后的音乐输出",
        attributes=[
            Attribute(
                name="songs",
                type=ArrayType(
                    item_type=ObjectType(
                        properties=[
                            Attribute(
                                name="song_name",
                                type=PrimitiveAttributeType.STRING,
                                title="歌曲名",
                                description="歌曲名称",
                                is_required=True,
                            ),
                            Attribute(
                                name="singer_name",
                                type=PrimitiveAttributeType.STRING,
                                title="歌手",
                                description="歌手名称",
                                is_required=True,
                            ),
                        ]
                    )
                ),
                title="歌曲列表",
                description="歌曲列表",
                is_required=True,
            )
        ],
    )

    model = concept.to_pydantic_model()
    item = model(songs=[{"song_name": "夜曲", "singer_name": "周杰伦"}])

    assert item.songs[0].song_name == "夜曲"
    assert item.songs[0].singer_name == "周杰伦"


def test_default_value_validation_for_array_type():
    """ArrayType 的 default_value 必须为 list，且元素类型必须匹配。"""
    # default_value 不是 list → TypeError
    with pytest.raises(TypeError, match="必须为 list"):
        Attribute(
            name="tags",
            type=ArrayType(item_type=PrimitiveAttributeType.STRING),
            title="标签",
            description="标签列表",
            is_required=False,
            default_value="not_a_list",
        )

    # 元素类型不匹配 → TypeError
    with pytest.raises(TypeError, match="default_value"):
        Attribute(
            name="scores",
            type=ArrayType(item_type=PrimitiveAttributeType.INTEGER),
            title="分数",
            description="分数列表",
            is_required=False,
            default_value=[1, "two", 3],
        )

    # 合法的空列表 → 通过
    attr = Attribute(
        name="tags",
        type=ArrayType(item_type=PrimitiveAttributeType.STRING),
        title="标签",
        description="标签列表",
        is_required=False,
        default_value=[],
    )
    assert attr.default_value == []


def test_default_value_validation_for_object_type():
    """ObjectType 的 default_value 必须为 dict，且子属性类型必须匹配。"""
    address_type = ObjectType(
        properties=[
            Attribute(
                name="city",
                type=PrimitiveAttributeType.STRING,
                title="城市",
                description="城市",
                is_required=True,
            ),
            Attribute(
                name="zipcode",
                type=PrimitiveAttributeType.STRING,
                title="邮编",
                description="邮编",
                is_required=False,
                default_value="000000",
            ),
        ]
    )

    # default_value 不是 dict → TypeError
    with pytest.raises(TypeError, match="必须为 dict"):
        Attribute(
            name="address",
            type=address_type,
            title="地址",
            description="地址信息",
            is_required=False,
            default_value="not_a_dict",
        )

    # 缺少必填子属性 → TypeError
    with pytest.raises(TypeError, match="缺少必填子属性"):
        Attribute(
            name="address",
            type=address_type,
            title="地址",
            description="地址信息",
            is_required=False,
            default_value={"zipcode": "100000"},
        )

    # 子属性类型错误 → TypeError
    with pytest.raises(TypeError, match="default_value"):
        Attribute(
            name="address",
            type=address_type,
            title="地址",
            description="地址信息",
            is_required=False,
            default_value={"city": 123},
        )


def test_simple_concept_still_rejects_array_and_object_types():
    with pytest.raises(Exception):
        SimpleConcept(
            name="InvalidSimple",
            definition="简单概念不能包含数组",
            attributes=[
                PrimitiveAttribute(
                    name="tags",
                    type=ArrayType(item_type=PrimitiveAttributeType.STRING),
                    title="标签",
                    description="标签列表",
                    is_required=False,
                )
            ],
        )
    

RUN_PYTEST = False

if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main([__file__, "-v"])
    else:
        # test_nl_repr_runs()
        test_attribute_and_concept_basic()
