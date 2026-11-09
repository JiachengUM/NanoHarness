import asyncio

from aicore.agents.experiments.ralph import (
    nl_repr,
    ModelParams,
    StructuredGoal,
    GoalLike,
    ralph_loop, 
    ReActExecutor,
    LMEvaluator,
    RalphReActEventPrinter,
)
from aicore.models.doubao_models import ModelName

GOALS = [
    (
        "量子力学是什么？",
        StructuredGoal(
            description="量子力学是什么？",
            criteria = ["请详细解释。不少于100字。"]
            ) 
    ),
    (
        "介绍最新的美国伊朗战争的战况",
        StructuredGoal(
            description="介绍最新的美国伊朗战争的战况",
            criteria = ["战况必须是最新的2026年4月的。务必查阅实时的新闻报道。"]
            )
    ),
]

executor = ReActExecutor(params=ModelParams(model=ModelName.SEED_1_8_251228), guideline="回答请简明扼要。")

evaluator = LMEvaluator(params=ModelParams(model=ModelName.SEED_1_8_251228))


async def test_ralph_loop_basic(goal: GoalLike):
    printer = RalphReActEventPrinter()

    async for event in ralph_loop(goal, executor, evaluator, max_turns=2):
        printer(event)
    
async def main():
    print(f"\n简单任务: {GOALS[1][0]}")
    await test_ralph_loop_basic(GOALS[1][0])   # 简单，ralph loop一次就完成
    
    print(f"\n结构化任务: {nl_repr(GOALS[1][1])}")
    await test_ralph_loop_basic(GOALS[1][1])   # goal和executor矛盾。

if __name__ == "__main__":
    asyncio.run(main())