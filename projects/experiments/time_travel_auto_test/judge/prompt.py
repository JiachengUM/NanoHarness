"""Judge prompt 模板 + trace 文本渲染（与 fake_person/llm_prompt.py 对齐）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

from projects.experiments.time_travel_auto_test.case_runner.trace import (
    RecordKind,
    StateCheckRecord,
    TraceRecorder,
    UtteranceRecord,
)


# ---------------- trace 文本渲染 ----------------


def render_timeline_text(recorder: TraceRecorder) -> str:
    """把 TraceRecorder 渲染成带时间线的高可读文本。

    这是 Judge prompt 的核心输入——必须让 LLM 看懂时序演进语义。

    虚拟时间与真实时间 1:1 自然流逝：时间戳如实反映每个事件实际发生的时刻，
    话语是耗时说出来的（区间 = 开口时刻 → 说完时刻）。
    中立观察者模型：框架不打断被测助手——假人插话与助手回复可以
    在时间上重叠，重叠窗口渲染为"双方同时说话"切片块。

    格式示例：
        [T0 = 2025-01-03 18:00:00]（T0 = 2025-01-03 18:00:00 为首行）
        [T0] 假人(driver): 你好小涂，有点热，把空调打开吧。 (说了 2.3s)
        [T0 + 1.2s → T0 + 6.0s] 助手: 好的，已为您打开空调。 (首字延迟 1.2s, 说了 4.8s)
        ━━━ 双方同时说话 [T0 + 2.0s → T0 + 2.8s] ━━━
          助手（窗口内）: 已为您打…
          假人(driver)（窗口内）: 算了别讲了
        [T0 + 2.0s → T0 + 2.8s] 假人(driver): 算了别讲了 (说了 0.8s)
        [T0 + 3.0s → T0 + 3.4s] [工具] set_air_conditioner({"mode": "制冷"}) → ok (耗时 120ms)
        [T0 + 45s] 状态检查: 空调开启状态及模式 → 实际=制冷中, 期望=制冷中 [✓ 通过]
        [T0 → T0+7d] 时间快进（静默期间无对话活动）
        [T0 + 7d] 助手（主动）: 时间到了，您该开会了。
    """
    records = sorted(recorder.records, key=lambda x: x[0])
    if not records:
        return "(空 trace，没有任何事件记录)"

    t0 = records[0][0]
    lines: list[str] = [f"（T0 = {t0.isoformat()}）"]

    # 预处理 1：工具调用/返回配对合并（栈式，支持嵌套调用）
    merged_records = _merge_tool_records(records)

    # 预处理 2：双方同时说话的重叠窗口（含窗口内切片文字）
    overlap_blocks = _build_overlap_blocks(recorder, t0)
    overlap_idx = 0

    for ts, kind, record in merged_records:
        # 先输出已开始的重叠块（块起点 <= 当前记录时刻 → 排在该记录行之前）
        while overlap_idx < len(overlap_blocks) and overlap_blocks[overlap_idx][0] <= ts:
            lines.extend(overlap_blocks[overlap_idx][1])
            overlap_idx += 1

        if kind == RecordKind.FAKE_PERSON_SPEAK and isinstance(record, UtteranceRecord):
            role = record.role.replace("fake_person:", "假人(") + ")"
            if record.is_partial:
                partial = "（半截话，超时截断）"
            else:
                partial = ""
            interval = _fmt_interval(record.started_at, record.ended_at, t0)
            duration = record.speech_duration
            if duration is None and record.started_at and record.ended_at:
                duration = (record.ended_at - record.started_at).total_seconds()
            timing = f" (说了 {duration:.1f}s)" if duration and duration >= 0.1 else ""
            lines.append(f"{interval} {role}{partial}: {record.content}{timing}")

        elif kind == RecordKind.ASSISTANT_REPLY and isinstance(record, UtteranceRecord):
            if record.interrupted_by_barge_in:
                partial = "（半截话，被用户插话打断）"
            elif record.is_partial:
                partial = "（半截话，超时截断）"
            else:
                partial = ""
            interval = _fmt_interval(record.started_at, record.ended_at, t0)
            timing_parts = []
            if record.is_proactive:
                timing_parts.append("主动")
                if record.ttft is not None:
                    timing_parts.append(f"触发后 {record.ttft:.1f}s 开口")
            elif record.ttft is not None:
                timing_parts.append(f"首字延迟 {record.ttft:.1f}s")
            if record.started_at and record.ended_at:
                duration = (record.ended_at - record.started_at).total_seconds()
                if duration >= 0.1:
                    timing_parts.append(f"说了 {duration:.1f}s")
            timing = f" ({', '.join(timing_parts)})" if timing_parts else ""
            lines.append(f"{interval} 助手{partial}: {record.content}{timing}")

        elif kind == RecordKind.VIRTUAL_CAR_SET_STATE:
            fields = record.get("updated_fields", {}) if isinstance(record, dict) else {}
            fields_str = ", ".join(f"{k}={v}" for k, v in fields.items())
            lines.append(f"[{_fmt_offset_str(ts, t0)}] [车态变更] {fields_str}")

        elif kind == RecordKind.VIRTUAL_CAR_STATE_CHECK and isinstance(record, StateCheckRecord):
            mismatches_str = ""
            if record.mismatches:
                mismatches_str = ", 不匹配: " + json.dumps(
                    record.mismatches, ensure_ascii=False
                )
            expected_str = json.dumps(record.expected_fields, ensure_ascii=False)
            actual_str = json.dumps(record.actual_fields, ensure_ascii=False)
            verdict = "✓ 通过" if record.passed else "✗ 失败"
            lines.append(
                f"[{_fmt_offset_str(ts, t0)}] [状态检查] 期望={expected_str}, 实际={actual_str} "
                f"[{verdict}]{mismatches_str}"
            )

        elif kind == RecordKind.ACCELERATION:
            if isinstance(record, dict):
                from_t = record.get("from")
                to_t = record.get("to")
                lines.append(
                    f"[{_fmt_offset_str(ts, t0)}] [时间快进] 从 {_fmt_clock(from_t, t0)} 跳到 "
                    f"{_fmt_clock(to_t, t0)}（静默期间无对话活动）"
                )

        elif kind == RecordKind.SYSTEM:
            if isinstance(record, dict):
                lines.append(f"[{_fmt_offset_str(ts, t0)}] [系统事件] {record.get('description', record.get('kind', ''))}")

        elif kind == RecordKind.TOOL_CALL:
            # 已在 _merge_tool_records 中配对合并；未配对的落单调用在此渲染
            if isinstance(record, dict):
                tool_name = record.get("tool_name", "?")
                tool_args = record.get("tool_args", {})
                args_str = json.dumps(tool_args, ensure_ascii=False) if tool_args else ""
                lines.append(f"[{_fmt_offset_str(ts, t0)}] [工具调用] {tool_name}({args_str})（未返回）")

        elif kind == RecordKind.TOOL_MERGED:
            if isinstance(record, dict):
                call_ts = record["call_ts"]
                result_ts = record["result_ts"]
                interval = _fmt_interval(call_ts, result_ts, t0)
                tool_name = record.get("tool_name", "?")
                tool_args = record.get("tool_args", {})
                args_str = json.dumps(tool_args, ensure_ascii=False) if tool_args else ""
                duration_ms = record.get("duration_ms", 0) or 0
                result_str = _format_tool_result(record.get("result"))
                duration_str = f", 耗时 {duration_ms:.0f}ms" if duration_ms else ""
                lines.append(f"{interval} [工具] {tool_name}({args_str}) → {result_str}{duration_str}")

        elif kind == RecordKind.LONG_PAUSE:
            if isinstance(record, dict):
                pause_s = record.get("pause_seconds", 0)
                lines.append(f"[{_fmt_offset_str(ts, t0)}] ⚠ 流式停顿 {pause_s:.1f}s")

    # 收尾：剩余的重叠块（起点晚于所有记录时刻——理论上不会出现，兜底）
    while overlap_idx < len(overlap_blocks):
        lines.extend(overlap_blocks[overlap_idx][1])
        overlap_idx += 1

    return "\n".join(lines)


def _fmt_offset_str(ts: datetime, t0: datetime) -> str:
    """把时刻格式化为 [T0 + X] 形式的偏移量前缀内容（不含方括号）。"""
    offset = _format_offset(ts - t0)
    return f"T0 + {offset}" if offset != "0s" else "T0"


def _fmt_interval(started: datetime, ended: datetime, t0: datetime) -> str:
    """格式化话语/工具区间 [T0 + X → T0 + Y]；零长度区间退化为单时刻。"""
    start_off = _format_offset(started - t0)
    if abs((ended - started).total_seconds()) < 0.05:
        return f"[{_fmt_offset_str(started, t0)}]"
    end_off = _format_offset(ended - t0)
    start_prefix = f"T0 + {start_off}" if start_off != "0s" else "T0"
    return f"[{start_prefix} → T0 + {end_off}]"


def _merge_tool_records(
    records: list[tuple[datetime, RecordKind, Any]],
) -> list[tuple[datetime, RecordKind, Any]]:
    """把 TOOL_CALL / TOOL_RESULT 配对合并为单条区间记录（TOOL_MERGED）。

    栈式配对（后进先出）支持嵌套调用：每个 TOOL_RESULT 匹配最近的
    同名 TOOL_CALL。未配对的 TOOL_CALL 保留原样（渲染为"未返回"）。
    """
    merged: list[tuple[datetime, RecordKind, Any]] = []
    pending_calls: list[tuple[datetime, dict]] = []

    for ts, kind, record in records:
        if kind == RecordKind.TOOL_CALL and isinstance(record, dict):
            pending_calls.append((ts, record))
        elif kind == RecordKind.TOOL_RESULT and isinstance(record, dict):
            tool_name = record.get("tool_name", "?")
            # 找最近的同名未配对调用
            match_idx = None
            for i in range(len(pending_calls) - 1, -1, -1):
                if pending_calls[i][1].get("tool_name", "?") == tool_name:
                    match_idx = i
                    break
            if match_idx is not None:
                call_ts, call_record = pending_calls.pop(match_idx)
                merged.append((call_ts, RecordKind.TOOL_MERGED, {
                    "call_ts": call_ts,
                    "result_ts": ts,
                    "tool_name": tool_name,
                    "tool_args": call_record.get("tool_args", {}),
                    "result": record.get("result"),
                    "duration_ms": record.get("duration_ms", 0),
                }))
            else:
                # 落单的返回（无对应调用）：原样保留
                merged.append((ts, kind, record))
        else:
            merged.append((ts, kind, record))

    # 剩余未配对的调用追加在末尾（渲染为"未返回"）
    for ts, record in pending_calls:
        merged.append((ts, RecordKind.TOOL_CALL, record))

    return merged


def _slice_utterance_text(u: UtteranceRecord, ws: datetime, we: datetime) -> str:
    """切出话语在 [ws, we] 窗口内说出的文字。

    - 有 segments（chunk 级时间戳）：按 chunk 占用区间与窗口求交，精确切片
    - 无 segments（非流式回复/主动话语）：按时间比例线性近似切分
    """
    if not u.content:
        return ""
    if u.segments:
        times = [t for t, _ in u.segments]
        ends = times[1:] + [u.ended_at]
        parts = [d for (t, d), e in zip(u.segments, ends) if t < we and e > ws]
        return "".join(parts)
    # 线性近似：内容按时间均匀分布在 [started_at, ended_at]
    total = (u.ended_at - u.started_at).total_seconds()
    if total <= 0:
        return u.content if ws <= u.started_at <= we else ""
    start_ratio = max(0.0, (ws - u.started_at).total_seconds() / total)
    end_ratio = min(1.0, (we - u.started_at).total_seconds() / total)
    n = len(u.content)
    i0, i1 = int(start_ratio * n), int(end_ratio * n)
    return u.content[i0:i1] if i1 > i0 else ""


def _build_overlap_blocks(
    recorder: TraceRecorder,
    t0: datetime,
) -> list[tuple[datetime, list[str]]]:
    """把重叠说话窗口渲染为切片块行列表。

    返回 [(窗口起点, 行列表), ...] 按窗口起点排序。
    块内展示窗口内双方各自说出的文字（含完全重叠和不完全重叠的部分）。
    """
    blocks: list[tuple[datetime, list[str]]] = []
    for ws, we, fp, asst in recorder.get_overlaps():
        interval = _fmt_interval(ws, we, t0)
        block_lines = [f"━━━ 双方同时说话 {interval} ━━━"]
        for u in (asst, fp):
            role = u.role.replace("fake_person:", "假人(") + ")" if u.role.startswith("fake_person:") else "助手"
            sliced = _slice_utterance_text(u, ws, we)
            if not sliced:
                sliced = "（该窗口内无文字输出）"
            block_lines.append(f"  {role}（同时段说到）: {sliced}")
        blocks.append((ws, block_lines))
    return blocks


def _fmt_clock(t: Optional[datetime], t0: datetime) -> str:
    """格式化时间快进的时刻：与 T0 同日只显示时分秒，跨日附加月-日。

    丢弃微秒，保持 trace 各部分时间风格一致（T0 行已含完整日期）。
    """
    if t is None:
        return "?"
    if t.date() != t0.date():
        return t.strftime("%m-%d %H:%M:%S")
    return t.strftime("%H:%M:%S")


def _format_offset(delta: timedelta) -> str:
    """把 timedelta 格式化为简短的偏移量字符串，精确到毫秒。

    先四舍五入到毫秒再分解，避免 59.9995s 显示为 "59m60.000s"（应进位为整分/时）。
    """
    total_ms = round(delta.total_seconds() * 1000)
    total_seconds_int = total_ms // 1000
    fractional = (total_ms % 1000) / 1000
    days, rem = divmod(total_seconds_int, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or fractional >= 0.001 or not parts:
        parts.append(f"{seconds + fractional:.3f}s")
    return "".join(parts)


def _format_tool_result(result: Any) -> str:
    """格式化工具调用结果，截断过长的内容。"""
    if result is None:
        return "ok"
    if isinstance(result, str):
        if len(result) > 80:
            return result[:80] + "..."
        return result
    if isinstance(result, dict):
        s = json.dumps(result, ensure_ascii=False)
        if len(s) > 80:
            return s[:80] + "..."
        return s
    s = str(result)
    if len(s) > 80:
        return s[:80] + "..."
    return s


# ---------------- Judge system prompt ----------------


JUDGE_SYSTEM_PROMPT = """你是一名严谨的车载助手测试裁判。你的任务是：审阅一段**带时间线的测试轨迹（trace）**，判断被测助手在这次测试中的表现是否符合预期。

