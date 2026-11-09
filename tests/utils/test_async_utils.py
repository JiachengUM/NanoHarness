"""
async_utils 模块测试套件

本模块测试 nanoai.utils.async_utils 中的所有核心功能，包括：

=== 同步功能测试 ===
- test_map_basic_and_complex: 测试同步 map 函数的基本功能、复杂参数解析和错误处理
- test_map_progress_callbacks: 测试 map 函数的进度回调功能
- test_runtime_stats: 测试 RuntimeStats 统计类的各种属性和方法

=== 异步功能测试 ===
- test_amap_basic_and_complex: 测试异步 amap 函数的基本功能、复杂参数解析和错误处理
- test_amap_concurrency_and_progress: 测试 amap 的并发控制和进度回调功能
- test_amap_async_callable_objects: 测试 amap 支持异步可调用对象
- test_amap_class_methods: 测试 amap 支持类方法（lambda、partial、with_param_parse_async）
- test_amap_stream_basic_and_complex: 测试 amap_stream 流式处理的基本功能和复杂参数
- test_amap_stream_concurrency_and_progress: 测试 amap_stream 的并发控制和进度回调
- test_amap_concurrency_benefit: 测试 amap 并发执行相比串行的性能优势

=== 重试机制测试 ===
- test_arepeat_and_pick_success: 测试 arepeat_and_pick 成功场景
- test_arepeat_and_pick_failure: 测试 arepeat_and_pick 失败场景
- test_arepeat_and_pick_partial_success: 测试 arepeat_and_pick 部分成功场景
- test_arepeat_and_pick_parameters: 测试 arepeat_and_pick 参数验证
- test_arepeat_and_pick_pick_methods: 测试 arepeat_and_pick 的结果选择方法
- test_arepeat_and_pick_error_handling: 测试 arepeat_and_pick 错误处理
- test_arepeat_and_pick_async_validation: 测试 arepeat_and_pick 异步函数验证

=== 重试装饰器测试 ===
- test_repeat_decorator_success: 测试 @repeat 装饰器成功场景
- test_repeat_decorator_failure: 测试 @repeat 装饰器失败场景
- test_repeat_decorator_partial_success: 测试 @repeat 装饰器部分成功场景
- test_repeat_decorator_parameters: 测试 @repeat 装饰器参数验证
- test_repeat_decorator_pick_methods: 测试 @repeat 装饰器结果选择方法
- test_repeat_decorator_advanced_features: 测试 @repeat 装饰器高级功能（超时、日志）
- test_repeat_decorator_performance: 测试 @repeat 装饰器性能

=== 工具函数测试 ===
- test_is_async_callable: 测试 _is_async_callable 函数识别异步可调用对象的能力

所有测试用例都包含完整的错误处理、边界条件测试和性能验证。
"""

import pytest
import asyncio

from nanoai.utils.async_utils import map, amap, amap_stream, RuntimeStats, with_param_parse, with_param_parse_async, _is_async_callable, arepeat_and_pick, drepeat_and_pick


def test_map_basic_and_complex():
    """测试 map 基本功能、复杂参数和错误处理"""
    # 基本功能
    def add_one(x: int) -> int:
        return x + 1
    
    results, stats = map(add_one, [0, 1, 2])
    assert results == [1, 2, 3]
    assert stats.success_count == 3
    
    # 复杂参数（通过 unwrap_param）
    def complex_func(x: int, y: int, multiplier: int = 1, offset: int = 0) -> int:
        return (x + y) * multiplier + offset
    
    wrapped_func = with_param_parse(complex_func)
    params = [
        ((1, 2), {"multiplier": 2, "offset": 10}),  # (1+2)*2+10 = 16
        ((3, 4), {"multiplier": 3, "offset": 5}),   # (3+4)*3+5 = 26
        ((5, 6), {"offset": 100}),                  # (5+6)*1+100 = 111
    ]
    results, stats = map(wrapped_func, params)
    assert results == [16, 26, 111]
    assert stats.success_count == 3
    
    # 错误处理
    def divide_by_zero(x: int) -> float:
        if x == 0:
            raise ValueError("Division by zero")
        return 10 / x
    
    results, stats = map(divide_by_zero, [0, 1, 2])
    assert isinstance(results[0], ValueError)
    assert results[1] == 10.0
    assert results[2] == 5.0
    assert stats.success_count == 2
    
    print("✓ test_map_basic_and_complex passed")


