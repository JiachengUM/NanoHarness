"""手动验证 aicore/agents/plan/plan_dag_runner.py 的 _resolve_ref / _resolve_value jq path 投影行为。

放在 tests/ 下但文件名不以 test_ 开头，不参与 pytest 收集（pytest.ini python_files = test_*.py）。

Run directly:
    uv run python -m tests.agents.verify_ref_resolution
"""

import re
from typing import Any, Callable

from rich.console import Console
from rich.pretty import Pretty

console = Console()

from aicore.agents.plan.plan_dag_runner import PlanDAGRunner

RUNTIME_STATE: dict[str, Any] = {
    "s1": {
        "inputs": {},
        "outputs": {
            "LightMusicSong": [
                {"play_id": "id1", "title": "song1"},
                {"play_id": "id2", "title": "song2"},
                {"play_id": "id3", "title": "song3"},
            ],
        },
    },
    "s2": {
        "inputs": {},
        "outputs": {
            "EmptyList": [],
        },
    },
}


def _runner() -> PlanDAGRunner:
    runner = PlanDAGRunner(tools=[])
    runner._runtime_state = RUNTIME_STATE
    return runner


_PATH_RE = re.compile(r"\.(s\d+)\.outputs\b")


def _referenced_context(expr: str) -> dict[str, Any]:
    """从表达式里提取引用到的 step_id，返回 RUNTIME_STATE 中对应的子集，作为输入上下文展示。"""
    step_ids: list[str] = []
    for step_id in _PATH_RE.findall(expr):
        if step_id in RUNTIME_STATE and step_id not in step_ids:
            step_ids.append(step_id)
    return {step_id: RUNTIME_STATE[step_id] for step_id in step_ids}


def _resolved(result: tuple[Any, Any]) -> tuple[Any, str | None]:
    value, error = result
    return value, error.kind if error is not None else None


# 每条用例：(label, ref/value 表达式, thunk(runner, expr) -> actual, expected)
CASES: list[tuple[str, str, Callable[[PlanDAGRunner, str], Any], Any]] = [
    (
        "array iterator fullmatch ref -> 原始 list，顺序与上游一致",
        ".s1.outputs.LightMusicSong[].play_id",
        lambda r, e: _resolved(r._resolve_ref_result(e, "s_test")),
        (["id1", "id2", "id3"], None),
    ),
    (
        "index ref 回归（非迭代路径不受影响）",
        ".s1.outputs.LightMusicSong[0].play_id",
        lambda r, e: _resolved(r._resolve_ref_result(e, "s_test")),
        ("id1", None),
    ),
    (
        "array iterator fullmatch resolve_value -> 结构化字段保持 list 类型，不转字符串",
        "{{ .s1.outputs.LightMusicSong[].play_id }}",
        lambda r, e: _resolved(r._resolve_value(e, "s_test")),
        (["id1", "id2", "id3"], None),
    ),
    (
        "array iterator 嵌入字符串 -> nl_repr(separator=', ', use_numbering=False) 拼接",
        "把这些歌按顺序整理成歌单播放：{{ .s1.outputs.LightMusicSong[].play_id }}",
        lambda r, e: _resolved(r._resolve_value(e, "s_test")),
        ("把这些歌按顺序整理成歌单播放：id1, id2, id3", None),
    ),
    (
        "array iterator 命中空列表 -> input_ref error",
        ".s2.outputs.EmptyList[].play_id",
        lambda r, e: _resolved(r._resolve_ref_result(e, "s_test")),
        (None, "input_ref"),
    ),
    (
        "array iterator 命中空列表嵌入字符串 -> input_ref error",
        "歌单：{{ .s2.outputs.EmptyList[].play_id }}",
        lambda r, e: _resolved(r._resolve_value(e, "s_test")),
        ("歌单：", "input_ref"),
    ),
    (
        "未命中路径 -> input_ref error，嵌入字符串时替换为空字符串",
        "结果：{{ .s1.outputs.Missing[].play_id }}",
        lambda r, e: _resolved(r._resolve_value(e, "s_test")),
        ("结果：", "input_ref"),
    ),
]


def main() -> None:
    all_ok = True
    runner = _runner()

    for label, expr, thunk, expected in CASES:
        actual = thunk(runner, expr)

        console.print(f"\n[bold]{label}[/bold]  [dim]{expr!r}[/dim]")
        console.rule(style="dim")
        console.print(Pretty(_referenced_context(expr)))

        ok = actual == expected
        all_ok = all_ok and ok
        status = "[green]OK[/green]" if ok else "[red]MISMATCH[/red]"
        console.print(f"actual={actual!r} {status}")

    console.print()
    console.print(
        "[bold green]all cases matched[/bold green]"
        if all_ok
        else "[bold red]some cases mismatched[/bold red]"
    )


if __name__ == "__main__":
    main()