## 你看到的 trace 是什么

这是一次车载助手自动测试的完整记录。测试通过"剧本事件"驱动：假人扮演用户说话，被测助手回复，中间可能插入车态变更、状态检查、时间快进等事件。所有事件都带时间戳，相对于场景起始时间 T0。

## 时序演进语义（务必正确理解）

1. **时间快进**（标记为 `[时间快进]`）：测试不会真等 7 天。当下一个事件在很久之后且期间无对话活动时，虚拟时间直接跳到目标时刻。这是**正常机制**，不是剧情断裂，也不是助手出错。
2. **话语时间区间**：话语是耗时说出来的，形如 `[T0 + 1.2s → T0 + 6.0s] 助手: ...（首字延迟 1.2s, 说了 4.8s）`——开口时刻到说完时刻。括号内是时序指标：`首字延迟` 是从用户说完到助手开口的耗时，`说了 Xs` 是话语时长，`主动` + `触发后 Xs 开口` 表示助手主动开口及其触发延迟。这些指标反映响应的及时性与说话节奏。
3. **双方同时说话**（标记为 `━━━ 双方同时说话 [...] ━━━` 块）：假人插话与助手回复在时间上重叠——测试框架是中立观察者，不打断任何一方，如实记录双方在重叠窗口内各自说出的文字（块内按角色列出）。同时说话本身**不是任何一方出错**。插话语义各不相同（附和认可、否定、新指令等），面对插话，助手可能继续说完当前输出（合作容忍），也可能中止旧输出去响应（抢占响应）——**哪种反应是正确表现，由本次测试的断言定义**，请按断言评判，不要预设某种反应模式必然对或必然错。
4. **半截话**（按成因分两种标记，含义不同）：
   - `（半截话，被用户插话打断）`：助手在流式输出中收到用户开口信号，主动中断自己的旧输出去响应插话——这是**助手支持插话打断时的正常机制呈现，不是助手出错**；打断后的新回复是否正确响应了插话，按断言评判。
   - `（半截话，超时截断）`：该回复因超过测试基建的超时上限被截断，只说了一部分——通常意味着该回复异常缓慢或卡死。
