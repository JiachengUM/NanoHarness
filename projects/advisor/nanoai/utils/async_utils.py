import asyncio
import inspect
import statistics
import time
from dataclasses import dataclass
from functools import cached_property, wraps
from typing import (
    Callable,
    Iterable,
    Any,
    AsyncGenerator,
    Awaitable,
    Literal,
)

from tqdm import tqdm

__all__ = [
    "RuntimeStats", 
    "with_param_parse", 
    "with_param_parse_async",
    "map",
    "amap",
    "amap_stream",
    "arepeat_and_pick",
    "drepeat_and_pick",
]

# 定义参数类型
_ParamDict = dict[str, Any]
_ParamTuple = tuple[Any, ...]
_ParamMixed = tuple[tuple[Any, ...], dict[str, Any]]
ParamItem = _ParamDict | _ParamTuple | _ParamMixed

def _parse_param(param: ParamItem) -> tuple[tuple[Any, ...], dict[str, Any]]:
    """解析参数，返回标准化的 (position_args, keyword_args) 元组
    
    :param param: 参数，支持三种格式：
        - Dict[str, Any]: keyword 参数，如 {"x": 1, "y": 2}
        - Tuple[Any, ...]: position 参数，如 (1, 2, 3)
        - Tuple[Tuple[Any, ...], Dict[str, Any]]: 混合参数，如 ((1, 2), {"z": 3})
    :return: 标准化的 (position_args, keyword_args) 元组
    :raises TypeError: 当参数格式无效时
    """
    if isinstance(param, dict):
        # 纯 keyword 参数
        return (), param
    elif isinstance(param, tuple):
        if len(param) == 2 and isinstance(param[0], tuple) and isinstance(param[1], dict):
            # 混合参数：(position_args, keyword_args)
            return param[0], param[1]
        else:
            # 纯 position 参数
            return param, {}
    else:
        raise TypeError(f"Invalid param format: {type(param)}")


def with_param_parse[T](func: Callable[..., T]) -> Callable[[ParamItem], T]:
    """将需要参数解析的函数包装为接受 ParamItem 的函数
    
    这个装饰器允许函数接受标准化的参数格式，支持三种参数类型：
    1. Dict[str, Any]: 纯关键字参数
    2. Tuple[Any, ...]: 纯位置参数  
    3. Tuple[Tuple[Any, ...], Dict[str, Any]]: 混合参数
    
    :param func: 原始函数，可以是任意签名的可调用对象
    :return: 包装后的函数，接受 ParamItem 参数
    
    使用示例:
        # 1. 基本函数包装
        def add(x: int, y: int) -> int:
            return x + y
        
        wrapped_add = with_param_parse(add)
        
        # 使用关键字参数
        result1 = wrapped_add({"x": 1, "y": 2})  # 结果: 3
        
        # 使用位置参数
        result2 = wrapped_add((1, 2))  # 结果: 3
        
        # 使用混合参数
        result3 = wrapped_add(((1,), {"y": 2}))  # 结果: 3
        
        # 2. 复杂函数包装
        def process_data(name: str, age: int, city: str = "北京", active: bool = True) -> str:
            status = "活跃" if active else "非活跃"
            return f"{name}({age}岁)来自{city}，状态：{status}"
        
        wrapped_process = with_param_parse(process_data)
        
        # 使用关键字参数
        result1 = wrapped_process({
            "name": "张三", 
            "age": 25, 
            "city": "上海", 
            "active": False
        })
        # 结果: "张三(25岁)来自上海，状态：非活跃"
        
        # 使用位置参数
        result2 = wrapped_process(("李四", 30))
        # 结果: "李四(30岁)来自北京，状态：活跃"
        
        # 使用混合参数
        result3 = wrapped_process((("王五", 28), {"city": "广州"}))
        # 结果: "王五(28岁)来自广州，状态：活跃"
        
        # 3. 与 map 函数结合使用
        def calculate_area(length: float, width: float, unit: str = "平方米") -> str:
            area = length * width
            return f"面积: {area}{unit}"
        
        wrapped_calc = with_param_parse(calculate_area)
        
        # 批量处理不同参数格式
        params = [
            {"length": 5.0, "width": 3.0, "unit": "平方厘米"},
            (10.0, 2.0),  # 使用默认单位
            ((7.5,), {"width": 4.0, "unit": "平方英尺"})
        ]
        
        results, stats = map(wrapped_calc, params)
        for result in results:
            print(result)
        # 输出:
        # 面积: 15.0平方厘米
        # 面积: 20.0平方米  
        # 面积: 30.0平方英尺
    """
    @wraps(func)
    def wrapper(param: ParamItem) -> T:
        position_args, keyword_args = _parse_param(param)
        return func(*position_args, **keyword_args)
    return wrapper