def test_map_progress_callbacks():
    """测试 map 的进度回调功能"""
    def task(x: int) -> int:
        return x * 2
    
    params = [i for i in range(3)]
    
    # 测试自定义进度回调
    progress_calls = []
    def progress_callback(completed: int):
        progress_calls.append(completed)
    
    results, stats = map(task, params, progress=progress_callback)
    assert results == [0, 2, 4]
    assert progress_calls == [1, 2, 3]
    
    # 测试 bool 类型进度回调
    results, stats = map(task, params, progress=False)
    assert results == [0, 2, 4]
    
    results, stats = map(task, params, progress=True)
    assert results == [0, 2, 4]
    
    print("✓ test_map_progress_callbacks passed")


def test_runtime_stats():
    """测试 RuntimeStats 类"""
    times = [0.1, 0.2, 0.15, 0.25, 0.05]
    stats = RuntimeStats(times, 4, 0.75)
    
    assert stats.len() == 5
    assert stats.success_count == 4
    assert stats.total_time == 0.75
    assert stats.avg == 0.15
    assert stats.min == 0.05
    assert stats.max == 0.25
    assert stats.std > 0
    
    # 测试打印功能
    try:
        stats.print()
    except Exception as e:
        assert False, f"RuntimeStats.print() failed: {e}"
    
    print("✓ test_runtime_stats passed")


def test_is_async_callable():
    """测试 _is_async_callable 函数"""
    # 普通协程函数
    async def async_func(x: int) -> int:
        return x + 1
    assert _is_async_callable(async_func) == True
    
    # 同步函数
    def sync_func(x: int) -> int:
        return x + 1
    assert _is_async_callable(sync_func) == False
    
    # 异步可调用对象
    class AsyncCallable:
        async def __call__(self, x: int) -> int:
            return x * 2
    assert _is_async_callable(AsyncCallable()) == True
    
    # 同步可调用对象
    class SyncCallable:
        def __call__(self, x: int) -> int:
            return x * 2
    assert _is_async_callable(SyncCallable()) == False
    
    # 非可调用对象
    assert _is_async_callable(42) == False
    assert _is_async_callable("hello") == False
    
    print("✓ test_is_async_callable passed")


@pytest.mark.asyncio
async def test_amap_basic_and_complex():
    """测试 amap 基本功能、复杂参数和错误处理"""
    # 基本功能
    async def add_one(x: int) -> int:
        await asyncio.sleep(0.01)
        return x + 1
    
    results, stats = await amap(add_one, [0, 1, 2])
    assert results == [1, 2, 3]
    assert stats.success_count == 3
    
    # 复杂参数（通过 unwrap_param_async）
    async def complex_async_func(x: int, y: int, multiplier: int = 1, offset: int = 0) -> int:
        await asyncio.sleep(0.01)
        return (x + y) * multiplier + offset
    
    wrapped_func = with_param_parse_async(complex_async_func)
    params = [
        ((1, 2), {"multiplier": 2, "offset": 10}),  # (1+2)*2+10 = 16
        ((3, 4), {"multiplier": 3, "offset": 5}),   # (3+4)*3+5 = 26
        ((5, 6), {"offset": 100}),                  # (5+6)*1+100 = 111
    ]
    results, stats = await amap(wrapped_func, params)
    assert results == [16, 26, 111]
    assert stats.success_count == 3
    
    # 错误处理
    async def divide_by_zero(x: int) -> float:
        await asyncio.sleep(0.01)
        if x == 0:
            raise ValueError("Division by zero")
        return 10 / x
    
    results, stats = await amap(divide_by_zero, [0, 1, 2])
    assert isinstance(results[0], ValueError)
    assert results[1] == 10.0
    assert results[2] == 5.0
    assert stats.success_count == 2
    
    print("✓ test_amap_basic_and_complex passed")


@pytest.mark.asyncio
async def test_amap_concurrency_and_progress():
    """测试 amap 并发控制和进度回调"""
    async def slow_task(x: int) -> int:
        await asyncio.sleep(0.1)
        return x
    
    params = [i for i in range(5)]
    
    # 测试并发控制
    start_time = asyncio.get_event_loop().time()
    results, stats = await amap(slow_task, params, max_concurrent=2)
    end_time = asyncio.get_event_loop().time()
    
    assert results == [0, 1, 2, 3, 4]
    assert stats.success_count == 5
    # 5个任务，并发数为2，应该需要约 0.3 秒（3轮 * 0.1秒）
    assert 0.25 <= (end_time - start_time) <= 0.4
    
    # 测试进度回调
    progress_calls = []
    def progress_callback(completed: int):
        progress_calls.append(completed)
    
    async def task(x: int) -> int:
        await asyncio.sleep(0.01)
        return x
    
    results, stats = await amap(task, [0, 1, 2], progress=progress_callback)
    assert results == [0, 1, 2]
    assert progress_calls == [1, 2, 3]
    
    # 测试 bool 类型进度回调
    results, stats = await amap(task, [0, 1, 2], progress=True)
    assert results == [0, 1, 2]
    
    print("✓ test_amap_concurrency_and_progress passed")


