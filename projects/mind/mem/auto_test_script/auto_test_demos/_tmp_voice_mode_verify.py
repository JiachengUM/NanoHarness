"""voice 模式验证脚本：跑单个 case，观察假人是否会自主构建导航前置。

目标 case：叶子标签用例-设为途经点
核心验证点：car_info 里导航状态为"未启动"，冷启动台词仅为"设为途经点"，
假人理应意识到需要先有导航目的地，主动先发起导航，再设途经点。

运行（d:\yitu_projects\nanoai 为 cwd）：
  D:\apps\miniconda\envs\dzy_env\python.exe projects\mind\mem\auto_test_script\auto_test_demos\_tmp_voice_mode_verify.py
"""
import asyncio
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_auto_test import (
    DemoAgentV1Bot,
)
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list_sync,
)

DATASET_NAME = "奔驰remark_非VF车控数据_第二份_cases_part1"
TARGET_CASE_ID = "叶子标签用例-设为途经点"


def main() -> None:
    # 注意：get_dataset_list_sync 传 str 时内部有 bug（会按字符迭代），这里传列表绕过
    cases = get_dataset_list_sync([DATASET_NAME])
    target = [c for c in cases if c.case_id == TARGET_CASE_ID]
    assert target, f"未找到 case_id={TARGET_CASE_ID!r}"
    print(f"\n========== 已锁定目标 case: {TARGET_CASE_ID} ==========")
    print(f"car_info:\n{target[0].context_config.get('car_info')}")
    print(f"冷启动台词: {target[0].user_query_lists[0][0].content}")
    print(f"max_round: {target[0].max_round}")
    print("=" * 80)

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=target,
        verbose=True,
        log_dialogue=True,
        show_progress=False,
        test_mode="voice",
    )

    async def _run() -> RunAllCasesResult | None:
        final: RunAllCasesResult | None = None
        async for item in auto_test.arun_full_auto_judge_test(
            concurrency_mode=False,
            pause_mode=False,
            memory_reset_mode=False,
            upload_history_to_volc_memory=False,
            epoch=1,
        ):
            if isinstance(item, RunCaseResult):
                print("\n" + "=" * 80)
                print(f"[结果] Case: {item.case_id}")
                print(f"[结果] Passed: {item.is_passed}")
                print(f"[结果] Execution success: {item.execution_success}")
                if item.execution_error:
                    print(f"[结果] Execution error: {item.execution_error}")
                print(f"[结果] Reason:\n{item.reason}")
                print("\n--- 完整对话历史 (history_for_judge) ---")
                print(item.history_for_judge)
                print("=" * 80)
            elif isinstance(item, RunAllCasesResult):
                final = item
        return final

    result = asyncio.run(_run())
    if result is not None:
        print(
            f"\n========== 最终汇总 ==========\n"
            f"总数: {result.total_case_num}\n"
            f"通过: {result.passed_case_num}\n"
            f"通过率: {result.pass_rate}\n"
            f"执行成功: {result.execution_success_num}\n"
            f"执行成功率: {result.execution_success_rate}"
        )


if __name__ == "__main__":
    main()