5. **状态检查**（标记为 `[状态检查]`）：在指定时间点检查虚拟车的 k/v 状态。`[✓ 通过]` 或 `[✗ 失败]` 已自动判定，你不需要重新评结构化断言。
6. **车态变更**（标记为 `[车态变更]`）：模拟外部世界变化（如驾驶员踩油门），**不是**助手操作。助手的车控操作不会以这个形式出现。
7. **快进后助手主动说话**：如果 trace 里快进后出现了"助手: xxx"且前面没有假人说话，这是**助手主动开口**（如定时提醒到期触发）。其开口时机与内容是否正确，按断言评判。
8. **时间偏移**：`[T0 + 30s]` 表示场景开始后 30 秒；`[T0 + 7d]` 表示 7 天后。时间偏移是判断"响应是否及时""提醒是否准时"的关键依据。
9. **工具调用**（标记为 `[T0 + Xs → T0 + Ys] [工具] 名称(参数) → 返回值 (耗时 Zms)`）：助手在回复过程中调用了工具，含调用区间、参数与返回。用于判断助手是否正确使用了工具，而非仅凭"说了什么"推断。`（未返回）` 表示调用后一直没有返回结果。
10. **流式停顿**（标记为 `⚠ 流式停顿 Xs`）：助手文本流式输出过程中，相邻文本增量之间出现超过 2 秒的停顿，反映回复的流畅程度。工具调用相关的等待不在此列（工具执行区间已由 `[工具]` 行单独呈现）。