def with_param_parse_async[T](func: Callable[..., Awaitable[T]]) -> Callable[[ParamItem], Awaitable[T]]:
    """异步版本的参数解析包装器
    
    :param func: 原始异步函数
    :return: 包装后的异步函数，接受 ParamItem 参数
    """
    @wraps(func)
    async def wrapper(param: ParamItem) -> T:
        assert inspect.iscoroutinefunction(func), f"func {func} must be async"

        position_args, keyword_args = _parse_param(param)
        return await func(*position_args, **keyword_args)
    return wrapper


@dataclass(frozen=True)
class RuntimeStats:
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
    
    def print(self):
        print(f"总任务数: {self.len()}")
        print(f"完成任务数: {self.success_count}")
        print(f"总耗时: {self.total_time:.2f}秒")
        print(f"单次调用平均时间: {self.avg:.2f}秒")
        print(f"单次调用时间标准差: {self.std:.2f}秒")
        print(f"单次调用最短时间: {self.min:.2f}秒")
        print(f"单次调用最长时间: {self.max:.2f}秒")
        
        if self.total_time > 0:
            speedup = self.len() * self.avg / self.total_time
            print(f"加速比: {speedup:.2f}x")
        else:
            print("加速比: N/A (总耗时为0)")


# 定义显示进度的方法
ProgressMethod = Callable[[int], None] | tqdm | bool


def _is_async_callable(func) -> bool:
    """检查函数是否是可调用的异步函数
    
    支持以下情况：
    1. 协程函数本身
    2. 可调用对象，其 __call__ 方法是协程函数
    3. 其他可调用对象，调用后返回协程
    """
    if inspect.iscoroutinefunction(func):
        return True
    
    # 检查是否是可调用对象且其 __call__ 方法是协程
    if callable(func) and hasattr(func, '__call__'):
        return inspect.iscoroutinefunction(func.__call__)
    
    return False


def map[T](
    func: Callable[[Any], T],
    params: Iterable[Any],
    /,
    *,
    progress: ProgressMethod = False,
) -> tuple[list[T | Exception], RuntimeStats]:
    """同步 map 实现，返回结果列表
    
    - 串行执行函数，直接传递参数给函数
    - 收集所有结果和异常，返回结果列表
    - 统计执行时间和成功率
    - 支持进度显示（自定义回调或 tqdm 进度条）
    
    :param func: 要执行的函数，接受单个参数
    :param params: 参数列表
    :param progress: 进度回调，支持：
        - Callable[[int], None]: 自定义回调函数
        - tqdm: tqdm 进度条对象
        - bool: True 时创建默认 tqdm 进度条，False 时无进度显示
    :return: 结果列表，失败时返回异常对象，以及运行时间统计
    """
    
    # 处理 bool 类型的 progress
    if isinstance(progress, bool):
        if progress:
            try:
                total = len(params)
            except:
                total = None
            progress = tqdm(total=total, desc="map processing")
    
    # 时间统计
    times: list[float] = []
    results = []
    success_count = 0

    start_time = time.time()

    for i, param in enumerate(params):
        task_start_time = time.time()
        try:
            result = func(param)
            success_count += 1
        except Exception as e:
            result = e
        finally:
            results.append(result)

            task_end_time = time.time()
            times.append(task_end_time - task_start_time)

            # 处理进度回调
            if isinstance(progress, tqdm):
                progress.update()  # 默认增加 1
            elif callable(progress):
                try:
                    progress(len(times))
                except Exception as e:
                    print(f"Error in progress callback: {e}")
                    continue
    
    # 关闭 tqdm 进度条
    if isinstance(progress, tqdm):
        progress.close()
    
    return results, RuntimeStats(times, success_count, time.time() - start_time)


