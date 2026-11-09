#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pydantic>=2.7"]
# ///
"""
parse_dm_queries.py v0.4 — 严格 id 驱动的车机 logcat 解析，输出 query 证据 NDJSON
====================================================================================
输出: 每行一个 query object（QueryEvidence，pydantic 定义见下文），NDJSON。

设计原则（v0.4，按 review 修订）:
  1. 顶层为 query（不再是 session 包裹）; session_id 仅作为 query 的归属字段
  2. 不输出 asr_stream（流式过程），只保留 ASR final 文本
  3. replies 去重规则: 同一 source 内同 payload 合并（多组件投影，tags 累积）;
     tts / ui / dm / event 不同渠道之间不去重（各自保留）
  4. payload 为空的事件不输出
  5. 搜索类回调（onSuccess 等）作为 operations 的 result 事件保留
  6. 无 other 桶: 无法分类且无载荷的事件直接丢弃
  7. query 边界 = onAsrResult 按 recordId 分组（组内最后一条 = final）
"""

from __future__ import annotations

import re
import sys
import json
import argparse
import datetime
from typing import List, Optional, Dict
from enum import Enum

from pydantic import BaseModel, Field


# 全局
KEEP_NOISE = (
    False  # 默认过滤 decision 中的 DMSDS/DSKDM 配置噪音（--keep-noise 关闭过滤）
)


# ============================================================
# 枚举定义（下游 agent 可依据 schema 中的 enum 取值域做判断）
# ============================================================


class OperationKind(str, Enum):
    """操作事件类型"""

    CALL = "call"  # 请求发出（API 调用）
    RESULT = "result"  # 回调结果（如 searchPoiByKeyword onSuccess）
    SET = "set"  # HAL 属性写入（车辆物理执行）
    GET = "get"  # HAL 属性读取（状态查询）


class ReplySource(str, Enum):
    """回复渠道"""

    TTS = "tts"  # 实际 TTS 播报文本
    UI = "ui"  # UI 上屏文本


class UiChangeKind(str, Enum):
    """主界面级 UI 变化类型"""

    PAGE_CHANGE = "page_change"  # 导航页面切换（Fragment）
    ACTIVITY_START = "activity_start"  # Activity 启动（窗口级）


class ResultType(str, Enum):
    """结构化结果类型（可扩展）"""

    POI_LIST = "poi_list"  # 搜索候选项列表
    # 预留扩展: MEDIA_QUEUE = 'media_queue', RECOMMEND_CARDS = 'recommend_cards'


# ============================================================
# Schema（pydantic，供下游判分 agent 使用；model_json_schema() 可导出）
# ============================================================


class EventBase(BaseModel):
    """事件公共字段"""

    ts: str = Field(description="日志时间戳，格式 MM-DD HH:MM:SS.mmm")
    record_id: Optional[str] = Field(
        default=None,
        description="事件携带的 recordId（ASR/dm 原始 id，可为 null）。"
        "同一 recordId = 同一事件的多组件投影，可据此关联",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="事件携带的 sessionId（每轮 DM 请求可能变化，仅作参考，不可作为分组键）",
    )
    tags: List[str] = Field(
        description="打印该事件的组件 tag 列表（同事件多组件投影合并后累积）"
    )
    payload: str = Field(description="该事件的关键载荷文本（原样提取，未做语义处理）")


class Decision(EventBase):
    """决策类事件：意图解析、路径判定、命令下发"""

    pass


class Operation(EventBase):
    """执行类事件：车辆/导航/媒体 API 调用及其回调"""

    api: str = Field(
        description="API 名，如 searchPoiByKeyword / NaviRoutePlan / dealNaiOperation / CAR.HAL.set / command://xxx"
    )
    kind: OperationKind = Field(
        description="事件类型: call=请求发出 / result=回调结果 / set=HAL属性写入 / get=HAL属性读取"
    )
    params: str = Field(
        description="参数载荷（keyword/object/operation/dest/属性=值 等），无则空串"
    )


class Reply(EventBase):
    """回复类事件：车机对 query 的文本输出（已做流式聚合）"""

    source: ReplySource = Field(
        description="渠道标签: tts=实际 TTS 播报文本 / ui=UI 上屏文本。"
        "同一渠道内的流式帧已聚合为完整句；tts 与 ui 各自保留（不去重）"
    )
    ts_end: str = Field(description="该段最后一条流式帧的时间戳（单帧段与 ts 相同）")
    frames: int = Field(description="聚合的流式帧数（1 = 非流式）")


