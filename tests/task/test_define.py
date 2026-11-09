import json
from typing import Final

import pytest

from nanoai.task.define import Task, TaskCase
from nanoai.utils.nl_repr import nl_repr
from tests.task.task_data import TASK_BASIC_JSON


def test_task_load_json():
    """测试Task从JSON加载"""
    for task_json in TASK_BASIC_JSON:
        task = Task.model_validate_json(json.dumps(task_json))
        print(f"任务: {task}")
        print("---")


def test_task_create():
    """测试Task的创建功能 - 从简单到复杂的用例"""

    # 1. 添加输出标准的文本摘要任务
    task1 = Task(
        brief="对输入文本进行摘要，生成简洁的段落摘要",
        output_criteria=["摘要长度不超过原文的30%", "保留原文的核心信息和关键观点", "使用简洁明了的语言表达"],
    )
    assert len(task1.output_criteria) == 3
    print("============== 1. 添加输出标准的文本摘要任务: ==============")
    print(nl_repr(task1))
    print()

    # 2. 添加输入标准的文本摘要任务
    task2 = Task(
        brief="对输入文本进行摘要，生成简洁的段落摘要",
        output_criteria=["摘要长度不超过原文的30%", "保留原文的核心信息和关键观点", "使用简洁明了的语言表达"],
        input_criteria=["输入文本长度应在100-5000字之间", "文本应包含完整的语义信息", "文本语言应为中文或英文"],
    )
    print("============== 2. 添加输入标准的文本摘要任务: ==============")
    print(nl_repr(task2))
    print()

    # 3. 添加示例的完整文本摘要任务
    task3 = Task(
        brief="对输入文本进行摘要，生成简洁的段落摘要",
        output_criteria=[
            "摘要长度不超过原文的30%",
            "保留原文的核心信息和关键观点",
            "使用简洁明了的语言表达",
            "避免重复和冗余信息",
        ],
        input_criteria=["输入文本长度应在100-5000字之间", "文本应包含完整的语义信息", "文本语言应为中文或英文"],
        examples_pos=[
            TaskCase(
                input="人工智能技术正在快速发展，从机器学习到深度学习，再到现在的生成式AI，技术不断突破。这些技术已经在医疗、教育、金融等多个领域得到应用，为人类生活带来了便利。",
                output="AI技术快速发展，从机器学习到生成式AI不断突破，已在医疗、教育、金融等领域广泛应用。",
            ),
            TaskCase(
                input="气候变化是全球面临的重要挑战。温室气体排放导致地球温度上升，引发极端天气事件增多、海平面上升等问题。各国需要采取积极措施，减少碳排放，发展清洁能源，保护生态环境。",
                output="气候变化是全球重要挑战，温室气体排放导致温度上升，引发极端天气和海平面上升，需要减少碳排放和发展清洁能源。",
            ),
        ],
        examples_neg=[
            TaskCase(
                input="人工智能技术正在快速发展，从机器学习到深度学习，再到现在的生成式AI，技术不断突破。这些技术已经在医疗、教育、金融等多个领域得到应用，为人类生活带来了便利。",
                output="AI很好，技术很厉害，有很多应用。",
                comment="摘要过于简单，丢失了重要的技术细节和具体应用领域信息",
            ),
            TaskCase(
                input="气候变化是全球面临的重要挑战。温室气体排放导致地球温度上升，引发极端天气事件增多、海平面上升等问题。各国需要采取积极措施，减少碳排放，发展清洁能源，保护生态环境。",
                output="气候变化问题很严重，需要大家共同努力解决。",
                comment="摘要过于笼统，缺乏具体的问题描述和解决方案",
            ),
        ],
        detail="本任务要求对输入的文本进行智能摘要，生成简洁而全面的摘要内容。摘要应准确反映原文的核心信息，去除冗余内容，保持逻辑连贯性。适用于新闻文章、学术论文、技术文档等多种文本类型的摘要生成。",
    )

    print("============== 3. 完整的文本摘要任务: ==============")
    print(nl_repr(task3))


def test_task_template():
    """测试Task模板功能"""
    template = Task(brief="生成{style}风格的{format}摘要", template_defaults={"style": "简洁", "format": "段落"})

    # 测试基本实例化
    task1 = template.instantiate()
    assert task1.brief == "生成简洁风格的段落摘要"

    # 测试参数覆盖
    task2 = template.instantiate(style="学术")
    assert task2.brief == "生成学术风格的段落摘要"

    # 测试参数名称提取
    assert template.param_names == {"style", "format"}


def test_task_errors():
    """测试Task的错误处理"""
    template = Task(brief="生成{style}摘要")

    # 测试缺少必需参数
    with pytest.raises(KeyError):
        template.instantiate()

    # 测试无效参数
    with pytest.raises(ValueError):
        template.instantiate(style="学术", extra="无效")


def test_task_inheritance():
    """测试Task继承"""

    class MyTask(Task):
        pass

    template = MyTask(brief="生成{style}摘要", template_defaults={"style": "简洁"})
    task = template.instantiate()
    assert isinstance(task, Task)
    assert task.brief == "生成简洁摘要"


def test_task_frozen():
    """测试Task的不可变性"""
    task = Task(brief="测试brief")
    with pytest.raises(Exception):
        task.brief = "修改"


def main():
    test_task_load_json()
    test_task_create()
    test_task_template()
    test_task_errors()
    test_task_inheritance()
    test_task_frozen()


RUN_PYTEST: Final = True


if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main(["-vs", __file__])
    else:
        test_task_create()
        # main()