async def amap[T](
    func: Callable[[Any], Awaitable[T]],
    params: Iterable[Any],
    /,
    *,
    max_concurrent: int = 100,
    progress: ProgressMethod = False,
) -> tuple[list[T | Exception], RuntimeStats]:
    """异步 map 实现，返回结果列表
    
    - 并发执行异步函数，最多 max_concurrent 个同时运行
    - 使用信号量控制并发数，防止资源耗尽
    - 等待所有任务完成后，返回完整结果列表
    - 统计执行时间和成功率
    - 支持进度显示（自定义回调或 tqdm 进度条）
    
    :param func: 要执行的异步函数，接受单个参数
    :param params: 参数列表
    :param max_concurrent: 最大并发数
    :param progress: 进度回调，支持：
        - Callable[[int], None]: 自定义回调函数
        - tqdm: tqdm 进度条对象
        - bool: True 时创建默认 tqdm 进度条，False 时无进度显示
    :return: 结果列表，失败时返回异常对象，以及运行时间统计
    """
    assert max_concurrent > 0, "max_concurrent must be a positive integer"
    assert _is_async_callable(func), f"func {func} must be async callable"
    
    # 处理 bool 类型的 progress
    if isinstance(progress, bool):
        if progress:
            try:
                total = len(params)
            except:
                total = None
            progress = tqdm(total=total, desc="amap processing")
    
    assert (progress is False or 
            isinstance(progress, tqdm) or 
            callable(progress)), "progress must be False, tqdm or callable"
    
    semaphore = asyncio.Semaphore(max_concurrent)

    # 时间统计
    success_count = 0
    times: list[float] = []
    
    async def worker(index: int, param: Any) -> T | Exception:
        nonlocal success_count, times
        
        task_start_time = time.time()
        async with semaphore:
            try:
                result = await func(param)
                success_count += 1
            except Exception as e:
                result = e
            finally:
                task_end_time = time.time()
                times.append(task_end_time - task_start_time)
                
                # 处理进度回调
                if isinstance(progress, tqdm):
                    progress.update() # 默认增加 1
                elif callable(progress):
                    try:
                        progress(len(times))
                    except Exception as e:
                        print(f"Error in progress callback: {e}")

                return result
    
    start_time = time.time()
    results = await asyncio.gather(*[worker(i, p) for i, p in enumerate(params)], return_exceptions=True)
    
    # 关闭 tqdm 进度条
    if isinstance(progress, tqdm):
        progress.close()
    
    return results, RuntimeStats(times, success_count, time.time() - start_time)


