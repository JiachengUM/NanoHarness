import pytest
import asyncio

from rich import print

from aicore.events.task import (
    TaskProgressEvent, 
    TaskSuccessEvent, 
    TaskFailureEvent, 
    TaskStartEvent,
    TaskEventPrinter,
)

from aicore.core.stream_task_runner import TaskProgress, TaskSuccess, StreamTaskRunner

# --- 辅助函数：模拟业务工厂 ---

def make_factory(progress_list: list, final_result = None, raise_error: Exception | None = None):
    """
    创建一个模拟的业务工厂
    :param progress_list: 想要 yield 的进度数据列表
    :param final_result: 想要 return 的结果数据
    :param raise_error: 如果想测试报错，传一个 Exception 实例
    """
    async def mock_business_logic():
        for p in progress_list:
            await asyncio.sleep(0.01) # 模拟异步IO
            yield TaskProgress(progress=p)
        
        if raise_error:
            raise raise_error
            
        yield TaskSuccess(result=final_result)
    
    return mock_business_logic

# --- 测试用例 ---

@pytest.mark.asyncio
async def test_single_task_success():
    """测试 1：单个任务，正常产出进度和结果"""
    print("\n=== 测试 1: 单个任务成功 ===")
    runner = StreamTaskRunner()
    
    # 1. 添加任务
    factory = make_factory(progress_list=["step 1", "step 2"], final_result={"code": 200})
    runner.add_task(factory, task_id="task_1")
    
    # 2. 收集事件
    events = []
    print("收集事件中...")
    printer = TaskEventPrinter()

    async for event in runner.run():
        printer(event)
        events.append(event)
    
    # 3. 断言
    print(f"事件总数: {len(events)}")
    assert len(events) == 4 # Start + Progress x2 + Success
    
    # 检查开始事件
    assert isinstance(events[0], TaskStartEvent)
    assert events[0].task_id == "task_1"
    
    # 检查进度事件
    assert isinstance(events[1], TaskProgressEvent)
    assert events[1].progress == "step 1"
    
    # 检查结果事件
    assert isinstance(events[3], TaskSuccessEvent)
    assert events[3].result == {"code": 200}
    print("测试 1 完成！")


@pytest.mark.asyncio
async def test_task_failure():
    """测试 2：任务执行过程中报错"""
    print("\n=== 测试 2: 任务失败 ===")
    runner = StreamTaskRunner()
    
    # 1. 添加一个会报错的任务
    error = ValueError("Database connection failed")
    factory = make_factory(progress_list=["step 1"], raise_error=error)
    runner.add_task(factory, task_id="task_err")
    
    # 2. 收集事件
    events = []
    print("收集事件中...")
    printer = TaskEventPrinter()
    async for event in runner.run():
        printer(event)
        events.append(event)
    
    # 3. 断言
    print(f"事件总数: {len(events)}")
    assert len(events) == 3 # Start + Progress + Failure
    
    assert isinstance(events[0], TaskStartEvent)
    
    assert isinstance(events[1], TaskProgressEvent)
    assert events[1].progress == "step 1"
    
    assert isinstance(events[2], TaskFailureEvent)
    assert "Database connection failed" in events[2].error
    print("测试 2 完成！")

@pytest.mark.asyncio
async def test_concurrent_tasks():
    """测试 3：并发执行多个任务（乱序测试）"""
    print("\n=== 测试 3: 并发任务 ===")
    runner = StreamTaskRunner()
    
    # 任务 A 慢一点，任务 B 快一点
    factory_a = make_factory(progress_list=["A1", "A2"], final_result="Result A")
    factory_b = make_factory(progress_list=["B1"], final_result="Result B")
    
    runner.add_task(factory_a, task_id="A")
    runner.add_task(factory_b, task_id="B")
    
    events = []
    print("收集事件中...")
    printer = TaskEventPrinter()
    async for event in runner.run():
        printer(event)
        events.append(event)
    
    # 断言：总共应该有 2个Start + 3个Progress + 2个Success = 7个事件
    # 注意：因为并发，Progress 的顺序可能是 A1, B1, A2 或者 B1, A1, A2
    print(f"事件总数: {len(events)}")
    assert len(events) == 7
    
    # 确保两个任务都开始了
    start_ids = {e.task_id for e in events if isinstance(e, TaskStartEvent)}
    print(f"开始的任务: {start_ids}")
    assert start_ids == {"A", "B"}
    
    # 确保两个任务都成功了
    success_ids = {e.task_id for e in events if isinstance(e, TaskSuccessEvent)}
    print(f"成功的任务: {success_ids}")
    assert success_ids == {"A", "B"}
    print("测试 3 完成！")

    print(runner.results)

@pytest.mark.asyncio
async def test_task_cancellation():
    """测试 4：消费者中途取消（模拟断网/超时）"""
    print("\n=== 测试 4: 任务取消 ===")
    runner = StreamTaskRunner()
    
    # 一个无限循环的任务，用来模拟长时间运行
    async def infinite_task():
        i = 0
        while True:
            yield TaskProgress(progress=i)
            await asyncio.sleep(0.1)
            i += 1
            
    runner.add_task(infinite_task, task_id="infinite")
    
    # 使用 asyncio.timeout 来模拟外部取消
    count = 0
    events = []
    print("收集事件中...")
    printer = TaskEventPrinter()
    try:
        async with asyncio.timeout(0.3):  # 0.3秒后超时
            async for event in runner.run():
                printer(event)
                events.append(event)
                count += 1
    except asyncio.TimeoutError:
        # 预期会超时，这模拟了外部取消的场景
        print("  超时触发，模拟外部取消")
        pass
    
    # 测试应该能正常完成，不会挂死
    # 至少应该收到 1 个事件（Start 事件）
    print(f"收到的事件数: {count}")
    print(f"事件列表: {[event.type for event in events]}")
    assert count >= 1
    print("测试 4 完成！")


async def main():
    await test_single_task_success()
    await test_task_failure()
    await test_concurrent_tasks()
    await test_task_cancellation()

if __name__ == "__main__":
    asyncio.run(main())