class PoiItem(BaseModel):
    """搜索候选项（POI）详情，来自 AIN-AINaviPresenter 的 AIMapPoi 日志行"""

    poi_id: str = Field(description="POI 唯一标识（高德 pid，如 B0JDGZ081F）")
    name: str = Field(description="POI 名称（如 星巴克(上海静安四季坊店)）")
    address: Optional[str] = Field(default=None, description="地址")
    city_name: Optional[str] = Field(default=None, description="城市名")
    dest_name: Optional[str] = Field(default=None, description="目的地名")
    latitude: Optional[float] = Field(default=None, description="纬度")
    longitude: Optional[float] = Field(default=None, description="经度")
    coord_type: Optional[str] = Field(default=None, description="坐标系（GCJ02 等）")
    telephone: Optional[str] = Field(default=None, description="电话")
    distance: Optional[int] = Field(default=None, description="距当前位置距离（米）")
    unsorted: Optional[str] = Field(default=None, description="排序标志")
    poi_type: Optional[str] = Field(
        default=None, description="POI 类型编码（050501=餐饮等）"
    )


class Result(BaseModel):
    """结构化结果数据（区别于文本 replies）: 搜索候选项列表等。
    判分用途: 验证候选项数量/名称与 query 期望是否匹配（如"恒隆广场那家星巴克"
    的候选项里是否真的存在恒隆广场店）。
    """

    type: ResultType = Field(
        description="结果类型: poi_list=搜索候选项列表（可扩展 media_queue/recommend_cards）"
    )
    ts: str = Field(description="结果到达时间")
    record_id: Optional[str] = Field(
        default=None, description="关联 recordId（可为 null）"
    )
    count: Optional[int] = Field(
        default=None, description="候选项总数（onListDataUpdate 的 poiInfos size）"
    )
    items: List[PoiItem] = Field(
        default_factory=list, description="候选项详情列表（按 poi_id 去重）"
    )


class UiChange(BaseModel):
    """主界面级 UI 变化（窗口/页面切换，忽略细节局部变化如气泡/动画/倒计时）。
    判分用途: 验证车机是否按预期切换界面（如搜索后进入结果页、
    选择后进入路线页、确认后进入导航引导页）。
    注: 弹窗级信号（Dialog/Popup）日志中不可得，如需弹窗证据请配合 screencap。
    """

    kind: UiChangeKind = Field(
        description="变化类型: page_change=导航页面切换 / activity_start=Activity 启动（窗口级）"
    )
    ts: str = Field(description="变化时间")
    record_id: Optional[str] = Field(
        default=None, description="关联 recordId（可为 null）"
    )
    from_path: Optional[str] = Field(
        default=None, description="page_change: 来源页面路径（如 /main/MapFragment）"
    )
    to_path: Optional[str] = Field(
        default=None,
        description="page_change: 目标页面路径（如 /search/search_result_fragment）",
    )
    component: Optional[str] = Field(
        default=None,
        description="activity_start: 启动的组件（如 com.mercedes.aiassistant/.ui.CsdChatUIActivity）",
    )


RE_PAGE_CHANGE = re.compile(r"onFragmentEvent from = (\S+) , to = (\S+)")
RE_ACTIVITY_START = re.compile(r"ActivityTaskManager: START .*cmp=(\S+)")


def extract_ui_changes(window_events):
    """提取主界面级 UI 变化（聚焦窗口/页面切换，忽略局部细节）。
    信号源:
      - page_change: 导航 Fragment 切换（onFragmentEvent from/to，过滤同页）
      - activity_start: Activity START（窗口级，如助手界面弹出）
    """
    out, seen = [], set()
    for e in window_events:
        m = RE_PAGE_CHANGE.search(e["body"])
        if m and m.group(1) != m.group(2):
            key = (m.group(1), m.group(2))
            if key in seen:
                continue  # 同一切换被多组件重复打印，窗口内去重
            seen.add(key)
            out.append(
                UiChange(
                    kind="page_change",
                    ts=e["ts"],
                    record_id=e["record_id"],
                    from_path=m.group(1),
                    to_path=m.group(2),
                )
            )
            continue
        m = RE_ACTIVITY_START.search(e["body"])
        if m:
            out.append(
                UiChange(
                    kind="activity_start",
                    ts=e["ts"],
                    record_id=e["record_id"],
                    component=m.group(1),
                )
            )
    return out


