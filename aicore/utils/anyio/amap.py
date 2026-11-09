"""
异步并发执行工具模块 (基于 anyio)

本模块提供 `amap` 函数，用于并发执行多个异步任务。
核心思想类似于 Python 内置的 `map()`，但支持：
1. 并发执行多个异步函数调用
2. 限制最大并发数（防止资源耗尽）
3. 收集每个任务的执行时间和统计信息
4. 显示进度条
5. 错误处理（某个任务失败不会中断其他任务）

适用场景：批量调用网络 API、数据库查询、文件 IO 等需要等待的操作。
"""

import inspect
import time
import statistics
from dataclasses import dataclass
from functools import cached_property, wraps

import anyio
from tqdm import tqdm

from typing import (
    Callable,
    Iterable,
    Any,
    Awaitable,
)


__all__ = [
    "RuntimeStats",
    "with_param_parse_async",
    "amap",
]


_ParamDict = dict[str, Any]
_ParamTuple = tuple[Any, ...]
_ParamMixed = tuple[tuple[Any, ...], dict[str, Any]]
ParamItem = _ParamDict | _ParamTuple | _ParamMixed


def _parse_param(param: ParamItem) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """
    将各种参数格式统一解析为 (位置参数元组, 关键字参数字典)

    支持三种格式：
    - dict: {"x": 1, "y": 2} → (), {"x": 1, "y": 2}
    - tuple: (1, 2) → (1, 2), {}
    - mixed: ((1, 2), {"z": 3}) → (1, 2), {"z": 3}
    """
    if isinstance(param, dict):
        return (), param
    else:
        assert isinstance(param, tuple)
        if len(param) == 2 and isinstance(param[0], tuple) and isinstance(param[1], dict):
            return param[0], param[1]  # type: ignore
        else:
            return param, {}
    

def with_param_parse_async[T](func: Callable[..., Awaitable[T]]) -> Callable[[ParamItem], Awaitable[T]]:
    """
    装饰器：为异步函数添加参数解析能力

    被装饰的函数可以接收多种参数格式，自动转换为标准的位置参数+关键字参数调用。
    常用于配合 `amap` 使用，让复杂函数也能方便地批量执行。
    """
    @wraps(func)
    async def wrapper(param: ParamItem) -> T:
        assert inspect.iscoroutinefunction(func), f"func {func} must be async"

        position_args, keyword_args = _parse_param(param)
        return await func(*position_args, **keyword_args)
    return wrapper


