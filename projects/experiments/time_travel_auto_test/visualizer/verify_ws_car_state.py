"""WS 实跑验证：虚拟车扩展（初始车态快照 + 分组元数据 + 车控事件链）。

验证点：
1. case_started 事件携带全量 initial_car_info（含新增：多媒体三态/歌曲信息/
   四座乘员/空调风向/方向盘加热等 40+ 字段默认值）
2. case_started 事件携带 car_state_groups 分组元数据（前端分层展示依据）
3. case_started 事件携带 script_plan 剧本时间表（时间线"未来区"预设事件竖线）
4. 助手车控工具改车态 → car_set_state 增量事件正常发射并标注 source 来源
   （assistant=助手车控 / script=剧本上帝视角）
5. case 自然结束，state_check 通过

用法：D:/apps/miniconda/envs/dzy_env/python.exe visualizer/verify_ws_car_state.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import websockets  # noqa: E402

WS_URL = "ws://127.0.0.1:8800/ws"

# 新增字段抽查（设备模型扩展核心）
REQUIRED_NEW_FIELDS = [
    "多媒体播放状态",
    "正在播放的歌曲名",
    "正在播放的歌手名",
    "正在播放的歌单名",
    "导航目的地",
    "主驾是否有人",
    "副驾是否有人",
    "二排左侧是否有人",
    "二排右侧是否有人",
    "空调风向",
    "方向盘加热",
    "车载电视",
    "冰箱模式",
]

REQUIRED_GROUPS = [
    "行驶与能源",
    "空调",
    "座椅与方向盘",
    "乘员",
    "门窗与天窗",
    "灯光",
    "媒体",
    "导航",
    "车载电器",
]


async def run_case_and_collect(ws, case_id: str) -> list[dict]:
    """运行一个 case 并收集全部事件直到 case_finished / run_error。"""
    await ws.send(json.dumps({
        "kind": "command",
        "command_id": f"run-{case_id}",
        "command": "run_case",
        "payload": {"case_id": case_id},
    }))
    events: list[dict] = []
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=120)
        msg = json.loads(raw)
        if msg.get("kind") == "ack":
            if not msg.get("ok"):
                raise RuntimeError(f"run_case 被拒绝: {msg}")
            continue
        if msg.get("kind") != "event":
            continue
        ev = msg["event"]
        events.append(ev)
        if ev["kind"] in ("case_finished", "run_error"):
            return events


def check(cond: bool, label: str, errors: list[str]) -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}")
    if not cond:
        errors.append(label)


async def main() -> int:
    errors: list[str] = []
    async with websockets.connect(WS_URL) as ws:
        hello = json.loads(await ws.recv())
        assert hello["kind"] == "hello"
        print(f"connected: {WS_URL}")

        # ---------- case 1: builtin-simple-ac ----------
        print("\n=== case 1: builtin-simple-ac ===")
        events = await run_case_and_collect(ws, "builtin-simple-ac")
        kinds = [e["kind"] for e in events]
        started = next(e for e in events if e["kind"] == "case_started")["payload"]

        print(f"事件总数: {len(events)}, 类型分布: {sorted(set(kinds))}")

        print("\n-- initial_car_info 全量快照 --")
        info = started["initial_car_info"]
        print(f"字段数: {len(info)}")
        for f in REQUIRED_NEW_FIELDS:
            check(f in info, f"初始车态含 '{f}' (={info.get(f)!r})", errors)

        print("\n-- car_state_groups 分组元数据 --")
        groups = started.get("car_state_groups")
        check(isinstance(groups, dict) and len(groups) >= 9,
              f"分组数 = {len(groups) if groups else 0} (≥9)", errors)
        for g in REQUIRED_GROUPS:
            check(groups and g in groups, f"分组 '{g}' 存在", errors)

        print("\n-- 车控事件链 --")
        car_events = [e for e in events if e["kind"] == "car_set_state"]
        print(f"car_set_state 事件数: {len(car_events)}")
        for e in car_events[:6]:
            upd = e["payload"].get("updated_fields", {})
            print(f"    mock={e['mock_time'][11:19]} source={e['payload'].get('source')!r} {upd}")
        check(len(car_events) > 0, "助手车控触发了 car_set_state 增量事件", errors)
        check(all(e["payload"].get("source") == "assistant" for e in car_events),
              "case1 车控事件全部标注 source=assistant（助手车控）", errors)

        print("\n-- script_plan 剧本时间表（未来区预设事件竖线数据源） --")
        plan = started.get("script_plan")
        check(isinstance(plan, list) and len(plan) >= 2,
              f"script_plan 条目数 = {len(plan) if isinstance(plan, list) else None} (≥2)", errors)
        if isinstance(plan, list) and plan:
            for item in plan:
                print(f"    {item['at'][11:19]} [{item['kind']}] {item['label']}")
            check(all(k in item for item in plan for k in ("kind", "at", "target", "label")),
                  "plan 条目含 kind/at/target/label 字段", errors)
            check([i["at"] for i in plan] == sorted(i["at"] for i in plan),
                  "script_plan 按时刻升序", errors)
            check(plan[0]["kind"] == "fake_person_speak" and "把空调打开" in plan[0]["label"],
                  "首条预设事件 = 假人开空调台词", errors)
            check(any(i["kind"] == "state_check" for i in plan),
                  "state_check 进入剧本时间表", errors)

        finished = next(e for e in events if e["kind"] == "case_finished")["payload"]
        check(finished.get("state_check_passed") is True,
              f"state_check 通过 (passed={finished.get('state_check_passed')})", errors)

        # ---------- case 2: builtin-navigation-multi-condition ----------
        print("\n=== case 2: builtin-navigation-multi-condition ===")
        events2 = await run_case_and_collect(ws, "builtin-navigation-multi-condition")
        started2 = next(e for e in events2 if e["kind"] == "case_started")["payload"]
        info2 = started2["initial_car_info"]
        print(f"事件总数: {len(events2)}")
        check(len(info2) >= 40, f"case2 初始车态字段数 = {len(info2)} (≥40)", errors)
        check(started2.get("car_state_groups") == groups,
              "case2 分组元数据与 case1 一致（静态字典）", errors)
        finished2 = next(e for e in events2 if e["kind"] == "case_finished")["payload"]
        check(finished2.get("state_check_passed") is True,
              f"case2 state_check 通过 (passed={finished2.get('state_check_passed')})", errors)
        tool_calls = [e for e in events2 if e["kind"] == "tool_call"]
        print(f"tool_call 事件数: {len(tool_calls)}")

        # ---------- case 3: builtin-god-view（剧本/助手混合来源） ----------
        print("\n=== case 3: builtin-god-view ===")
        events3 = await run_case_and_collect(ws, "builtin-god-view")
        started3 = next(e for e in events3 if e["kind"] == "case_started")["payload"]
        plan3 = started3.get("script_plan") or []
        print(f"事件总数: {len(events3)}")
        print(f"script_plan 条目: {[(i['at'][11:19], i['kind']) for i in plan3]}")
        check(any(i["kind"] == "car_set_state" and "剧本改车态" in i["label"] for i in plan3),
              "剧本 set_state 进入 script_plan（未来区金色竖线预览）", errors)

        print("\n-- 混合来源 car_set_state --")
        car3 = [e for e in events3 if e["kind"] == "car_set_state"]
        for e in car3:
            upd = e["payload"].get("updated_fields", {})
            print(f"    mock={e['mock_time'][11:19]} source={e['payload'].get('source')!r} {upd}")
        sources3 = {e["payload"].get("source") for e in car3}
        check("assistant" in sources3, "助手开空调 → source=assistant（前端红色标记）", errors)
        check("script" in sources3, "剧本改车态 → source=script（前端金色标记）", errors)
        script_ev = next(e for e in car3 if e["payload"].get("source") == "script")
        check("车辆当前行驶速度" in script_ev["payload"]["updated_fields"],
              "剧本事件多字段一条（车速+档位+车外温度）", errors)

        finished3 = next(e for e in events3 if e["kind"] == "case_finished")["payload"]
        check(finished3.get("state_check_passed") is True,
              f"混合来源 state_check 通过 (passed={finished3.get('state_check_passed')})", errors)

    print("\n" + "=" * 50)
    if errors:
        print(f"验证失败 {len(errors)} 项:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("全部验证通过 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
