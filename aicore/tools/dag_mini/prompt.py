"""DAG Mini — Prompt 拼装纯函数 + chat_agent / TaskAgent 文案常量。"""

from __future__ import annotations

from typing import Any


def build_dep_answers_block(dep_answers: dict[str, str]) -> str:
    """依赖步骤结果 → 拼到 per-step Agent system_prompt 末尾（避免每次 iter user_msg 重复）。"""
    if not dep_answers:
        return ""
    lines = "\n".join(f"[step:{gid}] {ans}" for gid, ans in dep_answers.items())
    return f"\n【依赖 step 累积上下文】\n{lines}"


def build_runtime_context_block(runtime_context: dict[str, str]) -> str:
    """运行时上下文 → 拼到 per-step Agent system_prompt 末尾（避免每次 iter user_msg 重复）。"""
    if not runtime_context:
        return ""
    lines = "\n".join(f"- {k}: {v}" for k, v in runtime_context.items())
    return f"\n【运行时上下文】\n{lines}"


# 默认追加到 per-step Agent 的 system_prompt 后面（Subagent._runner 注入）
SUBAGENT_SYSTEM_PROMPT_SUFFIX = """\
【回复要求】
1. 回复必须包含当前 step_goal 缺失信息的极简说明（如"未找到停车收费信息"），让上游能立即判断"信息是否够用"
2. 若首轮工具结果中已无 step_goal 要求的信息，立即停止工具调用，提取已有信息 + 返回缺失信息说明；不要为凑信息继续无谓工具调用
3. final answer 中：先列"已获取信息"，再列"缺失信息 + 缺失原因（首轮工具无/工具不支持/参数错）"

【工具调用铁律】
4. **同类查询合并 1 次 list 调用**：若 step_goal 涉及"找 N 类设施/查 N 个关键词/列 N 个候选"，必须把 N 个 key 拼成 1 次工具调用（如 POISearch(kinds=["餐厅","停车","充电"])，禁止每类调 1 次
5. **assistant_msg 中具体数字/时间/地点必须从 tool_result 原文摘**：禁止把 tool_result 的数字"再算一次"（如 ETA、距离）；不摘就标"未知"；禁止编造工具里没有的字段
6. **导航成功后停止**：Navigation 工具返回 ETA 即终止，禁止再调 Navigation 验证
7. **音频/播客拿到 1 个候选即停**：PlaylistSearch/AudioPlay 拿到任意非空结果立即终止，禁止为"找更好的"再调
"""


# ============================================================================
# TaskAgent tool 的 description（chat_agent 拆解时用）
# ============================================================================

TASK_AGENT_DESCRIPTION = """\
把多意图 query 拆成 step_goal 列表（s1/s2/...）并调本 tool 执行。目标 ≤ 6 steps、3-4 层 DAG。

【何时调本 tool】query 涉及以下动作时必调：查/找/搜/导航/控车/回忆/推荐/播放/调整/提醒。
query 含 2+ 子任务（"然后/再/最后/顺便"）时也必调。纯知识问答（"X 是什么"）可直答。

【硬约束】tool arguments 必须是严格 JSON，不含任何 prose / markdown 包裹 / 前缀说明，否则解析失败。

【输入 JSON 格式（必须严格遵守）】
{{
  "steps": [
    {{"step_id": "s1", "goal": "...", "depends_on": []}},
    {{"step_id": "s2", "goal": "...", "depends_on": ["s1"]}}
  ]
}}

【5 条拆解硬约束】
1. 条件分支 / 并列子查询 → 合 1 step
2. **独立子目标才拆 step**：A 和 B 无数据依赖、可并行 → 拆 2 step；A 是 B 的子查询、需 B 结果 → 合 1 step 或 B→A
3. **避免"找周边/查资料"过大 step**：若 1 个 step 的 goal 同时涉及"找多类设施 + 查详情 + 综合分析"，per-step agent 会用 ReAct 重复调工具——拆成"找候选" + "查详情" 2 个 step 更稳
"""


# ============================================================================
# chat_agent 系统提示（最外层）
# ============================================================================

CHAT_SYSTEM_PROMPT = """\
你是车机助手。

【铁律】query 涉及以下任一动词 → 必须调 TaskAgent 工具：
  查 / 找 / 搜 / 导航 / 控车 / 回忆 / 推荐 / 播放 / 调整 / 提醒。
（即使 query 看起来只问"一个"问题，只要涉及上述动词，就走 TaskAgent。）

【例外】纯知识问答（"X 是什么 / 为什么 X / 解释 X"，无上述动词）→ 直答。

【完成后】TaskAgent 返回所有 step 的 assistant 结果，按步骤汇总给用户极简回复。
"""


def render_taskagent_description(tools: list[Any]) -> str:
    """把 tool 列表格式化成 LLM 可读的 name+描述 多行文本（按 name 排序便于 diff）。"""
    if not tools:
        return "（无可用 tool）"
    seen: set[str] = set()
    lines: list[str] = []
    for t in tools:
        name = getattr(t, "name", None) or str(t)
        if not name or name in seen:
            continue
        seen.add(name)
        desc = " ".join((getattr(t, "description", "") or "").split())
        lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    return "\n".join(sorted(lines))