class HalPropertyState(BaseModel):
    """HAL 属性后值快照: 本 query 窗口内该属性最后一次 set 的值（执行后状态）"""

    value: str = Field(description="属性值（如 19.0 CELSIUS / 2）")
    area_id: Optional[str] = Field(default=None, description="区域（如 ROW_1_LEFT）")
    ts: str = Field(description="最后一次 set 的时间")


class MediaProgress(BaseModel):
    """播放进度观测（窗口内聚合）"""

    first_ms: int = Field(description="窗口内首次观测到的播放进度（毫秒）")
    last_ms: int = Field(description="窗口内最后一次观测到的播放进度（毫秒）")
    updates: int = Field(description="进度更新次数（MediaControllerCallback 单源计数）")


class MediaState(BaseModel):
    """媒体播放状态快照（判分用: 车机是否执行了播放操作）。
    信号源: QQ音乐/媒体中心进程日志（QM-*/MC-*/MediaControllerCallback）。
    """

    play_state: Optional[str] = Field(
        default=None,
        description="播放状态（窗口内最后观测值，MC-... playState=XXX）: "
        "PLAYING=播放中 / PAUSED=已暂停 / STOPPING=停止中 等",
    )
    playing: bool = Field(description="是否正在播放（play_state=PLAYING 或进度递增）")
    track: Optional[str] = Field(
        default=None, description="当前曲目（playListFlow 列表首项 title）"
    )
    artist: Optional[str] = Field(default=None, description="歌手（列表首项 artist）")
    playlist_size: Optional[int] = Field(
        default=None, description="播放列表大小（PLAY_LIST_CHANGED 窗口内最终 size）"
    )
    progress: Optional[MediaProgress] = Field(
        default=None, description="播放进度观测（无进度事件则 null）"
    )
    errors: List[str] = Field(
        default_factory=list,
        description="播放器错误/失败（onError/PlayError 类；当前无此类信号时为空数组，"
        "不代表播放失败）",
    )
    restricted_hits: int = Field(
        default=0,
        description="曲目版权受限提示出现次数（unPlayableMsg/playAccess=0，列表中部分歌曲受限的元数据，"
        "与当前播放是否成功无关）",
    )


class QueryState(BaseModel):
    """query 级车辆状态快照（判分用: 执行后属性值可直接对比预期）"""

    hal: Dict[str, HalPropertyState] = Field(
        default_factory=dict,
        description="HAL 属性后值: key=属性名（如 HVAC_TEMPERATURE_SET），value=后值详情。"
        "仅记录本 query 窗口内被 set 的属性（change 回调不采集）",
    )
    media: Optional[MediaState] = Field(
        default=None,
        description="媒体播放状态快照（本 query 窗口内是否有播放活动；无则 null）",
    )


class QueryEvidence(BaseModel):
    """一个 query 的全部证据（NDJSON 每行一个）"""

    query_id: str = Field(
        description="ASR recordId（onAsrResult 分组键，取 ':' 前前缀），全文件唯一主键"
    )
    session_id: str = Field(
        description="时间连续性分组的会话标识（sess_NN，gap>60s 切分）；"
        "注意不等于车机日志中的 sessionId"
    )
    turn_index: int = Field(description="会话内 query 序号（从 0 起）")
    ts_asr_final: str = Field(
        description="ASR final 时间（onAsrResult 组内最后一条的时间）"
    )
    text: str = Field(
        description="ASR final 文本（onAsrResult 组内最后一条的文本，即引擎最终识别结果）"
    )
    voicecase: Optional[str] = Field(
        default=None,
        description="所属评测用例名（VoiceCase|start/end 时间窗匹配），无则 null",
    )
    decision: List[Decision] = Field(
        description="决策事件列表（意图解析 saveInput / best skill / 路径判定 / 命令下发），按时间序"
    )
    operations: List[Operation] = Field(
        description="执行事件列表（API 调用与回调），按时间序；0~n 条"
    )
    replies: List[Reply] = Field(
        description="回复事件列表（车机文本输出），按时间序；0~n 条"
    )
    results: List[Result] = Field(
        default_factory=list,
        description="结构化结果数据列表（如搜索候选项 poi_list），与文本 replies 区分；0~n 条",
    )
    ui_changes: List[UiChange] = Field(
        default_factory=list,
        description="主界面级 UI 变化列表（页面切换/Activity 启动），按时间序；0~n 条",
    )
    state: QueryState = Field(
        default_factory=QueryState,
        description="query 级车辆状态快照（当前: HAL 属性后值）",
    )


# ============================================================
# 解析规则
# ============================================================

