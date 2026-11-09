import pytest
import asyncio
from typing import Generator, Type, Any
from unittest.mock import patch
from openai import APITimeoutError

from nanoai.utils.nl_repr import nl_repr
from nanoai.utils._concept_meta import Concept
from nanoai.utils.async_utils import amap_stream, with_param_parse_async

from nanoai.task.define import Task
from nanoai.task.engine import execute_batch, aexecute_batch, LMWorker, DEFAULT_TIMEOUT, aexecute

from tests.task.task_data import TASK_REWRITE, TASK_TRANSLATE

# CONCEPTS = ["疾病", "电商用户", "电影", "零售商品", "电子游戏", "球类运动", "编程语言", "股票", "企业"]
CONCEPTS = ["疾病", "零售商品", "编程语言"]


@pytest.mark.asyncio
@pytest.mark.skip(reason="太慢了，手动测试吧")
async def test_concept_generation():
    '''很好的一个测试用例，同时测了concept generation and amap_stream'''
    print("测试概念生成")

    def params() -> Generator[tuple[tuple[str, Task, Any], dict[str, Any]], None, None]:
        for concept_desc in CONCEPTS:
            yield (concept_desc, Task(
                    brief="请根据输入生成一个概念的定义。",
                    output_criteria=["属性数量不少于5个。越多越好。不超过20个。", "属性的必填字段都为True。"],
                ),
                Concept), {"timeout": 30.0}
    
    gen = await amap_stream(with_param_parse_async(aexecute), params())
    async for result in gen:
        if isinstance(result, Exception):
            print(f"生成概念失败: {result}")
        else:
            print(nl_repr(result))



TEST_INPUTS = [
    "今天天气很好，适合出去散步和锻炼身体，呼吸新鲜空气。",
    "人工智能正在改变我们的生活方式，提高了工作效率。",
    "定期锻炼和均衡饮食有助于预防心血管疾病，提升整体健康水平。",
    "在线教育平台为偏远地区的学生提供了更多优质的学习资源和机会。",
]


def test_execute_batch():
    """测试批量执行功能，对比同步和异步模式的性能。"""
    import time

    print("=== 同步模式测试 ===")
    start_time = time.time()
    batch_res = execute_batch(TEST_INPUTS, [(TASK_REWRITE, str), (TASK_TRANSLATE, str)])
    sync_time = time.time() - start_time
    print(f"同步模式耗时: {sync_time:.2f}秒")
    print("同步模式结果:", batch_res)

    print("\n=== 异步模式测试 ===")
    start_time = time.time()
    batch_res_async = asyncio.run(aexecute_batch(TEST_INPUTS, [(TASK_REWRITE, str), (TASK_TRANSLATE, str)]))
    async_time = time.time() - start_time
    print(f"异步模式耗时: {async_time:.2f}秒")
    print("异步模式结果:", batch_res_async)

    print(f"\n=== 性能对比 ===")
    print(f"同步模式: {sync_time:.2f}秒")
    print(f"异步模式: {async_time:.2f}秒")
    if sync_time > 0 and async_time > 0:
        speedup = sync_time / async_time
        print(f"性能提升: {speedup:.2f}倍")
    else:
        print("性能提升: 无法计算（时间为0）")

    # 验证结果一致性
    assert len(batch_res) == len(batch_res_async), "结果数量不一致"
    assert len(batch_res) == len(TEST_INPUTS), "结果数量与输入数量不一致"
    for i, (sync_row, async_row) in enumerate(zip(batch_res, batch_res_async)):
        assert len(sync_row) == len(async_row), f"第{i}行结果数量不一致"


def test_lmworker_basic():
    """测试LMWorker的基本功能。"""
    # 创建LMWorker实例
    worker = LMWorker(TASK_REWRITE, str)
    
    # 测试同步执行
    result = worker.execute("今天天气很好")
    assert isinstance(result, str), "结果应该是字符串"
    assert len(result) > 0, "结果不应该为空"
    
    print(f"LMWorker同步执行结果: {result}")
    
    # 测试异步执行
    worker_async = LMWorker(TASK_TRANSLATE, str)
    result_async = asyncio.run(worker_async.aexecute("Hello world"))
    assert isinstance(result_async, str), "异步结果应该是字符串"
    assert len(result_async) > 0, "异步结果不应该为空"
    print(f"LMWorker异步执行结果: {result_async}")


def test_lmworker_custom_timeout():
    """测试 LMWorker 使用自定义超时时间"""
    task = Task(brief="测试任务")
    simple_input = "简单输入"
    
    custom_timeout = 30.0
    worker = LMWorker(task, str, timeout=custom_timeout)
    
    # 验证自定义超时时间
    assert worker.timeout == custom_timeout
    
    # Mock execute 函数
    with patch('nanoai.task.engine.execute') as mock_execute:
        mock_execute.return_value.output = "测试结果"
        
        result = worker.execute(simple_input)
        
        # 验证传递了正确的超时参数
        call_args = mock_execute.call_args
        assert call_args[1]['timeout'] == custom_timeout


def test_lmworker_timeout_exception_handling():
    """测试 LMWorker 的超时异常处理"""
    task = Task(brief="测试任务")
    simple_input = "简单输入"
    
    worker = LMWorker(task, str, timeout=5.0)
    
    # Mock execute 函数抛出超时异常
    with patch('nanoai.task.engine.execute') as mock_execute:
        # 直接让 mock 抛出 APITimeoutError
        mock_execute.side_effect = APITimeoutError("Request timed out")
        
        # 应该抛出 APITimeoutError
        with pytest.raises(APITimeoutError):
            worker.execute(simple_input)
        
        # 验证异常信息包含超时时间
        assert "5.0" in worker._status_desc
        assert "任务执行超时" in worker._status_desc


def test_lmworker_status_desc_clearing():
    """测试 LMWorker 状态描述的正确设置"""
    task = Task(brief="测试任务")
    simple_input = "简单输入"
    
    worker = LMWorker(task, str, timeout=6.0)
    
    # 初始状态
    assert not hasattr(worker, '_status_desc')
    
    # Mock execute 函数抛出超时异常
    with patch('nanoai.task.engine.execute') as mock_execute:
        mock_execute.side_effect = APITimeoutError("Test timeout")
        
        with pytest.raises(APITimeoutError):
            worker.execute(simple_input)
        
        # 验证状态描述被正确设置
        assert hasattr(worker, '_status_desc')
        assert "6.0" in worker._status_desc
        assert "任务执行超时" in worker._status_desc
        

RUN_PYTEST = False


def main():
    test_execute_batch()
    test_lmworker_basic() 
    test_lmworker_custom_timeout()
    test_lmworker_timeout_exception_handling()
    test_lmworker_status_desc_clearing()

if __name__ == "__main__":
    if RUN_PYTEST:
        pytest.main([__file__])
    else:
        asyncio.run(test_concept_generation())
    
        # test_execute_batch()
        # main()