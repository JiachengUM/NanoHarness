"""导出 trace 数据为 JSON，供 visualizer/index.html 可视化显示。

用法：
    # 跑完一次测试后，手动导出：
    from visualizer.export_trace import export_trace_json
    trace_json = export_trace_json(case, trace_recorder, judge_verdict)
    with open("trace.json", "w", encoding="utf-8") as f:
        json.dump(trace_json, f, ensure_ascii=False, indent=2)

    # 然后打开 visualizer/index.html 即可可视化查看
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    StateCheckRecord,
    TraceRecorder,
    UtteranceRecord,
)
from projects.experiments.time_travel_auto_test.case_schema import TestCase
from projects.experiments.time_travel_auto_test.judge.models import JudgeVerdict
from projects.experiments.time_travel_auto_test.script_events.script_event import (
    FakePersonScriptEvent,
    VirtualCarPerformScriptEvent,
    VirtualCarStateCheckScriptEvent,
)


def export_trace_json(
    case: TestCase,
    recorder: TraceRecorder,
    verdict: JudgeVerdict | None = None,
) -> dict[str, Any]:
    """将 case + trace + judge 导出为可视化 JSON 格式。

    返回的 dict 可由 visualizer/index.html 的 SAMPLE_DATA 变量直接加载。
    """
    records = sorted(recorder.records, key=lambda x: x[0])
    t0 = records[0][0] if records else None

    events: list[dict[str, Any]] = []
    for ts, kind, record in records:
        offset = (ts - t0).total_seconds() if t0 else 0
        ev = {"offset_seconds": round(offset, 1), "type": _kind_to_type(kind)}

        if kind == RecordKind.FAKE_PERSON_SPEAK and isinstance(record, UtteranceRecord):
            ev["role"] = record.role.replace("fake_person:", "")
            ev["content"] = record.content
            ev["is_partial"] = record.is_partial
        elif kind == RecordKind.ASSISTANT_REPLY and isinstance(record, UtteranceRecord):
            ev["content"] = record.content
            ev["is_partial"] = record.is_partial
        elif kind == RecordKind.VIRTUAL_CAR_SET_STATE:
            ev["updated_fields"] = record.get("updated_fields", {}) if isinstance(record, dict) else {}
        elif kind == RecordKind.VIRTUAL_CAR_STATE_CHECK and isinstance(record, StateCheckRecord):
            ev["expected"] = record.expected_fields
            ev["actual"] = record.actual_fields
            ev["passed"] = record.passed
            if record.mismatches:
                ev["mismatches"] = record.mismatches
        elif kind == RecordKind.ACCELERATION:
            if isinstance(record, dict):
                from_t = record.get("from")
                to_t = record.get("to")
                ev["from_offset"] = round((from_t - t0).total_seconds() if t0 and from_t else 0, 1)
                ev["to_offset"] = round((to_t - t0).total_seconds() if t0 and to_t else 0, 1)
                ev["description"] = f"时间快进至 {to_t.strftime('%H:%M:%S') if to_t else '?'}（静默期间无对话活动）"

        elif kind == RecordKind.SYSTEM:
            if isinstance(record, dict):
                ev["description"] = record.get("description", record.get("kind", ""))

        events.append(ev)

    # 导出剧本事件（用于双列对比）
    script_events = _export_script_events(case)

    result: dict[str, Any] = {
        "case_info": {
            "id": case.id,
            "name": case.case_name,
            "description": case.case_description,
            "fake_persons": [
                {"role_id": p.role_id, "profile": p.profile} for p in case.fake_persons
            ],
            "car_info": dict(case.virtual_car.car_info),
        },
        "trace": {
            "t0": t0.isoformat() if t0 else None,
            "events": events,
        },
        "script_events": script_events,
    }

    if verdict is not None:
        result["judge"] = {
            "score": verdict.score,
            "overall_passed": verdict.overall_passed,
            "must_pass": {
                "passed": verdict.score_breakdown.must_pass_passed,
                "total": verdict.score_breakdown.must_pass_total,
            },
            "bonus": {
                "passed": verdict.score_breakdown.bonus_passed,
                "total": verdict.score_breakdown.bonus_total,
            },
            "state_checks": {
                "passed": verdict.score_breakdown.state_check_passed,
                "total": verdict.score_breakdown.state_check_total,
            },
            "summary": verdict.summary,
            "assertions": [
                {
                    "assertion": ar.assertion,
                    "type": "must_pass" if ar.assertion_type == "must_pass" else "bonus",
                    "passed": ar.passed,
                    "reasoning": ar.reasoning,
                    "evidence": ar.evidence,
                }
                for ar in verdict.assertion_results
            ],
        }

    return result


def _export_script_events(case: TestCase) -> list[dict[str, Any]]:
    """从 TestCase 的 script_events + state_check_assertions 导出剧本事件列表。"""
    events: list[dict[str, Any]] = []

    # 1. 剧本演绎事件
    for ev in case.script_events:
        offset = ev.event_t0_plus_timedelta.total_seconds() if ev.event_t0_plus_timedelta else None
        script_ev: dict[str, Any] = {"offset_seconds": round(offset, 1) if offset is not None else None}

        if isinstance(ev, FakePersonScriptEvent):
            script_ev["type"] = "script_fake_person_speak"
            script_ev["target"] = ev.target
            # 通过 action 获取 content（可能为 None 表示 LLM 自主生成）
            from projects.experiments.time_travel_auto_test.fake_person.models import (
                FakePersonSpeakPerformAction,
            )
            if isinstance(ev.action, FakePersonSpeakPerformAction):
                script_ev["content"] = ev.action.args.content
            else:
                script_ev["content"] = None
        elif isinstance(ev, VirtualCarPerformScriptEvent):
            script_ev["type"] = "script_car_set_state"
            script_ev["fields"] = ev.action.args.fields if hasattr(ev.action, "args") else {}
        else:
            script_ev["type"] = "script_unknown"

        events.append(script_ev)

    # 2. 状态检查断言
    for ev in case.virtual_car_state_check_assertions:
        offset = ev.event_t0_plus_timedelta.total_seconds() if ev.event_t0_plus_timedelta else None
        events.append({
            "offset_seconds": round(offset, 1) if offset is not None else None,
            "type": "script_state_check",
            "expected_fields": ev.action.args.expected_fields,
        })

    # 按时间偏移排序；边界驱动事件（offset_seconds=None）放在最前面
    events.sort(key=lambda e: e.get("offset_seconds") if e.get("offset_seconds") is not None else -1.0)
    return events


def _kind_to_type(kind: RecordKind) -> str:
    """将 RecordKind 映射为可视化类型名。"""
    kind_map = {
        RecordKind.FAKE_PERSON_SPEAK: "fake_person_speak",
        RecordKind.ASSISTANT_REPLY: "assistant_reply",
        RecordKind.VIRTUAL_CAR_SET_STATE: "car_state_change",
        RecordKind.VIRTUAL_CAR_STATE_CHECK: "state_check",
        RecordKind.ACCELERATION: "acceleration",
        RecordKind.SYSTEM: "system",
        RecordKind.TOOL_CALL: "tool_call",
        RecordKind.TOOL_RESULT: "tool_result",
        RecordKind.LONG_PAUSE: "long_pause",
    }
    return kind_map.get(kind, "unknown")


def export_trace_to_file(
    case: TestCase,
    recorder: TraceRecorder,
    verdict: JudgeVerdict | None,
    output_path: str,
) -> None:
    """导出并写入文件。"""
    data = export_trace_json(case, recorder, verdict)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[visualizer] trace 已导出到: {output_path}")