"""
多跳 POI 查询工具实验版。

目标：处理「周围带书店的公园」这类需要先召回候选 POI，再围绕每个候选 POI
执行二跳检索的查询。状态只存在单次工具执行期间，不引入长期 subagent 状态。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import cached_property
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aicore.models.chat import ainvoke_output_by_schema
from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.tools import create_tool
from projects.mind.toolset.amap import (
    AroundSearchRequest,
    GeoRequest,
    PoiItem as PoiItemRaw,
    PoiSearchResponse,
    TextSearchRequest,
    amap_around_search,
    amap_geo,
    amap_text_search,
)


TextSearchFn = Callable[[TextSearchRequest], Awaitable[PoiSearchResponse]]
AroundSearchFn = Callable[[AroundSearchRequest], Awaitable[PoiSearchResponse]]
GeoFn = Callable[[GeoRequest], Awaitable[Any]]


class NearbyConstraint(BaseModel):
    """候选 POI 周边必须满足的关系约束。"""

    keywords: str = Field(..., description="周边需要检索的 POI 类型或关键词，如书店、咖啡店")
    radius: int = Field(default=1000, ge=0, le=50000, description="周边检索半径，单位米")
    min_count: int = Field(default=1, ge=1, description="至少需要命中的周边 POI 数量")


class MultiHopPoiPlan(BaseModel):
    """一次多跳 POI 查询的结构化计划。

    这个模型是 planner 和 executor 的边界。
    planner 只负责把自然语言变成计划；executor 只看这个计划执行地图检索。
    这样以后即使把规则 planner 换成 LLM structured output，也不需要改执行逻辑。
    """

    target_keywords: str = Field(..., description="主目标 POI 关键词，如公园")
    city: str | None = Field(default=None, description="搜索城市")
    nearby: list[NearbyConstraint] = Field(default_factory=list, description="周边关系约束")
    candidate_limit: int = Field(default=10, ge=1, le=25, description="主目标最多召回候选数")


class MultiHopPoiInput(BaseModel):
    """多跳 POI 查询输入。"""

    query: str = Field(..., description="自然语言 POI 查询，如：帮我搜一个周围带书店的公园")
    city: str | None = Field(default=None, description="可选城市")
    radius: int = Field(default=1000, ge=0, le=50000, description="周边约束默认半径，单位米")
    candidate_limit: int = Field(default=10, ge=1, le=25, description="主目标最多召回候选数")


PlannerFn = Callable[[MultiHopPoiInput], Awaitable["MultiHopPoiPlan"]]


class MultiHopPoiPlannerParams(BaseModel):
    """多跳 POI 查询计划生成参数。"""

    model: str = Field(default=ModelName.SEED_1_6_FLASH_250828, description="用于结构化解析用户查询的模型")

    @cached_property
    def client(self) -> AsyncArk:
        m = ModelName(self.model)
        client, _ = create_client(m, AsyncArk)
        return client


class RelatedPoiEvidence(BaseModel):
    """一个周边约束的命中证据。"""

    keywords: str = Field(..., description="本次周边检索使用的关键词，对应 NearbyConstraint.keywords，如书店")
    radius: int = Field(..., description="本次周边检索使用的半径，单位米，对应 NearbyConstraint.radius")
    matched_count: int = Field(..., description="在指定半径内命中的相关 POI 数量")
    nearest_distance: int | None = Field(default=None, description="命中的相关 POI 中距离主目标最近的距离，单位米；上游未返回距离时为空")
    pois: list[PoiItemRaw] = Field(default_factory=list, description="本次周边检索命中的原始 POI 列表，用作推荐依据和可解释证据")


class MultiHopPoiCandidate(BaseModel):
    """满足多跳约束的候选 POI 及其证据。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    poi: PoiItemRaw = Field(..., description="第一跳召回的主目标 POI，例如一个公园")
    related: list[RelatedPoiEvidence] = Field(default_factory=list, description="该主目标满足的周边关系证据列表，例如公园周边命中的书店")
    score: float = Field(default=0.0, description="内部排序分数，仅用于候选排序，不代表业务上的绝对评分")
    reason: str = Field(default="", description="面向用户或调试输出的简短推荐理由，由 related 证据生成")