RE_LINE = re.compile(
    r"^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])\s+([^\s:]+)\s*:\s?(.*)$"
)
RE_LINE_BRIEF = re.compile(
    r"^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\s+([VDIWEF])/([^ (]+)\( *(\d+)\):\s?(.*)$"
)
RE_ASR = re.compile(
    r"onAsrResult \| seatId: \d+, text: ([^,]+), recordId: ([0-9a-f:]+)"
)
RE_RECORD = re.compile(r'recordId[:=] ?"?([0-9a-f:]{8,})')
RE_SESSION = re.compile(r'sessionId"?[:= ]"?([0-9a-f]{32})')

RE_SPEAKTEXT = re.compile(r'"speakText":"([^"]+)"')
RE_DOTTS = re.compile(r"doTts\.\.\.\s*(?:final\s+)?nlg = ([^,]+)")
RE_STARTSPEAK = re.compile(r"startSpeaking text = ([^,]+)")
RE_DMTASK_NLG = re.compile(r"dm_task: nlg = ([^,]+)")
RE_OUTPUTTEXT = re.compile(r"doOutputText, display = ([^,]+)")
RE_CHILDNODE = re.compile(r"Child node text: ([^,]+)")
RE_SAVEINPUT = re.compile(
    r"saveInput with: input = \[([^\]]*)\], intentName = \[([^\]]*)\]"
)
RE_ONSUCCESS = re.compile(
    r"(searchPoiByKeyword|NaviRoutePlan|MapOperaShowMyLocation|requestRoutePlanOrNavi) onSuccess,? ?(.*)"
)
RE_KEYWORD = re.compile(r"keywords?\s*[:=]?\s*\'?([^,\']+)")
RE_POI_BLOCK = re.compile(r"AIMapPoi\{([^}]*)\}")
RE_POI_COUNT = re.compile(r"poiInfos size=(\d+)")


def parse_poi(block):
    """解析单个 AIMapPoi{...} 块为 PoiItem"""

    def f(k):
        m = re.search(k + r"='([^']*)'", block)
        if m:
            return m.group(1)
        m = re.search(k + r"=([-\d.]+)", block)
        return m.group(1) if m else None

    try:
        return PoiItem(
            poi_id=f("poiId") or "",
            name=f("name") or "",
            address=f("address"),
            city_name=f("cityName"),
            dest_name=f("destName"),
            latitude=float(f("latitude")) if f("latitude") else None,
            longitude=float(f("longitude")) if f("longitude") else None,
            coord_type=f("coordType"),
            telephone=f("telephone"),
            distance=int(f("distance")) if f("distance") else None,
            unsorted=f("unsorted"),
            poi_type=f("poiType"),
        )
    except (TypeError, ValueError):
        return None


def extract_results(window_events):
    """从 query 窗口事件提取结构化结果（当前: poi_list）。
    来源: AIN-AINaviPresenter 的 AIMapPoi 行（dealResultOfSearch / lstOfData）。
    聚合: 按 poi_id 去重，count 取 poiInfos size。
    """
    items, seen_ids, count, ts, rid = [], set(), None, None, None
    for e in window_events:
        for m in RE_POI_BLOCK.finditer(e["body"]):
            poi = parse_poi(m.group(1))
            if poi and poi.poi_id and poi.poi_id not in seen_ids:
                seen_ids.add(poi.poi_id)
                items.append(poi)
                ts = ts or e["ts"]
                rid = rid or e["record_id"]
        cm = RE_POI_COUNT.search(e["body"])
        if cm:
            count = int(cm.group(1))
    if not items:
        return None
    return Result(type="poi_list", ts=ts or "", record_id=rid, count=count, items=items)


