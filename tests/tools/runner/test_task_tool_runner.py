"""TaskToolRunner anyio thin wrapper 行为测试.

验证: runner 自身只做 Protocol 解读 + TaskToolDoneEvent 包装 + nl_repr 渲染.
core 接管异常, task.py 提供格式化后的 worker.

直接 python -m tests.tools.runner.test_task_tool_runner 运行.
"""

import sys

import anyio
from anyio import get_cancelled_exc_class

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from pydantic import BaseModel, Field
from rich import print

from aicore.tools import TaskTool
from aicore.tools.runner import TaskToolRunner
from aicore.events.react import TaskToolDoneEvent
from aicore.core.types import SafeResult


class _Input(BaseModel):
    x: str = Field(...)


def _make_tool(
    name: str,
    *,
    sleep: float = 0.0,
    value: str | None = None,
    raises: BaseException | None = None,
    timeout: float | None = None,
    on_error=None,
    on_cancel=None,
) -> TaskTool[_Input, str, None, ...]:
    val = value if value is not None else f"{name}-result"

    async def worker(x: str) -> str:
        try:
            await anyio.sleep(sleep)
        except get_cancelled_exc_class():
            if on_cancel is not None:
                on_cancel()
            raise
        if raises is not None:
            raise raises
        return val

    return TaskTool[_Input, str, None, ...](
        name=name,
        description="test",
        args_schema=_Input,
        worker=worker,
        timeout=timeout,
        on_error=on_error,
    )


async def test_completion_order_and_insertion_order():
    runner = TaskToolRunner()
    runner.add_tool(_make_tool("t1", sleep=0.3, value="A"), _Input(x="h"))
    runner.add_tool(_make_tool("t2", sleep=0.1, value="B"), _Input(x="h"))
    runner.add_tool(_make_tool("t3", sleep=0.2, value="C"), _Input(x="h"))

    yielded: list[str | None] = []
    async for event in runner.run():
        assert isinstance(event, TaskToolDoneEvent)
        assert isinstance(event.output, SafeResult)
        yielded.append(event.output.data)

    assert yielded == ["B", "C", "A"], f"完成顺序错: {yielded}"
    final = [r.data for r in runner.results]
    assert final == ["A", "B", "C"], f"插入顺序错: {final}"
    assert len(runner.tool_results) == 3
    print("[green]OK[/green] test_completion_order_and_insertion_order")


async def test_indexed_completion_order_and_insertion_order():
    runner = TaskToolRunner()
    runner.add_tool(_make_tool("t1", sleep=0.3, value="A"), _Input(x="h"))
    runner.add_tool(_make_tool("t2", sleep=0.1, value="B"), _Input(x="h"))
    runner.add_tool(_make_tool("t3", sleep=0.2, value="C"), _Input(x="h"))

    yielded: list[tuple[int, str | None]] = []
    async for idx, event in runner.run_indexed():
        assert isinstance(event, TaskToolDoneEvent)
        assert isinstance(event.output, SafeResult)
        yielded.append((idx, event.output.data))

    assert yielded == [(1, "B"), (2, "C"), (0, "A")], f"indexed 完成顺序错: {yielded}"
    final = [r.data for r in runner.results]
    assert final == ["A", "B", "C"], f"插入顺序错: {final}"
    print("[green]OK[/green] test_indexed_completion_order_and_insertion_order")


async def test_exception_isolated_via_core():
    runner = TaskToolRunner()
    runner.add_tool(_make_tool("ok1", sleep=0.05, value="hello"), _Input(x="h"))
    runner.add_tool(
        _make_tool("bad", sleep=0.1, raises=ValueError("oops")), _Input(x="h")
    )
    runner.add_tool(_make_tool("ok2", sleep=0.15, value="world"), _Input(x="h"))

    async for _ in runner.run():
        pass

    final = runner.results
    assert final[0].is_success and final[0].data == "hello"
    assert not final[1].is_success and "oops" in (final[1].error or "")
    assert final[2].is_success and final[2].data == "world"
    print("[green]OK[/green] test_exception_isolated_via_core")


async def test_timeout_message_propagates_to_safe_result():
    """task.py 格式化 'TimeoutError(任务 X 超时)' → core 接管 → SafeResult.error 含此字样."""
    runner = TaskToolRunner()
    runner.add_tool(_make_tool("quick", sleep=0.05, value="done"), _Input(x="h"))
    runner.add_tool(_make_tool("slow", sleep=5.0, timeout=0.1), _Input(x="h"))

    async for _ in runner.run():
        pass

    final = runner.results
    assert final[0].is_success and final[0].data == "done"
    assert not final[1].is_success
    assert final[1].error == "任务 slow 超时", f"消息错: {final[1].error}"
    print("[green]OK[/green] test_timeout_message_propagates_to_safe_result")


async def test_on_error_propagates_to_safe_result():
    """on_error 经 task.py 格式化 → RuntimeError → core 取 str(e) → SafeResult.error."""
    runner = TaskToolRunner()
    runner.add_tool(
        _make_tool(
            "bad",
            sleep=0.01,
            raises=ValueError("boom"),
            on_error=lambda e: f"自定义[{type(e).__name__}]",
        ),
        _Input(x="h"),
    )

    async for _ in runner.run():
        pass

    final = runner.results
    assert not final[0].is_success
    assert final[0].error == "自定义[ValueError]"
    print("[green]OK[/green] test_on_error_propagates_to_safe_result")


async def test_consumer_break_cancels_workers():
    cancelled: list[str] = []
    runner = TaskToolRunner()
    runner.add_tool(_make_tool("quick", sleep=0.05, value="first"), _Input(x="h"))
    runner.add_tool(
        _make_tool("slow", sleep=10.0, on_cancel=lambda: cancelled.append("slow")),
        _Input(x="h"),
    )

    gen = runner.run()
    first = await gen.__anext__()
    assert first.output.data == "first"
    await gen.aclose()

    assert cancelled == ["slow"], f"slow 应被取消: {cancelled}"
    print("[green]OK[/green] test_consumer_break_cancels_workers")


async def main():
    await test_completion_order_and_insertion_order()
    await test_indexed_completion_order_and_insertion_order()
    await test_exception_isolated_via_core()
    await test_timeout_message_propagates_to_safe_result()
    await test_on_error_propagates_to_safe_result()
    await test_consumer_break_cancels_workers()
    print("\n[bold green]全部通过[/bold green]")


if __name__ == "__main__":
    anyio.run(main)