@pytest.mark.asyncio
async def test_amap_async_callable_objects():
    """测试 amap 支持异步可调用对象"""
    # 异步可调用对象
    class AsyncCallable:
        async def __call__(self, x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 3
    
    results, stats = await amap(AsyncCallable(), [0, 1, 2])
    assert results == [0, 3, 6]
    assert stats.success_count == 3
    
    # 测试拒绝同步函数
    def sync_func(x: int) -> int:
        return x + 1
    
    with pytest.raises(AssertionError, match="must be async callable"):
        await amap(sync_func, [0, 1, 2])
    
    print("✓ test_amap_async_callable_objects passed")


@pytest.mark.asyncio
async def test_amap_class_methods():
    """测试 amap 支持类方法"""
    class DataProcessor:
        def __init__(self, base_url: str):
            self.base_url = base_url
        
        async def process_item(self, item_id: int) -> str:
            """异步处理单个数据项"""
            await asyncio.sleep(0.01)
            return f"处理完成: {self.base_url}/item/{item_id}"
    
    processor = DataProcessor("https://api.example.com")
    
    # 方法1: 使用 lambda 包装类方法。TODO 暂时不支持。
    
    # 方法2: 使用 functools.partial
    from functools import partial
    
    results, stats = await amap(
        partial(processor.process_item),
        [10, 20, 30],
        max_concurrent=2
    )
    
    expected_results = [
        "处理完成: https://api.example.com/item/10",
        "处理完成: https://api.example.com/item/20",
        "处理完成: https://api.example.com/item/30"
    ]
    assert results == expected_results
    assert stats.success_count == 3
    
    # 方法3: 使用 with_param_parse_async 处理复杂参数
    class AdvancedProcessor:
        def __init__(self, api_key: str):
            self.api_key = api_key
        
        async def process_with_config(self, item_id: int, config: dict) -> str:
            """需要额外配置的处理方法"""
            await asyncio.sleep(0.01)
            return f"处理 {item_id}，配置: {config}，密钥: {self.api_key[:3]}***"
    
    advanced_processor = AdvancedProcessor("secret_key_123")
    wrapped_method = with_param_parse_async(advanced_processor.process_with_config)
    
    # 使用不同的参数格式
    params = [
        {"item_id": 1, "config": {"mode": "fast"}},
        {"item_id": 2, "config": {"mode": "slow"}},
        (3, {"config": {"mode": "normal"}}),  # 位置参数
    ]
    
    results, stats = await amap(
        wrapped_method,
        params,
        max_concurrent=2
    )
    
    assert len(results) == 3
    assert all("sec***" in result for result in results)  # 检查密钥被正确传递
    assert stats.success_count == 3
    
    print("✓ test_amap_class_methods passed")


@pytest.mark.asyncio
async def test_amap_stream_basic_and_complex():
    """测试 amap_stream 基本功能、复杂参数和错误处理"""
    # 基本功能
    async def square(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * x
    
    gen = await amap_stream(square, [0, 1, 2])
    results = []
    async for result in gen:
        results.append(result)
    
    assert len(results) == 3
    assert set(results) == {0, 1, 4}
    assert all(not isinstance(r, Exception) for r in results)
    
    # 复杂参数
    async def complex_async_func(x: int, y: int, multiplier: int = 1, offset: int = 0) -> int:
        await asyncio.sleep(0.01)
        return (x + y) * multiplier + offset
    
    wrapped_func = with_param_parse_async(complex_async_func)
    params = [
        ((1, 2), {"multiplier": 2, "offset": 10}),  # (1+2)*2+10 = 16
        ((3, 4), {"multiplier": 3, "offset": 5}),   # (3+4)*3+5 = 26
        ((5, 6), {"offset": 100}),                  # (5+6)*1+100 = 111
    ]
    gen = await amap_stream(wrapped_func, params)
    results = []
    async for result in gen:
        results.append(result)
    
    assert len(results) == 3
    assert set(results) == {16, 26, 111}
    assert all(not isinstance(r, Exception) for r in results)
    
    # 错误处理
    async def error_task(x: int) -> int:
        if x == 0:
            raise ValueError("Zero error")
        await asyncio.sleep(0.01)
        return x * 2
    
    gen = await amap_stream(error_task, [0, 1, 2])
    results = []
    async for result in gen:
        results.append(result)
    
    assert len(results) == 3
    exceptions = [r for r in results if isinstance(r, Exception)]
    successes = [r for r in results if not isinstance(r, Exception)]
    
    assert len(exceptions) == 1
    assert len(successes) == 2
    assert isinstance(exceptions[0], ValueError)
    assert set(successes) == {2, 4}
    
    print("✓ test_amap_stream_basic_and_complex passed")


@pytest.mark.asyncio
async def test_amap_stream_concurrency_and_progress():
    """测试 amap_stream 并发控制和进度回调"""
    # 并发控制
    async def slow_task(x: int) -> int:
        await asyncio.sleep(0.1)
        return x
    
    params = [i for i in range(5)]
    
    start_time = asyncio.get_event_loop().time()
    gen = await amap_stream(slow_task, params, max_concurrent=2)
    
    results = []
    async for result in gen:
        results.append(result)
    
    end_time = asyncio.get_event_loop().time()
    
    assert len(results) == 5
    assert set(results) == {0, 1, 2, 3, 4}
    # 5个任务，并发数为2，应该需要约 0.3 秒（3轮 * 0.1秒）
    assert 0.25 <= (end_time - start_time) <= 0.4
    
    # 进度回调
    async def task(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 2
    
    # 测试 bool 类型进度回调
    gen = await amap_stream(task, [0, 1, 2], progress=True)
    results = []
    async for result in gen:
        results.append(result)
    assert set(results) == {0, 2, 4}
    
    # 测试异步可调用对象
    class AsyncCallable:
        async def __call__(self, x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 3
    
    gen = await amap_stream(AsyncCallable(), [0, 1, 2])
    results = []
    async for result in gen:
        results.append(result)
    assert set(results) == {0, 3, 6}
    
    # 测试拒绝同步函数
    def sync_func(x: int) -> int:
        return x * x
    
    with pytest.raises(AssertionError, match="must be async callable"):
        gen = await amap_stream(sync_func, [0, 1, 2]) # type: ignore
    
    print("✓ test_amap_stream_concurrency_and_progress passed")


@pytest.mark.asyncio
async def test_amap_concurrency_benefit():
    """测试 amap 的并发优势"""
    async def io_task(x: int) -> int:
        await asyncio.sleep(0.1)  # 模拟 I/O 操作
        return x * 2
    
    params = [i for i in range(5)]
    
    # 测试并发执行
    start_time = asyncio.get_event_loop().time()
    results, stats = await amap(io_task, params, max_concurrent=5)
    end_time = asyncio.get_event_loop().time()
    
    assert results == [0, 2, 4, 6, 8]
    assert stats.success_count == 5
    
    # 并发执行应该比串行快很多
    execution_time = end_time - start_time
    assert execution_time < 0.2, f"Execution time {execution_time:.2f}s should be much less than 0.5s for concurrent execution"
    
    print("✓ test_amap_concurrency_benefit passed")


# 公共测试工具函数
async def create_simple_task(x: int) -> int:
    """创建简单的异步任务"""
    await asyncio.sleep(0.01)
    return x * 2

async def create_failing_task(x: int) -> int:
    """创建总是失败的异步任务"""
    await asyncio.sleep(0.01)
    raise ValueError("Task failed")

# 全局计数器用于不可靠任务
_unreliable_task_counter = 0

async def create_unreliable_task(x: int, fail_count: int = 1) -> int:
    """创建不可靠的异步任务（前几次失败，后面成功）"""
    global _unreliable_task_counter
    await asyncio.sleep(0.01)
    
    _unreliable_task_counter += 1
    
    if _unreliable_task_counter <= fail_count:
        raise ConnectionError(f"Attempt {_unreliable_task_counter} failed")
    return x * 3

async def create_random_task(x: int) -> int:
    """创建返回随机结果的异步任务"""
    import random
    await asyncio.sleep(0.01)
    return x + random.randint(1, 10)

async def create_string_task(prefix: str) -> str:
    """创建返回随机字符串的异步任务"""
    import random
    await asyncio.sleep(0.01)
    return prefix + str(random.randint(1, 100))


# 公共测试工具函数
async def verify_success_scenario(func, args, kwargs, expected_result, n_repeat=2):
    """验证成功场景的通用函数"""
    result = await func(*args, **kwargs)
    assert result == expected_result
    assert not isinstance(result, Exception)
    return result

async def verify_failure_scenario(func, args, kwargs, expected_exception_type, expected_message, n_repeat=2):
    """验证失败场景的通用函数"""
    with pytest.raises(expected_exception_type, match=expected_message):
        await func(*args, **kwargs)

async def verify_partial_success_scenario(func, args, kwargs, expected_result, n_repeat=3):
    """验证部分成功场景的通用函数"""
    result = await func(*args, **kwargs)
    assert result == expected_result
    assert not isinstance(result, Exception)
    return result


# === arepeat_and_pick 函数测试 ===

@pytest.mark.asyncio
async def test_arepeat_and_pick_success():
    """测试 arepeat_and_pick 成功场景"""
    result = await arepeat_and_pick(create_simple_task, (5,), {})
    assert result == 10
    assert not isinstance(result, Exception)
    
    print("✓ test_arepeat_and_pick_success passed")


@pytest.mark.asyncio
async def test_arepeat_and_pick_failure():
    """测试 arepeat_and_pick 失败场景"""
    with pytest.raises(ValueError, match="Task failed"):
        await arepeat_and_pick(create_failing_task, (1,), {}, n_repeat=2)
    
    print("✓ test_arepeat_and_pick_failure passed")


@pytest.mark.asyncio
async def test_arepeat_and_pick_partial_success():
    """测试 arepeat_and_pick 部分成功场景"""
    global _unreliable_task_counter
    _unreliable_task_counter = 0  # 重置计数器
    result = await arepeat_and_pick(create_unreliable_task, (4,), {}, n_repeat=3)
    assert result == 12
    assert not isinstance(result, Exception)
    
    print("✓ test_arepeat_and_pick_partial_success passed")


@pytest.mark.asyncio
async def test_arepeat_and_pick_parameters():
    """测试 arepeat_and_pick 参数验证"""
    # 测试不同的 n_repeat 值
    result = await arepeat_and_pick(create_simple_task, (1,), {}, n_repeat=1)
    assert result == 2
    
    result = await arepeat_and_pick(create_simple_task, (2,), {}, n_repeat=5)
    assert result == 4
    
    # 测试复杂参数传递
    async def complex_task(x: int, y: int, multiplier: int = 1, offset: int = 0) -> int:
        await asyncio.sleep(0.01)
        return (x + y) * multiplier + offset
    
    result = await arepeat_and_pick(
        complex_task, 
        (1, 2), 
        {"multiplier": 3, "offset": 10}, 
        n_repeat=2
    )
    assert result == 19
    
    print("✓ test_arepeat_and_pick_parameters passed")


@pytest.mark.asyncio
async def test_arepeat_and_pick_pick_methods():
    """测试 arepeat_and_pick pick 方法"""
    # 测试 "first" 选择
    result = await arepeat_and_pick(create_simple_task, (5,), {}, n_repeat=3, pick="first")
    assert result == 10
    
    # 测试自定义选择函数
    def pick_max(results: list[int]) -> int:
        return max(results)
    
    result = await arepeat_and_pick(create_random_task, (10,), {}, n_repeat=5, pick=pick_max)
    assert isinstance(result, int)
    assert result >= 11
    
    print("✓ test_arepeat_and_pick_pick_methods passed")


@pytest.mark.asyncio
async def test_arepeat_and_pick_error_handling():
    """测试 arepeat_and_pick 错误处理"""
    async def specific_error_task(x: int) -> int:
        await asyncio.sleep(0.01)
        raise RuntimeError("Specific runtime error")
    
    with pytest.raises(RuntimeError, match="Specific runtime error"):
        await arepeat_and_pick(specific_error_task, (1,), {}, n_repeat=2)
    
    print("✓ test_arepeat_and_pick_error_handling passed")


@pytest.mark.asyncio
async def test_arepeat_and_pick_async_validation():
    """测试 arepeat_and_pick 异步函数验证"""
    # 测试拒绝同步函数
    def sync_func(x: int) -> int:
        return x + 1
    
    with pytest.raises(AssertionError, match="must be async callable"):
        await arepeat_and_pick(sync_func, (1,), {})  # type: ignore
    
    # 测试异步可调用对象
    class AsyncCallable:
        async def __call__(self, x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2
    
    result = await arepeat_and_pick(AsyncCallable(), (3,), {}, n_repeat=2)
    assert result == 6
    
    print("✓ test_arepeat_and_pick_async_validation passed")


# === retry 装饰器测试 ===

@pytest.mark.asyncio
async def test_repeat_decorator_success():
    """测试 @repeat 装饰器成功场景"""
    @drepeat_and_pick(n_repeat=2)
    async def retry_task(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 2
    
    result = await retry_task(5)
    assert result == 10
    assert not isinstance(result, Exception)
    
    print("✓ test_repeat_decorator_success passed")


@pytest.mark.asyncio
async def test_repeat_decorator_failure():
    """测试 @repeat 装饰器失败场景"""
    @drepeat_and_pick(n_repeat=2)
    async def fail_task(x: int) -> int:
        await asyncio.sleep(0.01)
        raise ValueError("Always fails")
    
    with pytest.raises(ValueError, match="Always fails"):
        await fail_task(1)
    
    print("✓ test_repeat_decorator_failure passed")


@pytest.mark.asyncio
async def test_repeat_decorator_partial_success():
    """测试 @repeat 装饰器部分成功场景"""
    call_count = 0
    @drepeat_and_pick(n_repeat=3)
    async def unreliable_retry_task(x: int) -> int:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)
        if call_count <= 2:  # 前两次失败
            raise ConnectionError(f"Attempt {call_count} failed")
        return x * 3
    
    call_count = 0  # 重置计数器
    result = await unreliable_retry_task(4)
    assert result == 12
    assert not isinstance(result, Exception)
    
    print("✓ test_repeat_decorator_partial_success passed")


@pytest.mark.asyncio
async def test_repeat_decorator_parameters():
    """测试 @repeat 装饰器参数验证"""
    @drepeat_and_pick(n_repeat=5)
    async def multi_retry_task(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 2
    
    result = await multi_retry_task(3)
    assert result == 6
    
    # 测试复杂参数传递
    @drepeat_and_pick(n_repeat=2)
    async def complex_retry_task(x: int, y: int, multiplier: int = 1, offset: int = 0) -> int:
        await asyncio.sleep(0.01)
        return (x + y) * multiplier + offset
    
    result = await complex_retry_task(1, 2, multiplier=3, offset=10)
    assert result == 19
    
    print("✓ test_repeat_decorator_parameters passed")


@pytest.mark.asyncio
async def test_repeat_decorator_pick_methods():
    """测试 @repeat 装饰器 pick 方法"""
    @drepeat_and_pick(n_repeat=3, pick="first")
    async def first_pick_task(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 2
    
    result = await first_pick_task(5)
    assert result == 10
    
    # 测试自定义选择函数
    def pick_max(results: list[int]) -> int:
        return max(results)
    
    @drepeat_and_pick(n_repeat=3, pick=pick_max)
    async def max_pick_task(x: int) -> int:
        import random
        await asyncio.sleep(0.01)
        return x + random.randint(1, 10)
    
    result = await max_pick_task(10)
    assert isinstance(result, int)
    assert result >= 11
    
    print("✓ test_repeat_decorator_pick_methods passed")


@pytest.mark.asyncio
async def test_repeat_decorator_advanced_features():
    """测试 @repeat 装饰器高级功能"""
    # 测试超时功能
    @drepeat_and_pick(n_repeat=2, timeout=0.1)
    async def timeout_task(x: int) -> int:
        await asyncio.sleep(0.2)  # 超过超时时间
        return x * 2
    
    with pytest.raises(asyncio.TimeoutError):
        await timeout_task(5)
    
    # 测试日志功能
    @drepeat_and_pick(n_repeat=2, log_attempts=True)
    async def logged_task(x: int) -> int:
        await asyncio.sleep(0.01)
        return x + 1
    
    result = await logged_task(5)
    assert result == 6
    
    print("✓ test_repeat_decorator_advanced_features passed")


@pytest.mark.asyncio
async def test_repeat_decorator_performance():
    """测试 @repeat 装饰器性能"""
    
    async def fast_retry_task(x: int) -> int:
        await asyncio.sleep(0.001)
        return x + 1
    
    start_time = asyncio.get_event_loop().time()
    result = await drepeat_and_pick(n_repeat=5)(fast_retry_task)(1)
    end_time = asyncio.get_event_loop().time()
    
    assert result == 2
    execution_time = end_time - start_time
    assert execution_time < 0.1, f"Execution time {execution_time:.3f}s should be reasonable for concurrent execution"
    
    print("✓ test_repeat_decorator_performance passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
 