def classify(event):
    """机械分类。返回 (bucket, source, api, params, payload) 或 None（丢弃）。
    bucket: decision | operation | reply
    """
    b = event["body"]
    # --- 回复类（按 review 只保留 ui 与 tts 两个渠道）---
    # ui 渠道只从 AI 输出通道提取，排除用户输入回显（context.input.text/onContextInput）
    # 与整屏扫描（SWYSService Child node text）：
    #   1) context.output.text 消息体（AI 回复消息，带独立 recordId）
    #   2) dealChatData merge after（AI 回复流式累积帧）
    #   3) doOutputText display（AI 输出上屏）
    m = RE_DOTTS.search(b) or RE_STARTSPEAK.search(b)
    if m and m.group(1).strip():
        return ("reply", "tts", None, None, m.group(1).strip())
    if "context.output.text" in b:
        tm = re.search(r'"text":"([^"]+)"', b)
        if tm and tm.group(1).strip():
            return ("reply", "ui", None, None, tm.group(1).strip())
    if "dealChatData merge after::" in b:
        m = re.search(r"dealChatData merge after:: ([^\n]+)", b)
        return ("reply", "ui", None, None, m.group(1).strip() if m else "")
    m = RE_OUTPUTTEXT.search(b)
    if m and m.group(1).strip():
        return ("reply", "ui", None, None, m.group(1).strip())
    # 注: event 源（trackBaseEvent/trackDialogue 等事件上报）不再作为 reply 输出，
    # 按 review 要求 replies 只关注 ui 与 tts 两个渠道。
    # --- 决策类 ---
    m = RE_SAVEINPUT.search(b)
    if m:
        return ("decision", None, None, None, f"input={m.group(1)} intent={m.group(2)}")
    if "best skill" in b:
        return ("decision", None, None, None, b[:150])
    if "RegexMatc" in b and "matched" in b:
        return ("decision", None, None, None, b[:150])
    if "SEMANTICSDS START" in b or "DSKDM." in b:
        return ("decision", None, None, None, b[:150])
    if "sys.car.large-model" in b and "COMMAND" in b:
        return ("decision", None, None, None, "command://sys.car.large-model")
    # --- 操作类 ---
    m = RE_ONSUCCESS.search(b)
    if m:
        return (
            "operation",
            None,
            m.group(1),
            "result",
            f"onSuccess {m.group(2).strip()}".strip(),
        )
    # HAL 车辆属性操作（tag=CAR.HAL; body 不含 'CAR.HAL' 字样，用 tag 判断）
    if event["tag"] == "CAR.HAL":
        if "for set" in b:
            pm = re.search(
                r"Property ID: ([A-Z_]+)\(0x[0-9a-f]+\)(?:, Area ID: ([A-Z_0-9]+)\(0x[0-9a-f]+\))?.*?Value: ([^}]+)",
                b,
            )
            if pm:
                prop, area, val = pm.group(1), pm.group(2), pm.group(3).strip()
                return (
                    "operation",
                    None,
                    "CAR.HAL.set",
                    "set",
                    f"{prop}={val} area={area}" if area else f"{prop}={val}",
                )
            return ("operation", None, "CAR.HAL.set", "set", b[:80])
        if "for get" in b:
            pm = re.search(r"Property ID: ([A-Z_]+)", b)
            vm = re.search(r"ResultValue: HalPropValue\{[^}]*Value: ([^}]+)", b)
            prop = pm.group(1) if pm else "?"
            val = vm.group(1).strip() if vm else None
            return (
                "operation",
                None,
                "CAR.HAL.get",
                "get",
                f"{prop}={val}" if val else prop,
            )
        gm = re.search(r"CAR\.HAL : get, ([A-Z_]+)", b)
        if gm:
            return ("operation", None, "CAR.HAL.get", "get", gm.group(1))
        return None
    if "dealNaiOperation" in b:
        om = re.search(r"object=(\S+); operation=(\S+)", b)
        return (
            "operation",
            None,
            "dealNaiOperation",
            "call",
            f"object={om.group(1)} op={om.group(2)}" if om else "",
        )
    if "searchPoiByKeyword" in b:
        km = RE_KEYWORD.search(b)
        return (
            "operation",
            None,
            "searchPoiByKeyword",
            "call",
            f"keyword={km.group(1).strip()}" if km else "",
        )
    if "NaviRoutePlan" in b:
        dm = re.search(r"destPoiInfo=(\{[^}]*\}|[^,{]+)", b)
        return (
            "operation",
            None,
            "NaviRoutePlan",
            "call",
            f"dest={dm.group(1)[:80]}" if dm else "",
        )
    if "MapOperaShowMyLocation" in b:
        return ("operation", None, "MapOperaShowMyLocation", "call", "showMyLocation")
    cm = re.search(r"COMMAND -> intentApi = ([^\s,]+)", b)
    if cm:
        return ("decision", None, None, None, cm.group(1))
    cm2 = re.search(r"onCall\(\) called with: topic = \[([^\]]+)\]", b)
    if cm2:
        return ("operation", None, cm2.group(1), "call", cm2.group(1))
    return None


