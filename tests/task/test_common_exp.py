import pytest

from nanoai.task.common_exp import answer_with_cot
from tests.task.task_data import QUERIES_BOOL, QUERIES_COT


def test_reason_with_cot():
    print("测试answer_with_cot")
    for input, expected in QUERIES_COT:
        try:
            result = answer_with_cot(input)
            print(f"输入: {input}, 结果: {result}")
        except Exception as e:
            print(f"错误: {e}")
            continue

    for input, _ in QUERIES_BOOL:
        try:
            result = answer_with_cot(input)
            print(f"输入: {input}")
            print(f"答案: {result.answer}")
            print(f"步骤: {result.steps}")
            print("---")
        except Exception as e:
            print(f"错误: {e}")
            continue


def main():
    test_reason_with_cot()


RUN_PYTEST = False


if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        main()