class MultiHopPoiOutput(BaseModel):
    """多跳 POI 查询输出。"""

    query: str = Field(..., description="原始用户查询")
    plan: MultiHopPoiPlan = Field(..., description="本次查询使用的结构化执行计划")
    candidates: list[MultiHopPoiCandidate] = Field(default_factory=list, description="最终满足多跳约束并完成排序的候选 POI 列表")
    message: str = Field(..., description="本次查询的概要说明，例如找到几个候选或失败原因")


class MultiHopPoiState(BaseModel):
    """单次执行期间的临时状态。不会跨工具调用保存。

    这就是所谓“带状态”的部分，但它不是 subagent 的长期记忆。
    每次 __call__ 都会创建一个新的 state，执行完成后就随函数调用结束被释放。
    """

    query: str = Field(..., description="原始用户查询，仅在本次执行期间用于输出回填和调试")
    plan: MultiHopPoiPlan = Field(..., description="本次执行使用的结构化查询计划")
    recalled_targets: list[PoiItemRaw] = Field(default_factory=list, description="第一跳按主目标关键词召回的原始 POI 候选列表")
    candidates: list[MultiHopPoiCandidate] = Field(default_factory=list, description="经过第二跳周边约束过滤和证据补充后的候选列表")


async def plan_multi_hop_poi_query(input: MultiHopPoiInput, params: MultiHopPoiPlannerParams | None = None) -> MultiHopPoiPlan:
    """用 LLM structured output 将自然语言 POI 查询解析成执行计划。

    这里不再写规则 parser。LLM 只负责生成 MultiHopPoiPlan：
    - 主目标搜什么：target_keywords
    - 在哪个城市搜：city
    - 是否需要二跳/多跳周边约束：nearby

    后面的地图检索、候选过滤、排序仍然由确定性代码执行。
    """

    params = params or MultiHopPoiPlannerParams()
    prompt = f"""你是 POI 多跳检索计划生成器。请把用户的自然语言地点需求解析成结构化查询计划。

用户查询:
{input.query}

调用方提供的默认参数:
- city: {input.city}
- nearby 默认半径: {input.radius} 米
- 主目标候选上限: {input.candidate_limit}

解析规则:
1. target_keywords 是第一跳要搜索的主目标 POI 类型或名称，必须尽量短。例如「周围带书店的公园」的 target_keywords 是「公园」。
2. nearby 表示要围绕每个主目标候选继续检索的周边关系约束。
3. 如果用户说「周围带书店的公园」「附近有停车场的餐厅」「旁边有咖啡店的书店」，应生成 nearby 约束。
4. 如果用户没有表达周边关系，只需要单跳搜索，则 nearby 为空列表。
5. 如果用户没有明确周边半径，nearby.radius 使用调用方默认半径 {input.radius}。
6. 如果用户没有明确 min_count，使用 1。
7. 如果用户查询中没有城市，而调用方提供了 city，则 plan.city 使用调用方提供的 city。
8. candidate_limit 使用调用方提供的候选上限 {input.candidate_limit}。
9. 只输出 JSON，不要输出解释文字。

示例:
用户查询: 帮我搜一个周围带书店的公园
输出:
{{
  "target_keywords": "公园",
  "city": "{input.city or '上海'}",
  "nearby": [{{"keywords": "书店", "radius": {input.radius}, "min_count": 1}}],
  "candidate_limit": {input.candidate_limit}
}}
"""
    result = await ainvoke_output_by_schema(
        prompt,
        output_type=MultiHopPoiPlan,
        client=params.client,
        model=params.model,
    )
    plan = result.output

    nearby = [
        constraint.model_copy(update={"radius": constraint.radius or input.radius})
        for constraint in plan.nearby
    ]
    return plan.model_copy(
        update={
            "city": plan.city or input.city,
            "nearby": nearby,
            "candidate_limit": input.candidate_limit,
        }
    )


def _distance_of(poi: PoiItemRaw) -> int | None:
    """把高德返回的 distance 字段转成 int。

    高德模型里 distance 可能是字符串、空列表归一化后的 None，或者不存在。
    排序和证据展示需要数值距离，所以这里集中做容错转换。
    """
    try:
        return int(poi.distance)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