def parse_log(paths):
    events = []
    for p in paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            for ln, line in enumerate(f, 1):
                m = RE_LINE.match(line.rstrip("\r\n"))
                if m:
                    ts, pid, tid, lv, tag, body = m.groups()
                else:
                    m = RE_LINE_BRIEF.match(line.rstrip("\r\n"))
                    if not m:
                        continue
                    ts, lv, tag, pid, body = m.groups()
                rec = RE_RECORD.search(body)
                ses = RE_SESSION.search(body)
                events.append(
                    {
                        "ts": ts,
                        "pid": pid,
                        "tag": tag,
                        "body": body,
                        "line": ln,
                        "record_id": rec.group(1) if rec else None,
                        "session_id": ses.group(1) if ses else None,
                    }
                )
    events.sort(key=lambda e: e["ts"])
    return events


def find_asr_finals(events):
    groups, order = {}, []
    for e in events:
        m = RE_ASR.search(e["body"])
        if not m:
            continue
        text, rid = m.group(1).strip(), m.group(2).strip()
        base = rid.split(":")[0]
        if base not in groups:
            groups[base] = []
            order.append(base)
        groups[base].append({"ts": e["ts"], "text": text})
    finals = []
    for base in order:
        g = sorted(groups[base], key=lambda x: x["ts"])
        finals.append({"ts": g[-1]["ts"], "text": g[-1]["text"], "rid": base})
    finals.sort(key=lambda x: x["ts"])
    return finals


def extract_hal_state(window_events):
    """HAL 属性后值快照: 窗口内被 set 的属性，取最后一次 set 的值。
    change 回调不采集（后值已由 set 提供）。
    """
    state = {}
    for e in window_events:
        if e["tag"] != "CAR.HAL" or "for set" not in e["body"]:
            continue
        pm = re.search(
            r"Property ID: ([A-Z_]+)\(0x[0-9a-f]+\)(?:, Area ID: ([A-Z_0-9]+)\(0x[0-9a-f]+\))?.*?Value: ([^}]+)",
            e["body"],
        )
        if not pm:
            continue
        prop, area, val = pm.group(1), pm.group(2), pm.group(3).strip()
        state[prop] = HalPropertyState(value=val, area_id=area, ts=e["ts"])
    return QueryState(hal=state)


def extract_media_state(window_events, prev_track=None, prev_artist=None):
    """媒体播放状态快照: 窗口内聚合播放活动。
    信号源（媒体进程，均无 recordId，靠时间窗归属）:
      - playlist_size: QM-QCTRL PLAY_LIST_CHANGED size=N（取窗口内最终值）
      - track/artist: playListFlow collect 列表首项（权威，优先）或
                      lyric 标题行 "歌名 - 歌手"（换曲信号，补充）；
                      窗口内无新信号则继承上一 query 的曲目（持续状态）
      - progress/playing: MediaControllerCallback onPlayProgressUpdated:N（单源聚合）
      - play_state: MC-*/QM-* playState=XXX（窗口内最后观测值）
      - errors: onError/PlayError 类（播放器错误，非曲目受限）
      - restricted_hits: unPlayableMsg/playAccess=0 出现次数（列表中受限歌曲元数据）
    无任何媒体信号返回 None。
    """
    size = None
    track, artist = prev_track, prev_artist
    first = last = None
    updates = 0
    errors = set()
    play_state = None
    restricted_hits = 0
    for e in window_events:
        b = e["body"]
        m = re.search(r"PLAY_LIST_CHANGED, size = (\d+)", b)
        if m:
            size = int(m.group(1))
        # 列表首项（权威，覆盖 lyric）
        m = re.search(
            r"playListFlow collect size=\d+, list=\[mediaId=\d+, title=([^,]+), artist=([^,]+)",
            b,
        )
        if m:
            track, artist = m.group(1).strip(), m.group(2).strip()
        # 换曲信号: 歌词标题行 "歌名 - 歌手"（无条件更新；
        # 若与 playListFlow 冲突，由后续的 playListFlow 覆盖）
        m = re.search(r"LyricLine\(text=([^,]+?)\s*-\s*([^,(]+)", b)
        if m:
            track, artist = m.group(1).strip(), m.group(2).strip()
        m = re.search(r"onPlayProgressUpdated: (\d+)", b)
        if m and "MediaControllerCallback" in e["tag"]:
            v = int(m.group(1))
            if first is None:
                first = v
            last = v
            updates += 1
        m = re.search(r"playState=([A-Z_]+)", b)
        if m and ("MC-" in e["tag"] or "QM-" in e["tag"]):
            play_state = m.group(1)  # 窗口内最后观测值
        if re.search(r"onError|PlayError|playError|播放失败", b):
            errors.add(b[:120])
        if re.search(r"unPlayableMsg=|playAccess=0", b):
            restricted_hits += 1
    if (
        size is None
        and track is None
        and updates == 0
        and not errors
        and play_state is None
        and restricted_hits == 0
    ):
        return None
    if play_state is not None:
        playing = play_state == "PLAYING"
    else:
        playing = updates >= 2 and last is not None and last > 0
    return MediaState(
        play_state=play_state,
        playing=playing,
        track=track,
        artist=artist,
        playlist_size=size,
        progress=MediaProgress(first_ms=first, last_ms=last, updates=updates)
        if first is not None
        else None,
        errors=sorted(errors),
        restricted_hits=restricted_hits,
    )


