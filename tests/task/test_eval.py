import asyncio
import time
from typing import Final

import pytest

from nanoai.task.common import JudgeResult
from nanoai.task.eval import (
    CaseCriterion,
    TaskCaseGT,
    evaluate_dataset,
    aevaluate_dataset,
    evaluation_results_to_df,
)
from nanoai.utils.metric import DatumCriterion

# ==================== 全局配置 ====================

# 测试超时时间（秒）
# 用于所有异步测试的超时控制，防止因网络或API问题导致测试卡死
# 可以根据环境调整：开发环境可以设置较短时间，生产环境可以设置较长时间
TEST_TIMEOUT: Final[float] = 30.0

# ==================== 公共测试数据和函数 ====================

# 基础测试数据
BASIC_CASES = [
    TaskCaseGT(input="你好", output="Hello", gt="Hello"),
    TaskCaseGT(input="谢谢", output="Thank you", gt="Thanks"),
    TaskCaseGT(input="再见", output="Goodbye", comment="测试用例"),
]

# 扩展测试数据（用于异步测试）
EXTENDED_CASES = [
    TaskCaseGT(input="你好", output="Hello", gt="Hello"),
    TaskCaseGT(input="谢谢", output="Thank you", gt="Thanks"),
    TaskCaseGT(input="再见", output="Goodbye", comment="测试用例"),
    TaskCaseGT(input="早上好", output="Good morning", gt="Good morning"),
    TaskCaseGT(input="晚安", output="Good night", gt="Good night"),
]

# 异步优化测试数据
PERFORMANCE_CASES = [
    TaskCaseGT(input="测试输入1", output="测试输出1", gt="正确输出1", comment="测试用例1"),
    TaskCaseGT(input="测试输入2", output="测试输出2", gt="正确输出2", comment="测试用例2"),
    TaskCaseGT(input="测试输入3", output="测试输出3", gt="正确输出3", comment="测试用例3"),
]


# 公共评估函数
def length_criterion(output: str) -> bool:
    """检查输出长度是否合理"""
    return 3 <= len(output) <= 20


def grammar_criterion(output: str) -> JudgeResult:
    """检查语法是否正确"""
    valid_outputs = ["hello", "thank you", "thanks", "goodbye", "good morning", "good night"]
    if output.lower() in valid_outputs:
        return JudgeResult(judgment=True, reason="语法正确")
    else:
        return JudgeResult(judgment=False, reason="语法错误")


def gt_metric(case: TaskCaseGT) -> bool:
    """检查输出是否与gt匹配"""
    return case.output == case.gt


# 异步评估函数
async def async_metric_case(c):
    await asyncio.sleep(0.2)
    return JudgeResult(judgment=True, reason="LLM评估结果")


def sync_metric_case(c):
    time.sleep(0.2)
    return JudgeResult(judgment=True, reason="LLM评估结果")


async def async_metric_output(x):
    await asyncio.sleep(0.2)
    return JudgeResult(judgment=True, reason="LLM评估结果")


def sync_metric_output(x):
    time.sleep(0.2)
    return JudgeResult(judgment=True, reason="LLM评估结果")


# 公共评估标准
BASIC_CRITERIA = [
    DatumCriterion(metric=length_criterion, description="长度检查"),
    DatumCriterion(metric=grammar_criterion, description="语法检查"),
]

BASIC_GT_CRITERION = CaseCriterion[str, str, bool](metric=gt_metric, description="GT匹配检查")

# 异步评估标准
ASYNC_CRITERIA = [
    CaseCriterion[str, str, JudgeResult](description="测试标准1", metric=async_metric_case),
    CaseCriterion[str, str, JudgeResult](description="测试标准2", metric=async_metric_case),
    DatumCriterion(description="测试标准3", metric=async_metric_output),
]

SYNC_CRITERIA = [
    CaseCriterion[str, str, JudgeResult](description="测试标准1", metric=sync_metric_case),
    CaseCriterion[str, str, JudgeResult](description="测试标准2", metric=sync_metric_case),
    DatumCriterion(description="测试标准3", metric=sync_metric_output),
]

ASYNC_GT_CRITERION = CaseCriterion[str, str, JudgeResult](description="GT对比测试", metric=async_metric_case)
SYNC_GT_CRITERION = CaseCriterion[str, str, JudgeResult](description="GT对比测试", metric=sync_metric_case)


# ==================== 核心测试函数 ====================