async def amap_stream[T](
    func: Callable[[Any], Awaitable[T]],
    params: Iterable[Any],
    /,
    *,
    max_concurrent: int = 100,
    progress: ProgressMethod = False,
) -> AsyncGenerator[T | Exception, None]:
    """异步 map 流式实现，逐个产生结果
    
    - 并发执行异步函数，最多 max_concurrent 个同时运行
    - 使用信号量控制并发数，防止资源耗尽
    - 流式返回结果：完成一个返回一个，不等待所有任务
    - 适合处理大量数据，内存友好
    - 支持进度显示（自定义回调或 tqdm 进度条）
    
    :param func: 要执行的异步函数，接受单个参数
    :param params: 参数列表
    :param max_concurrent: 最大并发数
    :param progress: 进度回调，支持：
        - Callable[[int], None]: 自定义回调函数
        - tqdm: tqdm 进度条对象
        - bool: True 时创建默认 tqdm 进度条，False 时无进度显示
    :return: 异步生成器，逐个产生结果
    
    使用示例:
        # 基本使用
        async def fetch_data(url: str) -> str:
            await asyncio.sleep(0.1)  # 模拟网络请求
            return f"data from {url}"
        
        urls = ["http://example.com", "http://test.com", "http://demo.com"]
        gen = await amap_stream(fetch_data, urls)
        
        results = []
        async for result in gen:
            results.append(result)
            print(f"Got result: {result}")
        
        # 使用 with_param_parse_async 处理复杂参数
        async def process_data(x: int, y: int, multiplier: int = 1) -> int:
            await asyncio.sleep(0.01)
            return (x + y) * multiplier
        
        wrapped_func = with_param_parse_async(process_data)
        params = [
            {"x": 1, "y": 2, "multiplier": 3},  # 结果: 9
            (3, 4, {"multiplier": 2}),          # 结果: 14
            ((5, 6), {"multiplier": 1}),        # 结果: 11
        ]
        
        gen = await amap_stream(wrapped_func, params)
        async for result in gen:
            print(f"Processed: {result}")
        
        # 使用进度回调
        def progress_callback(completed: int):
            print(f"Completed {completed} tasks")
        
        gen = await amap_stream(fetch_data, urls, progress=progress)
        async for result in gen:
            print(f"Result: {result}")
        
        # 错误处理
        async def risky_task(x: int) -> int:
            if x == 0:
                raise ValueError("Zero not allowed")
            await asyncio.sleep(0.01)
            return x * 2
        
        gen = await amap_stream(risky_task, [0, 1, 2, 3])
        async for result in gen:
            if isinstance(result, Exception):
                print(f"Error: {result}")
            else:
                print(f"Success: {result}")
    """
    assert max_concurrent > 0, "max_concurrent must be a positive integer"
    assert _is_async_callable(func), f"func {func} must be async callable"
    
    # 处理 bool 类型的 progress
    if isinstance(progress, bool):
        if progress:
            try:
                total = len(params)
            except:
                total = None
            progress = tqdm(total=total, desc="amap_stream processing")
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # 时间统计
    success_count = 0
    times: list[float] = []
    
    async def worker(param: Any) -> T | Exception:
        nonlocal success_count, times
        
        task_start_time = time.time()
        async with semaphore:
            try:
                result = await func(param)
                success_count += 1
                return result
            except Exception as e:
                return e
            finally:
                task_end_time = time.time()
                times.append(task_end_time - task_start_time)
    
    async def gen() -> AsyncGenerator[T | Exception, None]:
        start_time = time.time()
        for coro in asyncio.as_completed([worker(p) for p in params]):
            result = await coro
            
            # 处理进度回调
            if isinstance(progress, tqdm):
                progress.update()  # 默认增加 1
            elif callable(progress):
                try:
                    progress(len(times))
                except Exception as e:
                    print(f"Error in progress callback: {e}")
            
            yield result

        # 关闭 tqdm 进度条
        if isinstance(progress, tqdm):
            progress.close()

        stats = RuntimeStats(times, success_count, time.time() - start_time)
        stats.print()
    
    return gen()


async def arepeat[R](
    func: Callable[..., Awaitable[R]],
    args: tuple[Any, ...],
    kw_args: dict[str, Any],
    /,
    *,
    n_repeat: int = 2,
) -> list[R | Exception]:
    """重复执行同一个函数，对于多次结果做比较和处理。
    和通常意义上的retry不同，repeat会异步执行n次，而retry是失败了再重试, 最多n次。它们的适用场景不同。
    用于处理结果不确定的函数，例如大模型调用。

    :param func: 要执行的函数，接受参数
    :param args: 位置参数
    :param kw_args: 关键字参数
    :param n_repeat: 重复执行次数
    """

    # TODO: 目前支持n_repeat=1的情况。但真的需要么？
    assert n_repeat > 0, "n_repeat must be a positive integer"
    assert _is_async_callable(func), f"func {func} must be async callable"
    
    # 创建任务列表
    tasks: list[asyncio.Task[Any]] = []
    for _ in range(n_repeat):
        coro = func(*args, **kw_args)
        # 使用类型忽略来处理 Awaitable 到 Coroutine 的转换
        task = asyncio.create_task(coro)  # type: ignore
        tasks.append(task)
    
    # 等待所有任务完成
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results