@dataclass(frozen=True)
class RuntimeStats:
    """
    运行时统计信息

    包含 `amap` 执行后的各项统计数据，帮助评估并发执行的效果。

    属性：
    - times: 每个任务的执行时间（秒）
    - success_count: 成功完成的任务数
    - total_time: 总耗时（从开始到所有任务完成）

    计算属性：
    - avg: 平均执行时间
    - std: 标准差（衡量时间波动）
    - min/max: 最短/最长执行时间
    """
    times: list[float]
    success_count: int
    total_time: float

    def len(self) -> int:
        return len(self.times)

    @cached_property
    def avg(self) -> float:
        return statistics.mean(self.times)

    @cached_property
    def std(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0

    @cached_property
    def min(self) -> float:
        return min(self.times)

    @cached_property
    def max(self) -> float:
        return max(self.times)

    def dump(self) -> list[str]:
        """
        将统计信息格式化为字符串列表，供外部调用者打印

        返回示例：
        [
            "总任务数: 100",
            "完成任务数: 98",
            "总耗时: 5.23秒",
            ...
        ]
        """
        lines = [
            f"总任务数: {self.len()}",
            f"完成任务数: {self.success_count}",
            f"总耗时: {self.total_time:.2f}秒",
            f"单次调用平均时间: {self.avg:.2f}秒",
            f"单次调用时间标准差: {self.std:.2f}秒",
            f"单次调用最短时间: {self.min:.2f}秒",
            f"单次调用最长时间: {self.max:.2f}秒",
        ]

        if self.total_time > 0:
            speedup = self.len() * self.avg / self.total_time
            lines.append(f"加速比: {speedup:.2f}x")
        else:
            lines.append("加速比: N/A (总耗时为0)")

        return lines


ProgressMethod = Callable[[int], None] | tqdm | bool # type: ignore


def _is_async_callable(func: Callable[..., Any]) -> bool:
    """判断函数是否为异步可调用对象

    支持两种情况：
    1. async def 定义的普通异步函数
    2. 类实例，其 __call__ 方法是异步的

    示例：
        async def foo(): ...
        _is_async_callable(foo) → True

        class Bar:
            async def __call__(self): ...
        _is_async_callable(Bar()) → True
    """
    if inspect.iscoroutinefunction(func):
        return True

    if callable(func) and hasattr(func, '__call__'):
        return inspect.iscoroutinefunction(func.__call__)

    return False


async def amap[T](
    func: Callable[[Any], Awaitable[T]],
    params: Iterable[Any],
    /,
    *,
    max_concurrent: int = 100,
    progress: ProgressMethod = False,   # type: ignore
) -> tuple[list[T | Exception], RuntimeStats]:
    """
    异步并发执行函数（类似 map，但支持并发）

    核心流程：
    1. 将所有参数转换为列表
    2. 创建一个任务组（task_group）管理并发任务
    3. 使用信号量（semaphore）限制同时运行的任务数
    4. 每个任务执行时记录时间，失败时保存异常对象
    5. 返回结果列表和统计信息

    参数：
    - func: 要执行的异步函数（必须是 async def 定义）
    - params: 参数列表，每个元素会传给 func
    - max_concurrent: 最大并发数（默认100，防止资源耗尽）
    - progress: 进度显示方式
      - False: 不显示进度
      - True: 使用 tqdm 显示进度条
      - tqdm 对象: 使用自定义的 tqdm
      - 回调函数: 接收已完成任务数作为参数

    返回：
    - results: 结果列表，按参数顺序排列，失败的任务返回 Exception 对象
    - stats: RuntimeStats 统计信息

    示例：
        async def fetch_url(url):
            # 网络请求...

        urls = ["https://a.com", "https://b.com", "https://c.com"]
        results, stats = await amap(fetch_url, urls, max_concurrent=10)

        for result in results:
            if isinstance(result, Exception):
                print(f"失败: {result}")
            else:
                print(f"成功: {result}")

        # 打印统计信息
        for line in stats.dump():
            print(line)
    """
    assert max_concurrent > 0, "max_concurrent must be a positive integer"
    assert _is_async_callable(func), f"func {func} must be async callable"

    if isinstance(progress, bool):
        if progress:
            try:
                total = len(params)   # type: ignore
            except Exception:
                total = None
            progress = tqdm(total=total, desc="amap processing")

    assert (progress is False or
            isinstance(progress, tqdm) or
            callable(progress)), "progress must be False, tqdm or callable"

    semaphore = anyio.Semaphore(max_concurrent)

    success_count = 0
    times: list[float] = []

    async def worker(index: int, param: Any, results: list[T | Exception]) -> None:
        """单个任务的执行函数

        负责：执行函数、记录时间、更新进度、保存结果
        使用 semaphore 控制并发数
        """
        nonlocal success_count, times

        task_start_time = time.time()
        async with semaphore:
            try:
                result = await func(param)
                success_count += 1
            except Exception as e:
                result = e
            finally:
                results[index] = result  # type: ignore
                task_end_time = time.time()
                times.append(task_end_time - task_start_time)

                if isinstance(progress, tqdm):
                    progress.update()
                elif callable(progress):
                    try:
                        progress(len(times))
                    except Exception as e:
                        print(f"Error in progress callback: {e}")

    start_time = time.time()
    params_list = list(params)
    results: list[T | Exception] = [None] * len(params_list)  # type: ignore

    async with anyio.create_task_group() as tg:
        for i, param in enumerate(params_list):
            tg.start_soon(worker, i, param, results)

    if isinstance(progress, tqdm):
        progress.close()

    return results, RuntimeStats(times, success_count, time.time() - start_time)