class MultiHopPoiWorker:
    """带执行期状态的多跳 POI worker。"""

    def __init__(
        self,
        *,
        planner: PlannerFn | None = None,
        planner_params: MultiHopPoiPlannerParams | None = None,
        text_search: TextSearchFn = amap_text_search,
        around_search: AroundSearchFn = amap_around_search,
        geo: GeoFn = amap_geo,
    ) -> None:
        self._planner = planner
        self._planner_params = planner_params or MultiHopPoiPlannerParams()
        self._text_search = text_search
        self._around_search = around_search
        self._geo = geo

    async def __call__(
        self,
        query: str,
        city: str | None = None,
        radius: int = 1000,
        candidate_limit: int = 10,
    ) -> MultiHopPoiOutput:
        # 每次工具调用都重新解析计划、创建 state。
        # state 只在这次调用里向后传递，避免跨用户请求残留中间候选。
        input = MultiHopPoiInput(query=query, city=city, radius=radius, candidate_limit=candidate_limit)
        plan = await self._plan(input)
        state = MultiHopPoiState(query=query, plan=plan)

        # 第一跳：召回主目标，例如先找一批「公园」。
        await self._recall_targets(state)

        # 第二跳：围绕每个主目标候选检查关系约束，例如查每个公园周边有没有「书店」。
        await self._apply_nearby_constraints(state)

        # 最后对满足条件的候选排序，并补充人类可读的推荐理由。
        self._rank(state)
        return self._to_output(state)

    async def _plan(self, input: MultiHopPoiInput) -> MultiHopPoiPlan:
        """生成查询计划。

        默认走 LLM structured output；测试或离线 demo 可以注入 planner，
        这样 executor 的多跳逻辑仍可在无网络、无模型的环境里验证。
        """
        if self._planner:
            return await self._planner(input)
        return await plan_multi_hop_poi_query(input, self._planner_params)

    async def _recall_targets(self, state: MultiHopPoiState) -> None:
        """第一跳：按主目标关键词召回候选 POI。

        对「周围带书店的公园」来说，这一步只搜索「公园」。
        注意这里还不判断书店条件，避免把关系约束混进一次 text search 里导致召回不稳。
        """
        rsp = await self._text_search(
            TextSearchRequest(
                keywords=state.plan.target_keywords,
                region=state.plan.city,
                page_size=state.plan.candidate_limit,
            )
        )
        # 后续第二跳 around search 需要坐标。
        # 如果没有 location，但有 address，后面会在 _target_location 里补一次 geo。
        state.recalled_targets = [poi for poi in rsp.pois if poi.name and (poi.location or poi.address)]

    async def _target_location(self, poi: PoiItemRaw, city: str | None) -> str | None:
        """拿到一个候选 POI 的中心坐标。

        优先使用 text search 已经返回的 location；如果没有 location，则用 address 调 geo。
        返回 None 表示这个候选无法作为第二跳 around search 的中心点。
        """
        if poi.location:
            return poi.location
        if not poi.address:
            return None
        geo_rsp = await self._geo(GeoRequest(address=poi.address, city=city))
        if not geo_rsp.geocodes:
            return None
        return geo_rsp.geocodes[0].location

    async def _evaluate_target(self, poi: PoiItemRaw, plan: MultiHopPoiPlan) -> MultiHopPoiCandidate | None:
        """评估一个主目标候选是否满足所有周边关系约束。

        例如候选是「某某公园」，计划要求 nearby=[书店]：
        1. 取公园坐标。
        2. 以公园坐标为中心调用 around_search(keywords=书店)。
        3. 命中数量不足 min_count，则这个公园被过滤掉。
        4. 命中则生成 RelatedPoiEvidence，记录附近有哪些书店、最近距离是多少。
        """
        location = await self._target_location(poi, plan.city)
        if not location:
            return None

        evidences: list[RelatedPoiEvidence] = []
        for constraint in plan.nearby:
            # 一个 plan 可以有多个 nearby 约束。
            # 例如「附近有书店和咖啡店的公园」未来可以表示成两个 NearbyConstraint。
            rsp = await self._around_search(
                AroundSearchRequest(
                    location=location,
                    keywords=constraint.keywords,
                    radius=constraint.radius,
                    page_size=25,
                )
            )
            related_pois = rsp.pois
            if len(related_pois) < constraint.min_count:
                # 当前实现采用 AND 语义：任一约束不满足，候选就被淘汰。
                return None
            distances = [_distance_of(item) for item in related_pois]
            nearest = min((distance for distance in distances if distance is not None), default=None)
            evidences.append(
                RelatedPoiEvidence(
                    keywords=constraint.keywords,
                    radius=constraint.radius,
                    matched_count=len(related_pois),
                    nearest_distance=nearest,
                    pois=related_pois,
                )
            )

        return MultiHopPoiCandidate(poi=poi, related=evidences)

    async def _apply_nearby_constraints(self, state: MultiHopPoiState) -> None:
        """第二跳：对第一跳召回的所有候选并发应用周边约束。"""
        if not state.plan.nearby:
            # 没有关系约束时，退化成普通 POI 搜索结果。
            state.candidates = [MultiHopPoiCandidate(poi=poi, reason="命中主目标关键词") for poi in state.recalled_targets]
            return

        # 每个候选的二跳检索相互独立，所以可以并发执行。
        # return_exceptions=True 让单个候选检索失败不影响其他候选。
        evaluated = await asyncio.gather(
            *(self._evaluate_target(poi, state.plan) for poi in state.recalled_targets),
            return_exceptions=True,
        )
        state.candidates = [
            item for item in evaluated
            if isinstance(item, MultiHopPoiCandidate)
        ]

    @staticmethod
    def _rank(state: MultiHopPoiState) -> None:
        """给满足约束的候选排序并生成 reason。

        当前是一个简单启发式：
        - 附近相关 POI 数量越多越好。
        - 最近相关 POI 越近越好。
        - 主目标自身距离越近越好。

        这个排序不是最终产品级策略，只是让实验版有稳定、可解释的顺序。
        """
        for candidate in state.candidates:
            nearest_values = [
                evidence.nearest_distance
                for evidence in candidate.related
                if evidence.nearest_distance is not None
            ]
            nearest = min(nearest_values, default=50000)
            related_count = sum(evidence.matched_count for evidence in candidate.related)
            target_distance = _distance_of(candidate.poi) or 50000

            # 分数只是内部排序用，不暴露为业务承诺。
            # related_count 权重大，是为了优先推荐确实有周边配套的候选。
            candidate.score = related_count * 1000 - nearest - target_distance * 0.1
            if candidate.related:
                parts = [
                    f"{evidence.radius}米内有{evidence.matched_count}个{evidence.keywords}"
                    + (f"，最近约{evidence.nearest_distance}米" if evidence.nearest_distance is not None else "")
                    for evidence in candidate.related
                ]
                candidate.reason = "；".join(parts)
            else:
                candidate.reason = "命中主目标关键词"

        state.candidates.sort(key=lambda item: item.score, reverse=True)

    @staticmethod
    def _to_output(state: MultiHopPoiState) -> MultiHopPoiOutput:
        """把执行期 state 转成稳定的工具输出。"""
        if not state.recalled_targets:
            message = f"没有召回到「{state.plan.target_keywords}」候选。"
        elif not state.candidates:
            constraints = "、".join(item.keywords for item in state.plan.nearby)
            message = f"召回到{len(state.recalled_targets)}个候选，但没有找到满足周边约束「{constraints}」的结果。"
        else:
            message = f"找到{len(state.candidates)}个满足条件的候选。"
        return MultiHopPoiOutput(query=state.query, plan=state.plan, candidates=state.candidates, message=message)


def multi_hop_poi_tool(worker: MultiHopPoiWorker | None = None):
    """创建多跳 POI 查询工具。"""
    return create_tool(
        name="多跳地点搜索工具",
        description="用于需要多次地理检索的地点搜索，例如：周围带书店的公园、附近有停车场的餐厅、旁边有咖啡店的书店。",
        args_schema=MultiHopPoiInput,
        worker=worker or MultiHopPoiWorker(),
    )


__all__ = [
    "MultiHopPoiInput",
    "MultiHopPoiOutput",
    "MultiHopPoiPlan",
    "MultiHopPoiPlannerParams",
    "MultiHopPoiWorker",
    "NearbyConstraint",
    "RelatedPoiEvidence",
    "multi_hop_poi_tool",
    "plan_multi_hop_poi_query",
]