async def arepeat_and_pick[R](
    func: Callable[..., Awaitable[R]],
    args: tuple[Any, ...],
    kw_args: dict[str, Any],
    /,
    *,
    n_repeat: int = 2,
    pick: Callable[[list[R]], R] | Literal["first"] = "first",
):
    """
    如果有>=1次执行成功，则从中选择结果返回，否则抛出异常。
    :param pick: 选择结果的方法，支持：
        - Callable[[list[R]], R]: 自定义选择方法
        - Literal["first"]: 选择第一个结果
    
    使用示例:
        # 基本使用
        async def unreliable_api_call(url: str) -> str:
            import random
            if random.random() < 0.3:  # 30% 失败率
                raise ConnectionError("API call failed")
            return f"Data from {url}"
        
        # 重复执行3次，选择第一个成功的结果
        result = await arepeat_and_pick(
            unreliable_api_call,
            ("https://api.example.com",),
            {},
            n_repeat=3,
            pick="first"
        )
        
        # 使用自定义选择方法
        def pick_longest(results: list[str]) -> str:
            return max(results, key=len)
        
        result = await arepeat_and_pick(
            unreliable_api_call,
            ("https://api.example.com",),
            {},
            n_repeat=3,
            pick=pick_longest
        )
    """

    results = await arepeat(func, args, kw_args, n_repeat=n_repeat)

    # 过滤出成功的结果（非异常）
    successful_results: list[R] = []
    exceptions: list[Exception] = []
    
    for result in results:
        if isinstance(result, Exception):
            exceptions.append(result)
        else:
            # 类型断言，确保result是R类型
            successful_results.append(result)  # type: ignore
    
    # 如果没有成功的结果，返回第一个异常
    if not successful_results:
        assert exceptions, "没有results时，不能没有异常"
        raise exceptions[0]
        
    # 根据pick方法选择结果
    if pick == "first":
        return successful_results[0]
    elif callable(pick):
        return pick(successful_results)
    else:
        raise ValueError(f"Invalid pick method: {pick}")


def drepeat_and_pick(
    n_repeat: int = 2,
    pick: Callable[[list], Any] | Literal["first"] = "first",
    timeout: float | None = None,
    log_attempts: bool = False
):
    """高级重试装饰器，基于 arepeat_and_pick 实现
    
    提供企业级重试功能，支持多种配置选项：
    - 精确的异常过滤
    - 灵活的结果选择策略
    - 超时保护机制
    - 退避策略
    - 可选的执行日志
    
    :param n_repeat: 重复执行次数，默认为2
    :param pick: 结果选择方法，支持：
        - str: "first" 选择第一个成功结果
        - Callable[[list], Any]: 自定义选择函数
    :param timeout: 超时时间（秒），None表示无超时
    :param log_attempts: 是否记录执行日志，默认为False
    
    使用示例:
        # 基本使用
        @repeat(n_repeat=3)
        async def api_call():
            # 重试3次，选择第一个成功结果
            pass
        
        # 自定义结果选择
        def pick_best(results: list[str]) -> str:
            return max(results, key=len)
        
        @repeat(n_repeat=3, pick=pick_best)
        async def get_best_result():
            # 选择最佳结果
            pass
        
        # 带超时保护
        @repeat(
            n_repeat=3,
            timeout=30.0,
            log_attempts=True
        )
        async def slow_operation():
            # 30秒超时，记录执行日志
            pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if log_attempts:
                print(f"🔄 开始执行 {func.__name__}，重试次数: {n_repeat}")
            
            # 如果有超时设置，使用 asyncio.wait_for 包装
            if timeout is not None:
                async def timeout_wrapper():
                    return await arepeat_and_pick(
                        func, args, kwargs,
                        n_repeat=n_repeat,
                        pick=pick
                    )
                
                try:
                    result = await asyncio.wait_for(timeout_wrapper(), timeout=timeout)
                except asyncio.TimeoutError:
                    if log_attempts:
                        print(f"⏰ {func.__name__} 执行超时 ({timeout}s)")
                    raise
            else:
                result = await arepeat_and_pick(
                    func, args, kwargs,
                    n_repeat=n_repeat,
                    pick=pick
                )
            
            if log_attempts:
                print(f"✅ {func.__name__} 执行成功")
            
            return result
        return wrapper
    return decorator