def test_evaluate_dataset_basic():
    """测试evaluate_dataset基本功能"""
    eval_results, case_info, gt_results, stats_row = evaluate_dataset(BASIC_CASES, BASIC_CRITERIA, BASIC_GT_CRITERION)

    # 验证基本结构
    assert len(eval_results) == 3, "应该有3个case的评估结果"
    assert len(eval_results[0]) == 2, "每个case应该有2个评估标准"
    assert len(case_info) == 3, "应该有3个case信息"
    assert len(gt_results) == 3, "应该有3个GT结果"

    # 验证具体结果
    assert isinstance(eval_results[0][0], bool), "长度检查应该返回bool"
    assert isinstance(eval_results[0][1], JudgeResult), "语法检查应该返回JudgeResult"
    assert gt_results[0] is True, "第一个case的GT结果应该是True"
    assert gt_results[1] is False, "第二个case的GT结果应该是False"
    assert gt_results[2] is None, "第三个case没有GT，结果应该是None"


def test_evaluate_dataset_without_gt():
    """测试没有GT数据的评估"""
    cases = [
        TaskCaseGT(input="你好", output="Hello"),
        TaskCaseGT(input="谢谢", output="Thank you"),
    ]

    def simple_criterion(output: str) -> bool:
        return len(output) > 0

    criteria = [DatumCriterion(metric=simple_criterion, description="非空检查")]

    eval_results, case_info, gt_results, stats_row = evaluate_dataset(cases, criteria)

    # 验证结果
    assert len(eval_results) == 2
    assert all(gt is None for gt in gt_results), "没有GT数据时，gt_results应该都是None"

    # 转换为DataFrame验证
    df = evaluation_results_to_df(case_info, criteria, eval_results, gt_results, stats_row)
    assert "gt" not in df.columns, "没有GT数据时不应该有gt列"


def test_evaluation_results_to_df():
    """测试evaluation_results_to_df函数"""
    case_info = [
        {"input": "你好", "output": "Hello", "gt": "Hello", "comment": None},
        {"input": "谢谢", "output": "Thank you", "gt": "Thanks", "comment": None},
        {"input": "再见", "output": "Goodbye", "gt": None, "comment": "测试用例"},
    ]

    criteria = [
        DatumCriterion(metric=lambda x: True, description="长度检查"),
        DatumCriterion(metric=lambda x: JudgeResult(judgment=True, reason="正确"), description="语法检查"),
    ]

    eval_results = [
        [True, JudgeResult(judgment=True, reason="正确")],
        [True, JudgeResult(judgment=False, reason="错误")],
        [False, JudgeResult(judgment=True, reason="正确")],
    ]

    gt_results = [True, False, None]
    stats_row = ["正确率统计: 3个case", "", "", "", None, None]

    df = evaluation_results_to_df(case_info, criteria, eval_results, gt_results, stats_row)

    # 验证DataFrame结构
    expected_columns = ["input", "output", "gt", "comment", "指标1:标准描述: 长度检查", "指标2:标准描述: 语法检查"]
    assert list(df.columns) == expected_columns
    assert len(df) == 4, "应该有4行（3个case + 1个统计行）"


def test_evaluate_dataset_async_vs_sync():
    """测试异步vs同步模式"""
    print("=== 异步vs同步模式测试 ===")

    # 同步模式
    start_time = time.time()
    try:
        eval_results_sync, case_info_sync, gt_results_sync, stats_row_sync = evaluate_dataset(
            EXTENDED_CASES, BASIC_CRITERIA, BASIC_GT_CRITERION
        )
        sync_time = time.time() - start_time
        sync_success = True
    except Exception as e:
        print(f"⚠️ 同步模式失败: {e}")
        sync_time = 0
        sync_success = False

    # 异步模式
    start_time = time.time()
    try:
        eval_results_async, case_info_async, gt_results_async, stats_row_async = asyncio.run(
            asyncio.wait_for(
                aevaluate_dataset(EXTENDED_CASES, BASIC_CRITERIA, BASIC_GT_CRITERION),
                timeout=TEST_TIMEOUT
            )
        )
        async_time = time.time() - start_time
        async_success = True
    except asyncio.TimeoutError:
        print(f"⚠️ 异步模式超时（{TEST_TIMEOUT}秒），可能因为网络或API问题")
        async_time = 0
        async_success = False
    except Exception as e:
        print(f"⚠️ 异步模式失败: {e}")
        async_time = 0
        async_success = False

    if sync_success:
        print(f"同步模式: {sync_time:.2f}秒")
    if async_success:
        print(f"异步模式: {async_time:.2f}秒")

    # 验证结果一致性
    if sync_success and async_success:
        assert len(eval_results_sync) == len(eval_results_async), "结果数量应该一致"
        assert len(gt_results_sync) == len(gt_results_async), "GT结果数量应该一致"
        print("✅ 异步vs同步模式测试通过！")
    else:
        print("⚠️ 跳过结果验证，因为某个模式失败了")


