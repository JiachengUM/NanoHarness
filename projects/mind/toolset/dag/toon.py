"""projects.mind.toolset.dag — TOON 序列化器（token 节省格式）

TOON 协议：https://github.com/toon-format/toon

v4 渲染规则：
- 顶层 dict 单 key + list value（list 内 dict keys 严格一致）→ tabular 格式
- 顶层 dict 单 key + 空 list value → ``f"{key}[0]:"``（0 results 显式信号）
- 顶层 dict 单 key + 缺字段 list value（item keys 子集不一致）→ tabular 兜底（schema = key 并集，缺失用空值）
- 顶层 dict 单 key + 异构 list value（非 dict item 或 type 混杂）→ row-by-row 兜底
- 顶层 dict 多 key → indented（key: value 一行一对）
- 空 dict / 标量 → 兜底 indented 或空串
"""
from __future__ import annotations

import json
import re
from typing import Any


# TOON 单元格需要引号包裹的字符（RFC 8259 + TOON spec）
_TOON_QUOTE_CHARS = frozenset({",", "\n", '"', ":", "[", "]", "{", "}"})


def _toon_cell(v: Any) -> str:
    """TOON 单个单元格序列化。

    - bool → true / false
    - int / float → str(v)
    - None → "" (空字符串)
    - dict / list → inline JSON 字符串
    - 字符串：含 ",/:\\n[]{} 时加引号 + 转义
    """
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    s = str(v)
    if any(c in s for c in _TOON_QUOTE_CHARS):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return s


def _toon_list_of_dicts(key: str, value: list) -> str:
    """list of dict 的 TOON 渲染。

    - 空 list → ``f"{key}[0]:"``（显式 0 results 信号，避免退化成 ``""``）
    - 同构（所有 item keys 完全一致）→ tabular（schema header + 行）
    - 缺字段（item keys 是子集关系，源自 API 部分字段未返回）→ tabular 兜底：
      schema = 所有 item keys 的并集（保序：第一条 item 的 key 顺序优先，缺失 key 追加末尾），
      缺失字段用空字符串渲染（与 None 等价）。这样 5 个 search tool 即使有 item 缺字段
      （如 SongSearch 第 4 条无 album_name/public_time）也能稳定走 tabular，节省 token
    - 异构（非 dict item 或 type 混杂）→ YAML-like row-by-row 兜底
    """
    if not value:
        return f"{key}[0]:"
    if all(isinstance(item, dict) for item in value):
        # 收集所有 item 的 key 并集（保持第一条 item 的 key 顺序，缺失追加到末尾）
        fields: list[str] = list(value[0].keys())
        seen: set[str] = set(fields)
        for item in value[1:]:
            for k in item.keys():
                if k not in seen:
                    fields.append(k)
                    seen.add(k)
        lines = [f"{key}[{len(value)}]{{{','.join(fields)}}}:"]
        for item in value:
            lines.append(
                "  " + ",".join(_toon_cell(item.get(f, "")) for f in fields)
            )
        return "\n".join(lines)
    # 兜底：含非 dict item 或 type 混杂
    lines = [f"{key}[{len(value)}]:"]
    for item in value:
        if not isinstance(item, dict) or not item:
            lines.append("  - " + _toon_cell(item))
            continue
        first_k, first_v = next(iter(item.items()))
        lines.append(f"  - {first_k}: {_toon_cell(first_v)}")
        for k, v in list(item.items())[1:]:
            lines.append(f"    {k}: {_toon_cell(v)}")
    return "\n".join(lines)


def to_toon(data: Any) -> str:
    """最小 TOON 序列化。"""
    if not data:
        return ""
    if isinstance(data, dict) and len(data) == 1:
        ((key, value),) = data.items()
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return _toon_list_of_dicts(key, value)
    if isinstance(data, dict):
        return "\n".join(f"{k}: {_toon_cell(v)}" for k, v in data.items())
    return _toon_cell(data)


# ---------------------------------------------------------------------------
# 反序列化：to_toon 的逆操作
# ---------------------------------------------------------------------------

_TOON_LINE_RE_TABULAR = re.compile(r"^([^\s\[:]+)\[(\d+)\]\{([^}]*)\}:\s*$")
_TOON_LINE_RE_EMPTY = re.compile(r"^([^\s\[:]+)\[0\]:\s*$")
_TOON_LINE_RE_HETERO = re.compile(r"^([^\s\[:]+)\[(\d+)\]:\s*$")


def _parse_cell(s: str) -> Any:
    """TOON 单元格 → Python 值。``_toon_cell`` 的逆操作。"""
    s = s.strip()
    if s == "":
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    # 数字（int / float）
    try:
        if "." in s or "e" in s or "E" in s:
            return float(s)
        return int(s)
    except ValueError:
        pass
    # inline JSON（dict / list 走 json.dumps 后落入此分支）
    if s.startswith("{") or s.startswith("["):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    # 带引号字符串：反转义 \\, \", \n（顺序：先 \\，避免 \\" → \" 误判）
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        inner = s[1:-1]
        inner = inner.replace("\\\\", "\x00")
        inner = inner.replace('\\"', '"')
        inner = inner.replace("\\n", "\n")
        inner = inner.replace("\x00", "\\")
        return inner
    return s


