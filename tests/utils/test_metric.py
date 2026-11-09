import asyncio
import time

import pytest

from nanoai.task.common import JudgeResult
from nanoai.utils.metric import DatumCriterion


def test_sync_metric():
    """测试同步metric函数"""
    print("=== 测试同步metric函数 ===")

    def sync_metric(text: str) -> bool:
        time.sleep(0.1)  # 模拟计算
        return len(text) > 0

    criterion = DatumCriterion(description="测试同步标准", metric=sync_metric)

    # 测试同步调用
    result = criterion.run("测试文本")
    print(f"同步调用结果: {result}")
    assert result is True

    print("✅ 同步metric测试通过")


@pytest.mark.asyncio
async def test_async_metric():
    """测试异步metric函数"""
    print("\n=== 测试异步metric函数 ===")

    async def async_metric(text: str) -> bool:
        await asyncio.sleep(0.1)  # 模拟异步计算
        return len(text) > 0

    criterion = DatumCriterion(description="测试异步标准", metric=async_metric)

    # 测试异步调用
    result = await criterion.arun("测试文本")
    print(f"异步调用结果: {result}")
    assert result is True

    # 测试同步调用应该抛出异常
    try:
        result = criterion.run("测试文本")
        print("❌ 异步函数同步调用应该抛出异常")
        assert False
    except RuntimeError as e:
        print(f"✅ 正确抛出异常: {e}")

    print("✅ 异步metric测试通过")


def test_mixed_usage():
    """测试混合使用场景"""
    print("\n=== 测试混合使用场景 ===")

    def sync_metric(text: str) -> JudgeResult:
        time.sleep(0.05)
        return JudgeResult(judgment=True, reason="同步评估")

    async def async_metric(text: str) -> JudgeResult:
        await asyncio.sleep(0.05)
        return JudgeResult(judgment=True, reason="异步评估")

    # 创建同步和异步的criterion
    sync_criterion = DatumCriterion(description="同步标准", metric=sync_metric)

    async_criterion = DatumCriterion(description="异步标准", metric=async_metric)

    # 测试同步criterion
    sync_result = sync_criterion.run("测试")
    print(f"同步criterion结果: {sync_result}")
    assert isinstance(sync_result, JudgeResult)

    # 测试异步criterion
    async def test_async():
        async_result = await async_criterion.arun("测试")
        print(f"异步criterion结果: {async_result}")
        assert isinstance(async_result, JudgeResult)

    asyncio.run(test_async())

    print("✅ 混合使用测试通过")


if __name__ == "__main__":
    test_sync_metric()
    asyncio.run(test_async_metric())
    test_mixed_usage()
    print("\n🎉 所有测试通过！DatumCriterion成功支持异步函数。")