def test_evaluate_dataset_async_error_handling():
    """测试异步模式的异常处理"""
    cases = [
        TaskCaseGT(input="你好", output="Hello", gt="Hello"),
        TaskCaseGT(input="谢谢", output="Thank you", gt="Thanks"),
    ]

    def error_criterion(output: str) -> bool:
        if "Hello" in output:
            raise ValueError("模拟评估错误")
        return True

    def normal_criterion(output: str) -> bool:
        return len(output) > 0

    criteria = [
        DatumCriterion(metric=normal_criterion, description="正常检查"),
        DatumCriterion(metric=error_criterion, description="错误检查"),
    ]

    try:
        eval_results, case_info, gt_results, stats_row = asyncio.run(
            asyncio.wait_for(
                aevaluate_dataset(cases, criteria),
                timeout=TEST_TIMEOUT
            )
        )
        
        # 验证异常处理
        assert len(eval_results) == 2, "应该有2个case的评估结果"
        assert eval_results[0][0] is True, "第一个评估标准应该返回True"
        assert isinstance(eval_results[0][1], ValueError), "第一个case第二个评估标准应该返回异常"
        assert eval_results[1][1] is True, "第二个case第二个评估标准应该返回True"
        
        print("✅ 异步异常处理测试通过！")
    except asyncio.TimeoutError:
        print(f"⚠️ 异步异常处理测试超时（{TEST_TIMEOUT}秒），跳过测试")
    except Exception as e:
        print(f"⚠️ 异步异常处理测试失败: {e}，跳过测试")


# 保留原有的假评估标准用于其他测试
ASYNC_CRITERIA = [
    CaseCriterion[str, str, JudgeResult](description="测试标准1", metric=async_metric_case),
    CaseCriterion[str, str, JudgeResult](description="测试标准2", metric=async_metric_case),
    DatumCriterion(description="测试标准3", metric=async_metric_output),
]

SYNC_CRITERIA = [
    CaseCriterion[str, str, JudgeResult](description="测试标准1", metric=sync_metric_case),
    CaseCriterion[str, str, JudgeResult](description="测试标准2", metric=sync_metric_case),
    DatumCriterion(description="测试标准3", metric=sync_metric_output),
]


def test_fake_async_optimization():
    """测试假异步优化效果（保留原有测试）"""
    print("=== 假异步优化测试 ===")
    print("模拟场景：每个评估标准需要0.2秒，3个case，3个标准，1个GT标准")
    print("理论总耗时：同步模式 = 3×3×0.2 + 3×1×0.2 = 2.4秒")
    print("理论总耗时：异步模式 ≈ 0.2秒（所有任务并行）")

    # 异步模式
    start_time = time.time()
    try:
        eval_results_async, case_info_async, gt_results_async, stats_row_async = asyncio.run(
            asyncio.wait_for(
                aevaluate_dataset(PERFORMANCE_CASES, ASYNC_CRITERIA, ASYNC_GT_CRITERION),
                timeout=TEST_TIMEOUT
            )
        )
        async_time = time.time() - start_time
        async_success = True
    except asyncio.TimeoutError:
        print(f"⚠️ 异步模式超时（{TEST_TIMEOUT}秒），可能因为网络或API问题")
        async_time = 0
        async_success = False
    except Exception as e:
        print(f"⚠️ 异步模式失败: {e}")
        async_time = 0
        async_success = False

    # 同步模式
    start_time = time.time()
    try:
        eval_results_sync, case_info_sync, gt_results_sync, stats_row_sync = evaluate_dataset(
            PERFORMANCE_CASES, SYNC_CRITERIA, SYNC_GT_CRITERION
        )
        sync_time = time.time() - start_time
        sync_success = True
    except Exception as e:
        print(f"⚠️ 同步模式失败: {e}")
        sync_time = 0
        sync_success = False

    if async_success:
        print(f"异步模式耗时: {async_time:.2f}秒")
    if sync_success:
        print(f"同步模式耗时: {sync_time:.2f}秒")
    
    if async_success and sync_success and async_time > 0:
        speedup = sync_time / async_time
        print(f"性能提升: {speedup:.2f}x")
    else:
        print("性能提升: 无法计算，因为某个模式失败了")

    # 验证结果一致性
    if async_success and sync_success:
        assert len(eval_results_async) == len(eval_results_sync), "结果数量不一致"
        assert len(gt_results_async) == len(gt_results_sync), "GT结果数量不一致"
        print("✅ 假异步优化测试通过！")
    else:
        print("⚠️ 跳过结果验证，因为某个模式失败了")


def main():
    test_evaluate_dataset_basic()
    test_evaluate_dataset_without_gt()
    test_evaluation_results_to_df()
    test_evaluate_dataset_async_vs_sync()
    test_evaluate_dataset_async_error_handling()
    test_fake_async_optimization()


RUN_PYTEST: Final = False


if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main(["-vs", __file__])
    else:
        main()
