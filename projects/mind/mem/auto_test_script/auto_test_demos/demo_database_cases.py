"""device_v1 持久化画像的最终状态评估 demo。

同一条真实 LLM Agent + FakePerson 对话，同时比较：

1. 现有 LLM Judge 根据对话/trace 给出的自然语言断言结果；
2. 对话落库后直接查询火山 ``device_v1`` 画像，对最终持久化对象做确定性断言。

运行前提：目标火山 collection 已配置截图所示 ``device_v1`` 画像抽取规则。

运行：
    .venv/bin/python \
        projects/mind/mem/auto_test_script/auto_test_demos/demo_database_cases.py
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rich import print

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_auto_test import (
    DemoAgentV1Bot,
    example_input_params,
)
from projects.mind.mem.auto_test_script.case_schema import (
    DialogueRoundConfig,
    TestCase,
)
from projects.mind.mem.volc_api import (
    CollectionID,
    Message,
    asearch_profile_memory,
)


DEVICE_PROFILE_TYPE = "device_v1"
REPORT_DIR = Path(__file__).resolve().parent.parent / "auto_test_report"
COMPARE_REPORT_PATH = REPORT_DIR / "device_v1_evaluation_comparison_v2.json"
DATASET_NAMES = ["device_v1 最终画像状态评估 demo"]


def _context() -> dict[str, Any]:
    """启用 device_v1 生产与消费；每个 case 的 user_id 仍由执行器改为 case_id。"""
    result = example_input_params.model_dump(exclude_none=True)
    result.update(
        {
            "profile_types": [DEVICE_PROFILE_TYPE],
            "system_prompt_profile_types": [DEVICE_PROFILE_TYPE],
            "search_profile_types": [DEVICE_PROFILE_TYPE],
            "user_profile": "用户希望车载助手长期记住其设备调节偏好。",
            "car_info": "当前车辆支持空调温度、风量和制热/制冷模式调节。",
        }
    )
    return result


# code_assertion 是本 demo 自己解释的最简 device_v1 断言 DSL。
DATABASE_CASES = [
    TestCase(
        id="device-v1-create-winter-climate-preference",
        case_id="device_v1创建冬季空调偏好v2",
        context_config=_context(),
        max_round=4,
        user_query_lists=[[
            Message(
                role="user",
                content=(
                    "请长期记住我的空调习惯：冬天开车时设为28度、风量1档、制热。"
                    "以后冬天我没说具体参数时，希望你自动使用这套偏好。"
                ),
            )
        ]],
        expected_script="""
