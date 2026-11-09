"""TaskAsyncRunner 版功能测试.

直接 python -m tests.core.test_task_runner 运行.
"""

import sys

from typing import Awaitable, Callable

import anyio

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
from anyio import get_cancelled_exc_class

from rich import print

from aicore.core.anyio.task_runner import TaskAsyncRunner
from aicore.core.types import SafeResult


def make_factory(
    sleep: float,
    value: str | None = None,
    raises: BaseException | None = None,
    on_cancel: Callable[[], None] | None = None,
) -> Callable[[], Awaitable[str | None]]:
    async def factory():
        try:
            await anyio.sleep(sleep)
        except get_cancelled_exc_class():
            if on_cancel is not None:
                on_cancel()
            raise
        if raises is not None:
            raise raises
        return value

    return factory


async def test_completion_and_insertion_order():
    runner = TaskAsyncRunner()
    runner.add_task(make_factory(sleep=0.3, value="A"))
    runner.add_task(make_factory(sleep=0.1, value="B"))
    runner.add_task(make_factory(sleep=0.2, value="C"))

    yielded: list[str | None] = []
    async for safe in runner.run():
        assert isinstance(safe, SafeResult)
        yielded.append(safe.data)

    assert yielded == ["B", "C", "A"], f"完成顺序错: {yielded}"
    final = [r.data for r in runner.results]
    assert final == ["A", "B", "C"], f"插入顺序错: {final}"
    print("[green]OK[/green] test_completion_and_insertion_order")


async def test_indexed_completion_order_and_insertion_order():
    runner = TaskAsyncRunner()
    runner.add_task(make_factory(sleep=0.3, value="A"))
    runner.add_task(make_factory(sleep=0.1, value="B"))
    runner.add_task(make_factory(sleep=0.2, value="C"))

    yielded: list[tuple[int, str | None]] = []
    async for idx, safe in runner.run_indexed():
        assert isinstance(safe, SafeResult)
        yielded.append((idx, safe.data))

    assert yielded == [(1, "B"), (2, "C"), (0, "A")], f"indexed 完成顺序错: {yielded}"
    final = [r.data for r in runner.results]
    assert final == ["A", "B", "C"], f"插入顺序错: {final}"
    print("[green]OK[/green] test_indexed_completion_order_and_insertion_order")


async def test_factory_exception_isolated():
    runner = TaskAsyncRunner()
    runner.add_task(make_factory(sleep=0.05, value="ok1"))
    runner.add_task(make_factory(sleep=0.10, raises=ValueError("oops")))
    runner.add_task(make_factory(sleep=0.15, value="ok2"))

    async for _ in runner.run():
        pass

    final = runner.results
    assert final[0].is_success and final[0].data == "ok1"
    assert not final[1].is_success and "oops" in (final[1].error or "")
    assert final[2].is_success and final[2].data == "ok2"
    print("[green]OK[/green] test_factory_exception_isolated")


async def test_consumer_break_cancels_pending():
    cancelled: list[str] = []

    runner = TaskAsyncRunner()
    runner.add_task(make_factory(sleep=0.05, value="first"))
    runner.add_task(
        make_factory(sleep=10.0, on_cancel=lambda: cancelled.append("slow"))
    )

    gen = runner.run()
    first = await gen.__anext__()
    assert first.data == "first"
    await gen.aclose()

    assert cancelled == ["slow"], f"slow 应被取消, 实际: {cancelled}"
    try:
        _ = runner.results
        assert False, "中途 break 后不应允许读 results"
    except RuntimeError:
        pass
    print("[green]OK[/green] test_consumer_break_cancels_pending")


async def test_double_run_rejected():
    runner = TaskAsyncRunner()
    runner.add_task(make_factory(sleep=0.01, value="x"))
    async for _ in runner.run():
        pass

    raised = False
    try:
        async for _ in runner.run():
            pass
    except AssertionError:
        raised = True
    assert raised

    raised = False
    try:
        runner.add_task(make_factory(sleep=0.01, value="y"))
    except RuntimeError:
        raised = True
    assert raised
    print("[green]OK[/green] test_double_run_rejected")


async def test_empty_runner_rejected():
    runner = TaskAsyncRunner()
    raised = False
    try:
        async for _ in runner.run():
            pass
    except AssertionError:
        raised = True
    assert raised
    print("[green]OK[/green] test_empty_runner_rejected")


async def main():
    await test_completion_and_insertion_order()
    await test_indexed_completion_order_and_insertion_order()
    await test_factory_exception_isolated()
    await test_consumer_break_cancels_pending()
    await test_double_run_rejected()
    await test_empty_runner_rejected()
    print("\n[bold green]全部通过[/bold green]")


if __name__ == "__main__":
    anyio.run(main)