def _split_csv_row(row: str) -> list[str]:
    """按 , 切分 TOON tabular 行，尊重引号与转义。"""
    cells: list[str] = []
    current: list[str] = []
    in_quote = False
    i = 0
    n = len(row)
    while i < n:
        c = row[i]
        if in_quote:
            if c == "\\" and i + 1 < n:
                current.append(row[i + 1])
                i += 2
                continue
            if c == '"':
                in_quote = False
                current.append(c)
                i += 1
                continue
            current.append(c)
            i += 1
        else:
            if c == ",":
                cells.append("".join(current))
                current = []
                i += 1
                continue
            if c == '"':
                in_quote = True
                current.append(c)
                i += 1
                continue
            current.append(c)
            i += 1
    cells.append("".join(current))
    return cells


def from_toon(s: str) -> Any:
    """TOON 字符串 → Python 对象。``to_toon`` 的逆操作。

    支持的格式（与 ``to_toon`` 输出严格对齐）：
    - ``""`` → ``""``（与 ``to_toon`` 空输入对称）
    - ``"key[N]{f1,f2,...}:\\n  v11,v12,...\\n  ..."`` → ``{"key": [{f1: v11, ...}, ...]}``
    - ``"key[0]:"`` → ``{"key": []}``
    - ``"key[N]:\\n  - k1: v1\\n    k2: v2\\n  - ..."`` → ``{"key": [{k1: v1, ...}, ...]}``
    - 多行 ``"k1: v1\\nk2: v2"`` → ``{"k1": v1, "k2": v2}``
    - 单行标量 → 对应 Python 值（str / int / float / bool / None / dict / list）
    """
    if not s:
        return ""
    lines = s.split("\n")
    first = lines[0]

    # 1) Tabular: key[N]{f1,f2,...}:
    m = _TOON_LINE_RE_TABULAR.match(first)
    if m:
        key, n, fields_str = m.group(1), int(m.group(2)), m.group(3)
        fields = fields_str.split(",") if fields_str else []
        items: list[dict] = []
        for i in range(n):
            row_line = lines[1 + i] if 1 + i < len(lines) else ""
            cells = _split_csv_row(row_line.strip())
            item: dict = {}
            for j, f in enumerate(fields):
                # 空 cell 视为"字段缺失"（to_toon 用 item.get(f, "") 编码缺失），
                # 省略而非 None，以保证 list-of-dict 的 round-trip 字段集合一致
                if j < len(cells) and cells[j].strip() != "":
                    item[f] = _parse_cell(cells[j])
            items.append(item)
        return {key: items}

    # 2) Empty list: key[0]:
    m = _TOON_LINE_RE_EMPTY.match(first)
    if m:
        return {m.group(1): []}

    # 3) Heterogeneous list fallback: key[N]:（- k: v + 续行）
    m = _TOON_LINE_RE_HETERO.match(first)
    if m:
        key, n = m.group(1), int(m.group(2))
        items = []
        idx = 1
        for _ in range(n):
            if idx >= len(lines):
                break
            item_line = lines[idx]
            sub = item_line.lstrip()
            if not sub.startswith("- "):
                idx += 1
                continue
            content = sub[2:]
            if ":" in content:
                k, _, v = content.partition(":")
                item: dict = {k.strip(): _parse_cell(v)}
                idx += 1
                # 续行（更深缩进）
                while idx < len(lines):
                    cont = lines[idx]
                    if not cont.strip():
                        idx += 1
                        continue
                    cont_strip = cont.lstrip()
                    cont_indent = len(cont) - len(cont_strip)
                    if cont_indent > 2 and ":" in cont_strip:
                        k2, _, v2 = cont_strip.partition(":")
                        item[k2.strip()] = _parse_cell(v2)
                        idx += 1
                    else:
                        break
                items.append(item)
            else:
                items.append(_parse_cell(content))
                idx += 1
        return {key: items}

    # 4) 多行 / 单行 dict: "k: v"
    if all(":" in ln for ln in lines if ln.strip()):
        result: dict = {}
        for ln in lines:
            if not ln.strip():
                continue
            k, _, v = ln.partition(":")
            result[k.strip()] = _parse_cell(v)
        return result

    # 5) 标量
    return _parse_cell(first.strip())


def toon_eq(a: Any, b: Any) -> bool:
    """结构等价比较（用于 ``to_toon`` / ``from_toon`` 的 round-trip 校验）。

    - dict：按 key 集合 + 递归比较（顺序无关）
    - list：按顺序递归比较
    - 标量：``type`` 严格相等 + ``==``（区分 ``int`` / ``float`` / ``bool``）
    """
    if type(a) is not type(b):
        # bool 是 int 的子类，需要 type 严格相等
        return False
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(toon_eq(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(toon_eq(x, y) for x, y in zip(a, b))
    return a == b


def assert_round_trip(data: Any, *, _ctx: str = "<root>") -> None:
    """``from_toon(to_toon(data)) == data`` 的断言辅助（dict 顺序无关）。

    不一致时抛 ``AssertionError`` 并指出差异路径。空输入（``to_toon`` 输出 ``""``）
    不参与 round-trip 校验，调用前需自行过滤。
    """
    s = to_toon(data)
    if s == "":
        return  # to_toon 本身对空值有损；这里跳过
    back = from_toon(s)
    if not toon_eq(back, data):
        raise AssertionError(
            f"round-trip 失败 @ {_ctx}\n  in  = {data!r}\n  toon= {s!r}\n  back= {back!r}"
        )