def is_dmsds_noise(payload):
    """DMSDS/DSKDM 纯配置/过程打印判定（True=丢弃）。
    保留例外: DSKDM 错误信号（RUNTIME.ERROR/ERROR）与 SEMANTICSDS 引擎调用标记。
    """
    if "DSKDM" not in payload and "SEMANTICSDS" not in payload:
        return False
    if "DSKDM.RUNTIME.ERROR" in payload or "DSKDM.ERROR" in payload:
        return False  # 错误信号保留（本地技能失败判分点）
    if "SEMANTICSDS" in payload:
        return False  # 引擎调用标记保留
    return True  # DSKDM.REQUEST./DMCONFIG./RESPONSE./BUNDLE./SUMMAR./DISCA./PATH 等丢弃


def build_queries(events, finals):
    queries = []
    prev_track = prev_artist = None  # 媒体曲目游标（跨 query 继承持续状态）
    for i, f in enumerate(finals):
        win_end = finals[i + 1]["ts"] if i + 1 < len(finals) else None
        buckets = {"decision": [], "operation": [], "reply": []}
        window_events = []
        for e in events:
            if e["ts"] < f["ts"]:
                continue
            if win_end and e["ts"] >= win_end:
                break
            window_events.append(e)
            r = classify(e)
            if r is None:
                continue
            bucket, source, api, kind, payload = r
            if not payload:
                continue  # 空载荷事件无意义，丢弃
            buckets[bucket].append(
                {
                    "ts": e["ts"],
                    "record_id": e["record_id"],
                    "session_id": e["session_id"],
                    "tag": e["tag"],
                    "source": source,
                    "api": api,
                    "kind": kind,
                    "params": payload,
                    "payload": payload,
                }
            )
        if not KEEP_NOISE:
            buckets["decision"] = [
                d for d in buckets["decision"] if not is_dmsds_noise(d["payload"])
            ]
        media = extract_media_state(window_events, prev_track, prev_artist)
        if media:
            prev_track, prev_artist = media.track, media.artist
        queries.append(
            {
                "query_id": f["rid"],
                "turn_index": i,
                "ts_asr_final": f["ts"],
                "text": f["text"],
                "decision": _collapse(buckets["decision"]),
                "operations": _collapse(buckets["operation"]),
                "replies": merge_replies(buckets["reply"]),
                "results": [extract_results(window_events)]
                if extract_results(window_events)
                else [],
                "ui_changes": extract_ui_changes(window_events),
                "state": QueryState(
                    hal=extract_hal_state(window_events).hal, media=media
                ),
            }
        )
    return queries


def merge_replies(items):
    """回复聚合: 先按 (source, payload) 去重投影，再按 source 分组做流式合并"""
    collapsed = _collapse(items)
    out = []
    for src in ("ui", "tts"):
        out.extend(merge_stream([x for x in collapsed if x["source"] == src]))
    return sorted(out, key=lambda x: x["ts"])


def merge_stream(items):
    """合并流式帧为完整段（按 source 分组调用）。
    规则（兼容累积式与重读式）:
      - 帧是已合并文本的子串/前缀 → 跳过（重读帧、重复短帧）
      - 帧以已合并文本开头 → 累积增长，替换为更长文本
      - 否则 → 新开一段（多段回复）
    """
    segs = []
    for it in sorted(items, key=lambda x: x["ts"]):
        t = it["payload"].strip()
        if not t or t in ("null", "000", "None"):
            continue  # 占位符/无意义载荷
        if segs:
            last = segs[-1]
            if t in last["payload"] or last["payload"].startswith(t):
                for tag in it["tags"]:
                    if tag not in last["tags"]:
                        last["tags"].append(tag)
                continue
            if t.startswith(last["payload"]):
                last["payload"] = t
                last["ts_end"] = it["ts"]
                last["frames"] += 1
                for tag in it["tags"]:
                    if tag not in last["tags"]:
                        last["tags"].append(tag)
                continue
        segs.append(
            {
                "ts": it["ts"],
                "ts_end": it["ts"],
                "source": it["source"],
                "tags": list(it["tags"]),
                "payload": t,
                "frames": 1,
            }
        )
    return segs


