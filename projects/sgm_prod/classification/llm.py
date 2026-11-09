from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ResponseParams, ainvoke_output_by_json

from projects.sgm_prod.classification.assets import load_llm_classification_prompt
from projects.sgm_prod.classification.models import IntentType


class SimpleComplexVerdict(BaseModel):
    is_simple: bool = Field(description="True 为简单意图，False 为复杂意图")


class MultiturnRouteVerdict(BaseModel):
    route: Literal["简单", "复杂"] = Field(description="当前轮应进入简单或复杂")


class MultiturnPlannerState(BaseModel):
    active_route: IntentType | None = Field(default=None, description="上一轮所属落域")
    active_domain: str | None = Field(default=None, description="上一轮业务域，例如 navigation/music")
    status: str | None = Field(default=None, description="上一轮运行状态")
    last_agent: str | None = Field(default=None, description="产生状态的下游系统")
    last_user_query: str | None = Field(default=None, description="上一轮用户输入")
    last_result_summary: str | None = Field(default=None, description="上一轮结构化结果摘要")
    candidates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="上一轮产生的候选列表，例如 POI、歌曲、路线。",
    )
    selected_candidate: dict[str, Any] | None = Field(
        default=None,
        description="上一轮已经明确选中的对象。",
    )
    expected_user_action: str | None = Field(
        default=None,
        description="系统正在等待用户做什么，例如 select_candidate/confirm_execute/refine_result。",
    )
    executable_actions: list[str] = Field(
        default_factory=list,
        description="基于当前状态可以直接执行的动作，例如 navigate/play/cancel。",
    )
    ttl_seconds: int | None = Field(default=None, description="状态有效期")


MULTITURN_ROUTER_PROMPT = """你是车载助手的多轮路由分类器。你只负责判断当前用户输入应进入：
- 简单：明确、可直接执行的导航、音乐、车控、天气等简单能力。
- 复杂：需要推荐、筛选、规划、推理、多工具组合，或承接复杂任务结果的请求。

你可以使用：
1. 当前用户输入。
2. 最近几轮用户输入。
3. 最近几轮已知落域：简单、复杂。

你拿不到系统真实输出，因此不能确认候选列表、页码、播放状态、导航状态是否真实存在。
仅根据语义理解，按照弱流继承规则进行判断。

判定规则：

1. 如果当前输入是完整独立任务，按当前输入重判，不强行继承历史。
   例如：
   - “播放张学友的吻别” -> 简单
   - “导航去深圳湾公园” -> 简单
   - “推荐一个适合带孩子玩的地方” -> 复杂

2. 如果最近有效上下文是简单导航流，当前输入是导航内操作，则判简单。
   包括：
   - 第一个、第二个、最后一个
   - 我想去第几个、我们去第几个、那就去第几个、选择第几个、确定第几个
   - 上一页、下一页、第几页
   - 开始导航、退出导航、取消导航
   - 不走高速、走高速、切换路线
   - 添加/删除/修改途经点
   - 地图放大、切换 3D 模式、导航播报设置
   - 对简单 POI/地点结果的轻量补充或筛选，例如“找带有卫生间的”“找商场停车场”“选一个火锅店”
   - 简单导航流内的路线/目的地状态查询，例如“到火锅店还需要多久”

3. 如果最近有效上下文是简单音乐流，当前输入是音乐内操作，则判简单。
   包括：
   - 暂停、继续、上一首、下一首、切歌
   - 单曲循环、随机播放、取消循环
   - 音量调大/调小
   - 打开/隐藏歌词
   - 退出音乐、停止播放
   - 明确歌曲、歌手、版本、音质切换
   - 对简单音乐播放条件的补充，例如年份/年代、语种、地区、男歌手/女歌手、乐队、曲风、类似某歌手风格
   - 简单音乐流内的场景补充，例如“适合生日听的歌”
   - 简单音乐流内的当前歌曲操作，例如“收藏这首歌”“加入歌单”“单曲循环”“从头播放”

4. 如果最近有效上下文是复杂推荐/筛选/规划任务，当前输入是对结果的选择、继续推荐、筛选补充，则判复杂。
   包括：
   - 第一个、第一首、第3个
   - 最近的那个、评分高的那个
   - 再来一个、换一个类似的
   - 多推荐点、其他的按顺序播放
   - 裸地点、裸 POI、裸歌名线索、裸歌手补充，例如“深圳湾公园”“王力宏和谭维维合唱的那首歌”
   - 复杂流里没有明确新动作的“开始导航吧”“不走高速”“随机播放”“收藏这首歌”
   - “那首/那个/他的/她的/类似/翻唱/作曲”等需要反查或承接复杂结果的表达

5. 如果当前输入明确打断旧任务并给出新简单任务，判简单。
   例如：
   - “导航去深圳湾公园”
   - “换成林俊杰的江南”
   - “播放晴天”
   注意：只有明确包含导航/播放/换成等新动作，才算新简单任务；只有地点名、序号、那个/那首，不算新简单任务。

6. 复杂流经过明确候选选择或具体实体补全后，后续纯导航/地图控制可以判简单。
   例如：
   - 复杂搜索 -> “茶百道” -> “开始吧” 可以判简单
   - 复杂搜索 -> “深圳湾公园” -> “走最快的路” 可以判简单
   但复杂搜索后直接说“开始导航吧”“第一个”“深圳湾公园”，当前轮仍判复杂。

7. 不确定时判复杂。

输出 JSON，不要输出额外解释：

{
  "route": "简单|复杂"
}
"""

