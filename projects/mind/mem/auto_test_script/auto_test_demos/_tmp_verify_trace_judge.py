"""验证 trace 注入裁判后，助手口头简略回复（如"没问题"）不再被误扣分。

目标数据集：奔驰无车控多轮
核心验证点：助手实际执行了操作但口头只说"没问题"等简略回复时，
            裁判应结合 trace 判 Pass，而非仅因口头简略判 Fail。

运行（d:\yitu_projects\nanoai 为 cwd）：
  D:\apps\miniconda\envs\dzy_env\python.exe projects\mind\mem\auto_test_script\auto_test_demos\_tmp_verify_trace_judge.py
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

DATASET_NAME = "奔驰无车控多轮"


def main() -> None:
    cases = get_dataset_list_sync([DATASET_NAME])
    print(f"\n========== 数据集: {DATASET_NAME} 共 {len(cases)} 条 ==========")
    # 筛选多轮 case（user_query_lists 有多段，或 expected_script 有多轮"用户："）
    candidates = []
    for c in cases:
        es = c.expected_script or ""
        # 多轮对话：expected_script 里"用户："出现≥2次
        if es.count("用户：") >= 2 or es.count("用户:") >= 2:
            candidates.append(c)
    print(f"多轮 case 数: {len(candidates)}")
    for c in candidates[:8]:
        print(f"  - {c.case_id} | max_round={c.max_round} | 用户行数={ (c.expected_script or '').count('用户：') + (c.expected_script or '').count('用户:') }")
    # 取前 3 个候选跑，观察助手实际回复是否有简略情况
    assert candidates, "未找到多轮 case"
    target = candidates[:3]
    print(f"\n========== 锁定 {len(target)} 个目标 case ==========")
    for t in target:
        print(f"\n--- Case: {t.case_id} | max_round={t.max_round} ---")
        print(f"冷启动台词: {t.user_query_lists[0][0].content}")
        print(f"expected_script:\n{t.expected_script}")
    print("=" * 80)

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=target,
        verbose=True,
        log_dialogue=True,
        show_progress=False,
        test_mode="api",  # 这个问题与 voice 无关，api 模式就有
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
        )


if __name__ == "__main__":
    main()
