import pytest
import time

import anyio

from rich import print

from aicore.utils.anyio.amap import amap, with_param_parse_async


@pytest.mark.anyio(backend="asyncio")
async def test_amap_basic():
    async def add_one(x: int) -> int:
        await anyio.sleep(0.01)
        return x + 1

    results, stats = await amap(add_one, [0, 1, 2])
    assert results == [1, 2, 3]
    assert stats.success_count == 3
    assert stats.len() == 3


@pytest.mark.anyio(backend="asyncio")
async def test_amap_concurrency_control():
    async def slow_task(x: int) -> int:
        await anyio.sleep(0.1)
        return x

    params = [i for i in range(5)]

    start_time = time.time()
    results, stats = await amap(slow_task, params, max_concurrent=2)
    end_time = time.time()

    assert results == [0, 1, 2, 3, 4]
    assert stats.success_count == 5
    assert 0.25 <= (end_time - start_time) <= 0.4


@pytest.mark.anyio(backend="asyncio")
async def test_amap_error_handling():
    async def divide_by_zero(x: int) -> float:
        await anyio.sleep(0.01)
        if x == 0:
            raise ValueError("Division by zero")
        return 10 / x

    results, stats = await amap(divide_by_zero, [0, 1, 2])
    assert isinstance(results[0], ValueError)
    assert results[1] == 10.0
    assert results[2] == 5.0
    assert stats.success_count == 2


@pytest.mark.anyio(backend="asyncio")
async def test_amap_progress_callbacks():
    async def task(x: int) -> int:
        await anyio.sleep(0.01)
        return x * 2

    params = [i for i in range(3)]

    progress_calls = []
    def progress_callback(completed: int):
        progress_calls.append(completed)

    results, stats = await amap(task, params, progress=progress_callback)
    assert results == [0, 2, 4]
    assert progress_calls == [1, 2, 3]

    results, stats = await amap(task, params, progress=False)
    assert results == [0, 2, 4]

    results, stats = await amap(task, params, progress=True)
    assert results == [0, 2, 4]


@pytest.mark.anyio(backend="asyncio")
async def test_amap_parameter_validation():
    async def task(x: int) -> int:
        return x * 2

    with pytest.raises(AssertionError, match="max_concurrent must be a positive integer"):
        await amap(task, [1, 2, 3], max_concurrent=0)

    with pytest.raises(AssertionError, match="max_concurrent must be a positive integer"):
        await amap(task, [1, 2, 3], max_concurrent=-1)

    def sync_func(x: int) -> int:
        return x + 1

    with pytest.raises(AssertionError, match="must be async callable"):
        await amap(sync_func, [1, 2, 3])  # type: ignore


@pytest.mark.anyio(backend="asyncio")
async def test_amap_runtime_stats():
    async def fast_task(x: int) -> int:
        await anyio.sleep(0.1)
        return x * 2

    results, stats = await amap(
        fast_task, 
        [0, 1, 2, 3, 4], 
        progress=True,
        )
    assert stats.len() == 5
    assert stats.success_count == 5
    assert stats.total_time > 0
    assert stats.avg > 0
    assert stats.min > 0
    assert stats.max > 0
    assert stats.std >= 0

    lines = stats.dump()
    print(lines)


@pytest.mark.anyio(backend="asyncio")
async def test_amap_concurrency_benefit():
    async def io_task(x: int) -> int:
        await anyio.sleep(0.1)
        return x * 2

    params = [i for i in range(5)]

    start_time = time.time()
    results, stats = await amap(io_task, params, max_concurrent=5)
    end_time = time.time()

    assert results == [0, 2, 4, 6, 8]
    assert stats.success_count == 5

    execution_time = end_time - start_time
    assert execution_time < 0.2, f"Execution time {execution_time:.2f}s should be much less than 0.5s for concurrent execution"


@pytest.mark.anyio(backend="asyncio")
async def test_amap_with_param_parse_async():
    async def complex_func(x: int, y: int, multiplier: int = 1, offset: int = 0) -> int:
        await anyio.sleep(0.01)
        return (x + y) * multiplier + offset

    wrapped_func = with_param_parse_async(complex_func)
    params = [
        ((1, 2), {"multiplier": 2, "offset": 10}),
        ((3, 4), {"multiplier": 3, "offset": 5}),
        ((5, 6), {"offset": 100}),
    ]

    results, stats = await amap(wrapped_func, params)
    assert results == [16, 26, 111]
    assert stats.success_count == 3


@pytest.mark.anyio(backend="asyncio")
async def test_amap_async_callable_objects():
    class AsyncCallable:
        async def __call__(self, x: int) -> int:
            await anyio.sleep(0.01)
            return x * 3

    results, stats = await amap(AsyncCallable(), [0, 1, 2])
    assert results == [0, 3, 6]
    assert stats.success_count == 3


@pytest.mark.anyio(backend="asyncio")
async def test_amap_empty_params():
    async def task(x: int) -> int:
        await anyio.sleep(0.01)
        return x * 2

    results, stats = await amap(task, [])
    assert results == []
    assert stats.success_count == 0
    assert stats.len() == 0


@pytest.mark.anyio(backend="asyncio")
async def test_amap_single_param():
    async def task(x: int) -> int:
        await anyio.sleep(0.01)
        return x * 2

    results, stats = await amap(task, [42])
    assert results == [84]
    assert stats.success_count == 1
    assert stats.len() == 1


@pytest.mark.anyio(backend="asyncio")
async def test_amap_keyword_params():
    async def task(x: int) -> int:
        await anyio.sleep(0.01)
        return x * 2

    results, stats = await amap(task, [1, 2, 3], max_concurrent=100, progress=False)
    assert results == [2, 4, 6]
    assert stats.success_count == 3


async def main():
    await test_amap_runtime_stats()


if __name__ == "__main__":
    anyio.run(main)