STATEFUL_MULTITURN_PLANNER_PROMPT = """你是车载助手的状态化多轮 planner。你只判断当前用户输入应进入：
- 简单：对象和动作已经明确，可以直接执行或查询。
- 复杂：需要推荐、筛选、比较、解释、规划、补充信息检索、多工具组合，或状态不足。

输入里的结构化状态是可信事实，包括候选列表、已选对象、执行状态、系统正在等待的用户动作。

判定原则：
1. 如果当前输入能用状态解析到明确对象，并且动作是可直接执行/控制/查询，判简单。
2. 如果当前输入要求基于候选做新的推荐、筛选、比较、解释、规划，判复杂。
3. 如果当前输入与状态无关，按当前输入本身判断：直接导航/播放/车控/天气判简单；推荐/筛选/比较/推理判复杂。
4. 如果状态缺失、过期、候选不清楚或指代无法解析，判复杂。

输出 JSON，不要输出额外解释：

{
  "route": "简单|复杂"
}
"""


def format_history(history: list[dict[str, Any]] | None) -> str:
    if not history:
        return "无"
    lines: list[str] = []
    for idx, item in enumerate(history[-5:], start=1):
        q = str(item.get("q", "")).strip()
        a = str(item.get("a", "")).strip()
        if q or a:
            lines.append(f"{idx}. 用户：{q}\n   助手：{a}")
    return "\n".join(lines) if lines else "无"


def format_route_history(history: list[dict[str, Any]] | None) -> str:
    if not history:
        return "无"
    lines: list[str] = []
    for idx, item in enumerate(history[-5:], start=1):
        query = str(item.get("query") or item.get("q") or "").strip()
        route = str(item.get("route") or item.get("label") or "").strip()
        if route == "simple":
            route = "简单"
        elif route == "complex":
            route = "复杂"
        if query or route:
            lines.append(f"{idx}. 用户：{query}\n   已知落域：{route or '未知'}")
    return "\n".join(lines) if lines else "无"


def format_planner_state(state: MultiturnPlannerState | dict[str, Any] | None) -> str:
    if not state:
        return "无"
    if isinstance(state, BaseModel):
        payload = state.model_dump(exclude_none=True)
    else:
        payload = state
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


async def llm_fallback(
    query: str,
    *,
    history: list[dict[str, Any]] | None = None,
    prompt: str | None = None,
) -> IntentType:
    client, model = create_client(ModelName.SEED_2_0_MINI_260428, AsyncArk)
    user_prompt = f"""历史对话（按时间正序）：
{format_history(history)}

当前 query：
{query.strip()}"""
    verdict, _ = await ainvoke_output_by_json(
        user_prompt,
        output_type=SimpleComplexVerdict,
        output_schema='{"is_simple": true}',
        client=client,
        model=model,
        params=ResponseParams(
            instructions=prompt or load_llm_classification_prompt(),
            temperature=0,
            max_output_tokens=32,
            store=False,
            caching=None,
            thinking={"type": "disabled"},
        ),
    )
    return "simple" if verdict.is_simple else "complex"


async def llm_multiturn_route(
    query: str,
    *,
    history: list[dict[str, Any]] | None = None,
    prompt: str | None = None,
) -> IntentType:
    client, model = create_client(ModelName.SEED_2_0_MINI_260428, AsyncArk)
    user_prompt = f"""历史用户输入和已知落域（按时间正序）：
{format_route_history(history)}

当前用户输入：
{query.strip()}"""
    verdict, _ = await ainvoke_output_by_json(
        user_prompt,
        output_type=MultiturnRouteVerdict,
        output_schema='{"route": "简单"}',
        client=client,
        model=model,
        params=ResponseParams(
            instructions=prompt or MULTITURN_ROUTER_PROMPT,
            temperature=0,
            max_output_tokens=32,
            store=False,
            caching=None,
            thinking={"type": "disabled"},
        ),
    )
    return "simple" if verdict.route == "简单" else "complex"


async def llm_stateful_multiturn_route(
    query: str,
    *,
    history: list[dict[str, Any]] | None = None,
    state: MultiturnPlannerState | dict[str, Any] | None = None,
    prompt: str | None = None,
) -> IntentType:
    client, model = create_client(ModelName.SEED_2_0_MINI_260428, AsyncArk)
    user_prompt = f"""结构化运行状态：
{format_planner_state(state)}

历史用户输入和已知落域（按时间正序）：
{format_route_history(history)}

当前用户输入：
{query.strip()}"""
    verdict, _ = await ainvoke_output_by_json(
        user_prompt,
        output_type=MultiturnRouteVerdict,
        output_schema='{"route": "简单"}',
        client=client,
        model=model,
        params=ResponseParams(
            instructions=prompt or STATEFUL_MULTITURN_PLANNER_PROMPT,
            temperature=0,
            max_output_tokens=32,
            store=False,
            caching=None,
            thinking={"type": "disabled"},
        ),
    )
    return "simple" if verdict.route == "简单" else "complex"
