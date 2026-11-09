import pytest

from nanoai.task._meta import generate_task, validate_task
from nanoai.task.define import Task
from nanoai.utils.nl_repr import nl_repr

# 一些无意义的符号输入和胡言乱语无法理解的文字，用于测试各个worker的鲁棒性。
QUERIES_NONSENSE = [
    "",
    "1234567890",
    "!@#$%^&*()",
    "123!@#$%^&*()",
    "啊啊啊",
    "123abc!@#",
    "qwertyuiop",
    "★☆♠♣♥♦",
    "hello世界123",
]

# 测试数据
TASK_DESC_BASIC = [
    "请将输入的文本翻译成英文",
    "请总结以下文章的主要内容",
    "请分析这段代码的逻辑",
]

TASK_DESC_COMPLEX = [
    # "请生成一个描述通用任务的数据结构，包括但不限于任务的简要描述、输入和输出要求、约束条件等。",
    "请根据用户的需求描述设计一个概念的数据结构，也就是data schema。",
]


def test_generate_task():
    print("测试generate_task")

    for input in TASK_DESC_BASIC:
        try:
            task = generate_task(input, False)
            print(f"任务简要描述: {input}")
            print(f"生成的任务: {task}")
            print(f"生成的任务描述: {nl_repr(task)}")
        except Exception as e:
            print(f"生成任务错误: {e}")
            continue

        try:
            val_res = validate_task(task)
            print(f"任务验证的结果: {val_res.is_valid}")
            print(f"任务验证的原因: {val_res.reasons}")
        except Exception as e:
            print(f"任务验证错误: {e}")
            continue

    # for input in TASK_DESC_COMPLEX:
    #     task = generate_task(input, True)
    #     print(f"输入: {input}")
    #     print(f"生成的任务: {task}")
    #     val_res = validate_task(task)
    #     print(f"任务验证的结果: {val_res.is_valid}")
    #     print(f"任务验证的原因: {val_res.reasons}")


@pytest.mark.skip(reason="暂时不测试，结构化会出错")
def test_generate_task_complex():
    print("测试generate_task_complex")
    for input in TASK_DESC_COMPLEX:
        try:
            task = generate_task(input, True, structure_strategy="json_schema")
            print(f"输入: {input}")
            print(f"生成的任务: {task}")
            print(f"生成的任务描述: {nl_repr(task)}")
        except Exception as e:
            print(f"生成复杂任务错误: {e}")


def test_validate_task():
    print("测试validate_task")

    # 描述含糊，不合理的Task实例
    INVALID_BRIEF_TASKS = [
        Task(brief="任务"),
        Task(brief="帮忙写个代码", output_criteria=["请使用vscode生成代码。"]),
    ]
    for task in INVALID_BRIEF_TASKS:
        print(f"任务: {task}")
        try:
            val_res = validate_task(task)
            print(f"任务验证的结果: {val_res.is_valid}")
            print(f"任务验证的原因: {val_res.reasons}")
        except Exception as e:
            print(f"任务验证错误: {e}")


def main():
    test_generate_task()
    test_validate_task()


RUN_PYTEST = False


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        main()