def _collapse(items):
    """去重: 同 (record_id, source/api/kind, payload) 合并为一条（多组件投影），
    tags 累积、保留最早 ts。不同 source（tts/ui/dm/event）之间不去重。"""
    out = {}
    for it in items:
        key = (it["record_id"], it["source"], it["api"], it["kind"], it["payload"])
        if key in out:
            if it["tag"] not in out[key]["tags"]:
                out[key]["tags"].append(it["tag"])
        else:
            out[key] = dict(it)
            out[key]["tags"] = [it["tag"]]
    return sorted(out.values(), key=lambda x: x["ts"])


def group_sessions(finals, gap_ms=60000):
    sessions, cur, prev = [], [], None
    for f in finals:
        if prev and _ms(f["ts"]) - _ms(prev) > gap_ms:
            sessions.append(cur)
            cur = []
        cur.append(f)
        prev = f["ts"]
    if cur:
        sessions.append(cur)
    return sessions


def _ms(ts):
    dt = datetime.datetime.strptime(ts, "%m-%d %H:%M:%S.%f").replace(year=2000)
    return dt.timestamp()


def find_voicecase(events):
    vcs, cur = [], None
    for e in events:
        if e["tag"] != "VoiceCase":
            continue
        m = re.search(r"VoiceCase\|(start|end)\|(.+)", e["body"])
        if not m:
            continue
        if m.group(1) == "start":
            cur = {"start": e["ts"], "name": m.group(2).strip()}
        elif cur:
            cur["end"] = e["ts"]
            vcs.append(cur)
            cur = None
    return vcs


def to_models(queries, session_of, vcs):
    """构建 pydantic QueryEvidence 列表（校验 + 序列化）"""
    models = []
    for q in queries:
        sid = session_of[q["query_id"]]
        vc = next(
            (
                v["name"]
                for v in vcs
                if v["start"] <= q["ts_asr_final"] <= v.get("end", q["ts_asr_final"])
            ),
            None,
        )
        models.append(
            QueryEvidence(
                query_id=q["query_id"],
                session_id=sid,
                turn_index=q["turn_index"],
                ts_asr_final=q["ts_asr_final"],
                text=q["text"],
                voicecase=vc,
                decision=[Decision(**e) for e in q["decision"]],
                operations=[Operation(**e) for e in q["operations"]],
                replies=[Reply(**e) for e in q["replies"]],
                results=q["results"],
                ui_changes=q["ui_changes"],
                state=q["state"],
            )
        )
    return models


def main():
    ap = argparse.ArgumentParser(description="解析车机 logcat 为 query 证据 NDJSON")
    ap.add_argument(
        "logfiles", nargs="*", help="logcat 文本文件（threadtime 或 brief 格式）"
    )
    ap.add_argument(
        "-o", "--output", default="query_evidence.jsonl", help="输出 NDJSON"
    )
    ap.add_argument(
        "--keep-noise",
        action="store_true",
        help="保留 DMSDS/DSKDM 配置刷屏行（默认过滤，调试时用）",
    )
    ap.add_argument(
        "--schema", action="store_true", help="仅输出 JSON Schema 到 stdout"
    )
    args = ap.parse_args()
    global KEEP_NOISE
    KEEP_NOISE = args.keep_noise

    if args.schema:
        print(
            json.dumps(QueryEvidence.model_json_schema(), ensure_ascii=False, indent=2)
        )
        return

    events = parse_log(args.logfiles)
    print(f"[1/4] 事件 {len(events)}", file=sys.stderr)
    finals = find_asr_finals(events)
    print(f"[2/4] query {len(finals)}", file=sys.stderr)
    vcs = find_voicecase(events)
    queries = build_queries(events, finals)

    sessions = group_sessions(finals)
    session_of = {}
    for gi, fs in enumerate(sessions):
        for f in fs:
            session_of[f["rid"]] = f"sess_{gi:02d}"

    models = to_models(queries, session_of, vcs)
    with open(args.output, "w", encoding="utf-8") as f:
        for m in models:
            f.write(m.model_dump_json() + "\n")
    print(f"[4/4] 输出 {len(models)} 个 query -> {args.output}", file=sys.stderr)
    for m in models[:30]:
        print(f"  [{m.session_id} #{m.turn_index:02d}] {m.text[:30]}")


if __name__ == "__main__":
    main()