用户：请长期记住我的空调习惯：冬天开车时设为28度、风量1档、制热。以后冬天我没说具体参数时，希望你自动使用这套偏好。
助手：确认已记录冬季空调偏好和自动应用意愿。
用户：好的，这就是我的长期偏好。
助手：确认。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "助手应正确理解并确认冬天空调28度、风量1档、制热的长期偏好。",
            "助手应理解用户希望在未给出明确参数时自动应用该偏好。",
        ],
        code_assertion={
            "device_type": "空调",
            "condition": "冬天",
            "target_temperature": 28,
            "fan_level": "1档",
            "work_mode": "制热",
            "auto_apply": "是",
            "matching_preference_count": 1,
        },
        case_description=(
            "自然语言回复正确不代表画像真的创建成功；最终须在 device_v1 中找到完整且唯一的偏好对象。"
        ),
        tags=["device_v1", "持久化对象", "创建画像"],
    ),
    TestCase(
        id="device-v1-update-winter-climate-preference",
        case_id="device_v1修改偏好且不产生新旧冲突v2",
        context_config=_context(),
        max_round=4,
        user_query_lists=[
            DialogueRoundConfig(
                user_query_list=[Message(
                    role="user",
                    content=(
                        "请长期记住：冬天开车时空调28度、风量1档、制热，"
                        "没有明确参数时自动应用。"
                    ),
                )],
                mock_time="2026-08-12 09:00:00",
            ),
            DialogueRoundConfig(
                user_query_list=[Message(
                    role="user",
                    content=(
                        "我发现冬天28度太热了。请把之前那条冬天空调偏好改成25度、风量2档；"
                        "仍然制热，仍然允许自动应用。不要另外新增一条。"
                    ),
                )],
                mock_time="2026-08-13 09:00:00",
            ),
        ],
        expected_script="""
用户（第一次独立会话）：请长期记住冬天空调28度、风量1档、制热，并允许自动应用。
助手：确认已记录。
用户：谢谢，退下吧，我给你打5分。

用户（第二次独立会话）：28度太热了，把之前那条冬天空调偏好改成25度、风量2档；仍然制热和自动应用，不要新增一条。
助手：识别这是修改已有偏好，确认更新而不是创建并存的新偏好。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "助手应理解第二次请求是修改已有冬季空调偏好，而不是新增另一条并存偏好。",
            "最终有效偏好应为冬天25度、风量2档、制热并允许自动应用。",
            "旧的冬天28度、风量1档偏好不应继续作为有效偏好存在。",
        ],
        code_assertion={
            "device_type": "空调",
            "condition": "冬天",
            "target_temperature": 25,
            "fan_level": "2档",
            "work_mode": "制热",
            "auto_apply": "是",
            "matching_preference_count": 1,
            "forbidden_preferences": [
                {"condition": "冬天", "target_temperature": 28, "fan_level": "1档"}
            ],
        },
        case_description=(
            "助手口头说‘已修改’时，LLM Judge 很难知道后台是覆盖旧对象还是追加了冲突对象；"
            "最终 device_v1 状态可以直接检查新值、旧值消失和唯一性。"
        ),
        tags=["device_v1", "持久化对象", "修改画像", "冲突消解"],
    ),
]


@dataclass
class DeviceV1EvaluationResult:
    case_id: str
    passed: bool
    assertions: dict[str, Any]
    assertion_results: dict[str, bool]
    raw_profiles: list[dict[str, Any]] = field(default_factory=list)
    normalized_devices: list[dict[str, Any]] = field(default_factory=list)


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _normalize_device_profile(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """容忍 memory_info 外层是单对象或 device_v1 schema 定义的数组。"""
    candidates: Any = raw
    for key in ("device_profile", "device_v1", "设备画像", "设备偏好"):
        if isinstance(candidates, dict) and key in candidates:
            candidates = candidates[key]
            break
    # 火山 device_v1 实际返回形态为
    # memory_info={"device_profile": "{...严格 JSON...}"}，先解码内层字符串。
    if isinstance(candidates, str):
        try:
            candidates = json.loads(candidates)
        except json.JSONDecodeError:
            return []
    if isinstance(candidates, dict):
        candidates = [candidates]
    if not isinstance(candidates, list):
        return []

    devices: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        device_info = _first(item, "设备信息", "device_info") or {}
        preferences = _first(item, "调节偏好", "preferences") or []
        auto_info = _first(item, "自动应用意愿", "auto_apply_preference") or {}
        if isinstance(preferences, dict):
            preferences = [preferences]
        devices.append(
            {
                "device_type": _first(device_info, "设备类型", "device_type"),
                "auto_apply": _first(auto_info, "自动应用", "auto_apply"),
                "preferences": [
                    {
                        "condition": _first(pref, "调节条件", "condition"),
                        "target_temperature": _first(pref, "目标温度", "target_temperature"),
                        "fan_level": _first(pref, "风量档位", "fan_level"),
                        "work_mode": _first(pref, "工作模式", "work_mode"),
                    }
                    for pref in preferences
                    if isinstance(pref, dict)
                ],
            }
        )
    return devices


def _canonical_scalar(key: str, value: Any) -> Any:
    """消除画像抽取中不影响业务语义的表述差异。"""
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    if key == "fan_level":
        return normalized.replace(" ", "")
    if key == "condition" and normalized in {"冬天", "冬天开车时", "冬季", "冬季开车时"}:
        return "冬天"
    return normalized


async def _read_device_v1_profiles(case: TestCase) -> list[dict[str, Any]]:
    """轮询真实画像库，容忍异步抽取/索引延迟。"""
    cfg = case.context_config
    last_rows: list[dict[str, Any]] = []
    for attempt in range(6):
        response = await asearch_profile_memory(
            collection_id=CollectionID(collection_name=cfg["collection_name"]),
            profile_type=[DEVICE_PROFILE_TYPE],
            user_id=str(cfg.get("user_id") or case.case_id),
            query=None,
            assistant_id=cfg.get("assistant_id"),
            limit=50,
        )
        last_rows = [dict(item.memory_info or {}) for item in response.data.result_list]
        if last_rows:
            return last_rows
        if attempt < 5:
            await asyncio.sleep(5)
    return last_rows


def _preference_matches(preference: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(
        _canonical_scalar(key, preference.get(key)) == _canonical_scalar(key, value)
        for key, value in expected.items()
    )


def evaluate_device_v1_final_state(
    case: TestCase,
    raw_profiles: list[dict[str, Any]],
) -> DeviceV1EvaluationResult:
    devices = [
        device
        for raw in raw_profiles
        for device in _normalize_device_profile(raw)
    ]
    assertions = dict(case.code_assertion or {})
    expected_preference = {
        key: assertions[key]
        for key in ("condition", "target_temperature", "fan_level", "work_mode")
        if key in assertions
    }
    target_devices = [
        device for device in devices if device.get("device_type") == assertions.get("device_type")
    ]
    matching_preferences = [
        pref
        for device in target_devices
        for pref in device.get("preferences", [])
        if _preference_matches(pref, expected_preference)
    ]
    forbidden = assertions.get("forbidden_preferences", [])
    forbidden_hits = [
        pref
        for device in target_devices
        for pref in device.get("preferences", [])
        if any(_preference_matches(pref, rule) for rule in forbidden)
    ]

    checks = {
        "device_exists": bool(target_devices),
        "expected_preference_exists": bool(matching_preferences),
        "matching_preference_count": (
            len(matching_preferences) == assertions.get("matching_preference_count", 1)
        ),
        "auto_apply": bool(target_devices)
        and all(device.get("auto_apply") == assertions.get("auto_apply") for device in target_devices),
        "forbidden_preferences_absent": not forbidden_hits,
    }
    return DeviceV1EvaluationResult(
        case_id=case.id,
        passed=all(checks.values()),
        assertions=assertions,
        assertion_results=checks,
        raw_profiles=raw_profiles,
        normalized_devices=devices,
    )


async def _run() -> tuple[RunAllCasesResult, list[dict[str, Any]]]:
    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=DATABASE_CASES,
        give_score=True,
        verbose=True,
        log_dialogue=True,
        show_progress=False,
    )
    cases_by_id = {case.id: case for case in DATABASE_CASES}
    comparisons: list[dict[str, Any]] = []
    final_result: RunAllCasesResult | None = None

    async for item in auto_test.arun_full_auto_judge_test(
        concurrency_mode=False,
        concurrency_num=1,
        pause_mode=False,
        # case_id 同时作为 user_id；先清空，确保创建/修改 case 有确定初态。
        memory_reset_mode=True,
        upload_history_to_volc_memory=False,
        memory_reset_except_skills=False,
        epoch=1,
        long_term_use=False,
    ):
        if isinstance(item, RunCaseResult):
            case = cases_by_id[item.id]
            raw_profiles = await _read_device_v1_profiles(case)
            db_result = evaluate_device_v1_final_state(case, raw_profiles)
            comparison = {
                "id": item.id,
                "llm_judge_passed": item.is_passed,
                "llm_judge_reason": item.reason,
                "device_v1_passed": db_result.passed,
                "assertions": db_result.assertions,
                "assertion_results": db_result.assertion_results,
                "normalized_devices": db_result.normalized_devices,
                "raw_profiles": db_result.raw_profiles,
            }
            comparisons.append(comparison)
            print(f"\n[bold]{item.case_id}[/bold]")
            print(f"LLM Judge: {'PASS' if item.is_passed else 'FAIL'}")
            print(f"device_v1: {'PASS' if db_result.passed else 'FAIL'}")
            print(f"状态断言: {db_result.assertion_results}")
            print(f"最终画像: {db_result.normalized_devices}")
        elif isinstance(item, RunAllCasesResult):
            final_result = item

    assert final_result is not None
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    COMPARE_REPORT_PATH.write_text(
        json.dumps(comparisons, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return final_result, comparisons


if __name__ == "__main__":
    result, comparisons = asyncio.run(_run())
    disagreements = sum(
        item["llm_judge_passed"] != item["device_v1_passed"]
        for item in comparisons
    )
    print(
        f"\n完成 {result.total_case_num} 条；LLM/device_v1 结论不一致 {disagreements} 条。"
    )
    print(f"对比报告：{COMPARE_REPORT_PATH}")