## 裁判价值观对齐假人

你会看到本次测试中假人的人设信息。评判时请代入假人的视角——不是冷冰冰的功能性判定，而是从该用户的角度感受被测助手的回复是否体贴、是否到位、是否贴合该用户的需求和偏好。

## 评判任务

我会给你两类断言：
1. **必过项**（must_pass）：必须通过的断言。任一不过 → 整体不通过。
2. **加分项**（bonus）：可选的加分断言。过得越多分数越高。

状态检查（state_check）已自动判定，全部算必过项，你不需要重新评。

**评判标准以断言为准**：以上时序语义只是帮你读懂 trace 的机制常识，不构成任何行为对错标准——什么算通过、什么算不通过，完全取决于断言对被测助手的要求。断言要求什么就判什么，不要套用预设的行为模板。

## 输出格式（严格遵守）

输出 JSON，结构如下：

```json
{
  "assertion_results": [
    {
      "assertion": "原始断言文本",
      "assertion_type": "must_pass 或 bonus",
      "passed": true 或 false,
      "reasoning": "你的判断理由，结合 trace 中的具体事件说明，并从假人视角评价",
      "evidence": ["引用 trace 中的关键事件片段，如 'T0+3s 助手: 好的，已为您打开空调'"]
    }
  ],
  "overall_passed": true 或 false,
  "summary": "总体评价，从假人视角总结被测助手在本次测试中的表现"
}
```

注意：
- 只输出 JSON，不要输出其他内容
- `overall_passed` = 所有必过项都 passed（加分项不影响 overall_passed）
- `evidence` 至少一条，引用 trace 中的具体时间点和事件
- 如果 trace 为空或明显异常，所有断言判 false，并在 reasoning 里说明
- 评判时结合假人人设，从该用户视角判断助手表现
"""
