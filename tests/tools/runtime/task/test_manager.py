from datetime import datetime

from rich import print

# 假设的导入路径，请根据你的实际项目结构调整
from aicore.runtime.task.manager import TaskManager
from aicore.runtime.task.models import TaskRun, TaskStatus
from aicore.events.task import (
    TaskStartEvent, 
    TaskProgressEvent, 
    TaskSuccessEvent, 
    TaskFailureEvent, 
    TaskCancelledEvent
)

# --- 测试用例 ---

"""测试任务生命周期的完整流程"""

def test_handle_start_success():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 1] 测试任务启动")
    event = TaskStartEvent(task_id="task_001")

    task_manager.handle_event(event)

    run = task_manager.get_task("task_001")
    assert run is not None
    assert run.status == TaskStatus.RUNNING
    assert run.task_id == "task_001"
    print("[测试 1] ✓ 通过 - 任务启动成功，状态: RUNNING")

def test_handle_progress_success():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 2] 测试进度更新")
    task_manager.handle_event(TaskStartEvent(task_id="task_001"))

    event = TaskProgressEvent(
        task_id="task_001",
        progress="正在规划路线..."
    )

    task_manager.handle_event(event)

    run = task_manager.get_task("task_001")
    assert isinstance(run, TaskRun)
    assert len(run.trace) == 1
    assert "正在规划路线..." in run.trace[0]
    print("[测试 2] ✓ 通过 - 进度更新成功，trace: ", run.trace)

def test_handle_success_success():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 3] 测试任务成功结束")
    task_manager.handle_event(TaskStartEvent(task_id="task_001"))

    event = TaskSuccessEvent(
        task_id="task_001",
        result={"distance": "10km"}
    )

    task_manager.handle_event(event)

    run = task_manager.get_task("task_001")
    assert isinstance(run, TaskRun)
    assert run.status == TaskStatus.SUCCESS
    assert run.result == {"distance": "10km"}
    assert run.progress == 100
    print("[测试 3] ✓ 通过 - 任务成功结束，状态: SUCCESS，结果: ", run.result)

def test_handle_failure_success():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 4] 测试任务失败结束")
    task_manager.handle_event(TaskStartEvent(task_id="task_001"))

    event = TaskFailureEvent(
        task_id="task_001",
        error="网络超时"
    )

    task_manager.handle_event(event)

    run = task_manager.get_task("task_001")
    assert isinstance(run, TaskRun)
    assert run.status == TaskStatus.FAILED
    assert "网络超时" in run.error  # type: ignore
    print("[测试 4] ✓ 通过 - 任务失败，状态: FAILED，错误: ", run.error)

def test_handle_cancelled_success():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 5] 测试任务取消")
    task_manager.handle_event(TaskStartEvent(task_id="task_001"))

    event = TaskCancelledEvent(
        task_id="task_001",
        timestamp=datetime.now()
    )

    task_manager.handle_event(event)

    run = task_manager.get_task("task_001")
    assert isinstance(run, TaskRun)
    assert run.status == TaskStatus.CANCELLED
    print("[测试 5] ✓ 通过 - 任务已取消，状态: CANCELLED")


"""测试代码中的 assert 逻辑（异常路径）"""

def test_start_existing_task_raises():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 6] 测试重复启动任务应抛出异常")
    task_manager.handle_event(TaskStartEvent(task_id="task_001"))

    try:
        task_manager.handle_event(TaskStartEvent(task_id="task_001"))
        print("[测试 6] ✗ 失败 - 未抛出异常")
    except AssertionError as e:
        print("[测试 6] ✓ 通过 - 正确抛出异常: ", str(e))

def test_progress_nonexistent_task_raises():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 7] 测试不存在的任务更新进度应抛出异常")
    event = TaskProgressEvent(
        task_id="nonexistent_task",
        progress="test"
    )

    try:
        task_manager.handle_event(event)
        print("[测试 7] ✗ 失败 - 未抛出异常")
    except AssertionError as e:
        print("[测试 7] ✓ 通过 - 正确抛出异常: ", str(e))

"""测试查询接口"""

def test_get_active_tasks():
    task_manager = TaskManager[str, str, str]()
    print("\n[测试 8] 测试获取活跃任务列表")
    task_manager.handle_event(TaskStartEvent(task_id="task_001"))
    task_manager.handle_event(TaskStartEvent(task_id="task_002"))

    task_manager.handle_event(TaskSuccessEvent(task_id="task_001", result="none"))

    active = task_manager.get_active_tasks()
    assert len(active) == 1
    assert active[0].task_id == "task_002"
    print("[测试 8] ✓ 通过 - 活跃任务数量: ", len(active), "，任务ID: ", active[0].task_id)


def main():
    test_handle_start_success()
    test_handle_progress_success()
    test_handle_success_success()
    test_handle_failure_success()
    test_handle_cancelled_success()
    test_start_existing_task_raises()
    test_progress_nonexistent_task_raises()
    test_get_active_tasks()
    
if __name__ == "__main__":
    main()