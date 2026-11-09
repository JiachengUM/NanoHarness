# eval_tools/poi_compare/runner.py
"""
Runner：顺序执行每个case（ReAct then Ralph），保存ExperimentRecord列表到results.json。
顺序执行（非并发）以避免amap API限速和缓存差异带来的干扰。
"""
import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rich import print

from aicore.agents.experiments.ralph import (
    ReActExecutor,
    LMEvaluator,
    ModelParams,
    NotePad,             # 定义在ralph.py，非__all__但可直接import
    ReActTrajectory,     # 定义在ralph.py
    ralph_loop,
    RalphExecuteEvent,
    RalphFinishedEvent,  # 定义在ralph.py
)
from aicore.agents.react import ToolCallStartEvent
from aicore.models.credentials import ModelName
from aicore.tools.experiments.poi_search import create_poi_search_tool
from aicore.utils.nl_repr import nl_repr
from projects.mind.toolset.poi_search import SGMPoiWorker

from eval_tools.poi_compare.models import ExperimentRecord
from eval_tools.poi_compare.judger import judge

CASES_PATH = Path(__file__).parent / "cases.json"
RESULTS_PATH = Path(__file__).parent / "results_evaluator_v2.json"

MODEL = ModelName.SEED_1_8_251228
REACT_MAX_TURNS = 5
RALPH_MAX_TURNS = 2  # 每轮内 ReAct max_turns=5，最多 2×5=10 步


async def run_react(goal: str, executor: ReActExecutor) -> tuple[str, int, str]:
    """直接运行ReActExecutor，不经过ralph_loop，返回(输出文本, 实际steps数, 可读轨迹)。"""
    notepad = NotePad[str, ReActTrajectory]()
    async for _ in executor(goal, notepad):
        pass
    output, traj = executor.finish()
    tool_call_steps = sum(1 for e in traj.events if isinstance(e, ToolCallStartEvent))
    return output, tool_call_steps, nl_repr(traj)


async def run_ralph(goal: str, executor: ReActExecutor, evaluator: LMEvaluator) -> tuple[str, int, list[str]]:
    """通过ralph_loop运行，返回(最终输出文本, 实际使用轮数1-indexed, 每轮可读轨迹)。"""
    final_output = ""
    final_round = 1  # 默认至少1轮
    notepad = NotePad[str, ReActTrajectory]()
    trajectories: list[str] = []

    async for event in ralph_loop(goal, executor, evaluator, notepad=notepad, max_turns=RALPH_MAX_TURNS):
        if isinstance(event, RalphExecuteEvent) and notepad.traj is not None:
            trajectories.append(nl_repr(notepad.traj))
        if isinstance(event, RalphFinishedEvent):
            final_output = event.result
            final_round = event.round + 1  # round是0-indexed

    if not final_output:
        raise RuntimeError("ralph_loop ended without RalphFinishedEvent — evaluator may have failed")

    return final_output, final_round, trajectories


async def run_case(case: dict) -> ExperimentRecord:
    """对单个case运行ReAct和Ralph，返回ExperimentRecord。"""
    goal = case["goal"]
    expected = case["expected"]
    params = ModelParams(model=MODEL)

    # 1. 运行ReAct（独立executor实例和poi_tool实例）
    print(f"  [ReAct] running...")
    react_executor = ReActExecutor(params=params, tools=[create_poi_search_tool(SGMPoiWorker())], max_turns=REACT_MAX_TURNS)
    react_output, react_steps, react_trajectory = await run_react(goal, react_executor)
    react_result = await judge(goal, react_output, expected)
    print(f"  [ReAct] score={react_result.score} pass={react_result.pass_fail} steps={react_steps}")

    # 2. 运行Ralph（独立executor实例和poi_tool实例，避免状态污染）
    print(f"  [Ralph] running...")
    ralph_executor = ReActExecutor(params=params, tools=[create_poi_search_tool(SGMPoiWorker())], max_turns=REACT_MAX_TURNS)
    evaluator = LMEvaluator(params=params)
    ralph_output, ralph_rounds, ralph_trajectories = await run_ralph(goal, ralph_executor, evaluator)
    ralph_result = await judge(goal, ralph_output, expected)
    print(f"  [Ralph] score={ralph_result.score} pass={ralph_result.pass_fail} rounds={ralph_rounds}")

    return ExperimentRecord(
        case_id=case["id"],
        dimension=case["dimension"],
        level=case["level"],
        goal=goal,
        expected=expected,
        react_output=react_output,
        react_result=react_result,
        react_steps=react_steps,
        react_trajectory=react_trajectory,
        ralph_output=ralph_output,
        ralph_result=ralph_result,
        ralph_rounds=ralph_rounds,
        ralph_trajectories=ralph_trajectories,
    )


async def run_all(
    cases_path: Path = CASES_PATH,
    results_path: Path = RESULTS_PATH,
    case_ids: list[str] | None = None,
) -> list[ExperimentRecord]:
    """
    运行所有（或指定）case，结果保存到results.json。
    case_ids: 若指定，只运行该列表中的case（用于单case调试）。
    """
    with open(cases_path) as f:
        cases = json.load(f)

    if case_ids:
        cases = [c for c in cases if c["id"] in case_ids]

    records: list[ExperimentRecord] = []
    for i, case in enumerate(cases, 1):
        print(f"\n[{i}/{len(cases)}] Case: {case['id']} — {case['goal'][:40]}")
        try:
            record = await run_case(case)
            records.append(record)
            # 每完成一个case立即写入，避免后续失败丢失进度
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump([r.model_dump() for r in records], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  [ERROR] Case {case['id']} failed: {e}")
            continue

    print(f"\nResults saved to {results_path}")
    return records


if __name__ == "__main__":
    asyncio.run(run_all())
