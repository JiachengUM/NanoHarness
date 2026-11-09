import json
import logging
from functools import cached_property
from typing import Dict, Any, Optional, List, Type, Callable, Awaitable, TypeVar, Union

import anyio
import yaml
from pydantic import BaseModel, Field
from aicore.models.credentials import AsyncArk, ModelName, create_client
from aicore.models.responses import ainvoke, ResponseParams
from aicore.tools.dag.operator_models import (
    NavigationParams,
    NavigationOutput,
    POISearchParams,
    SongSearchParams,
    PlaylistSearchParams,
    AlbumSearchParams,
    AudioPlayParams,
    AudioPlayOutput,
    AUDIO_PLAY_ACTIONS,
    CarControlParams,
    CarControlOutput,
    WebSearchParams,
    BaseSchema,
    ConditionParams,
    ConditionOutput,
    ConditionRule,
    MemoryRecallParams,
    MemoryRecallOutput,
    ValidatorParams,
    ValidatorOutput,
)
from aicore.utils.nl_repr import nl_repr
from .base_classes import (
    BaseExecutor,
    ExecutorResult,
    OperatorContext,
    validate_params,
    BuildPromptInput,
    FilterAndStructureInput,
    FilterAndStructureOutput,
    BuildConditionPromptInput,
    ConditionJudgeInput,
    BuildValidatorPromptInput,
    ValidatorJudgeInput,
    BuildMemoryMockPromptInput,
    MemoryMockJudgeInput,
)

logger = logging.getLogger(__name__)


class ClientParams(BaseModel):
    """LLM 客户端参数"""

    model: str = Field(default=ModelName.SEED_1_6_FLASH_250828, description="模型名称")
    params: ResponseParams = Field(
        default=ResponseParams(thinking={"type": "disabled"}),
        description="响应参数配置",
    )

    @cached_property
    def client(self) -> AsyncArk:
        m = ModelName(self.model)
        client, _ = create_client(m, AsyncArk)
        return client


Client = ClientParams()


_T = TypeVar("_T")


async def parallel_map_params(
    func: Callable[[Any], Awaitable[_T]],
    params: List[Any],
    *,
    max_concurrent: int = 10,
) -> List[Any]:
    """并行执行单参异步函数，用于 Executor 内 params 列表并行展开。

    与 aicore/utils/anyio/amap.py 一致：anyio.create_task_group + anyio.Semaphore；
    worker 内 Task 边界异常隔离（不屏蔽，存入 results 供调用方判断）。
    业务逻辑无 try-except，仅 Task 边界处理（符合 AGENTS.md 3.1 精神）。

    Args:
        func: 单参异步函数
        params: 参数列表
        max_concurrent: 最大并发数（默认 10，防资源耗尽）
    """
    if not params:
        return []
    semaphore = anyio.Semaphore(max_concurrent)
    results: List[Any] = [None] * len(params)

    async def worker(index: int, param: Any) -> None:
        async with semaphore:
            # Task 边界异常隔离：不抛出，存入 results，调用方统一判断
            try:
                results[index] = await func(param)
            except BaseException as exc:  # noqa: BLE001 — Task 边界，非业务捕获
                results[index] = exc

    async with anyio.create_task_group() as tg:
        for i, p in enumerate(params):
            tg.start_soon(worker, i, p)
    return results


def _build_filter_prompt(input_data: BuildPromptInput) -> str:
    """构造 LLM 提示词（网页搜索专用）：按 step_goal 筛选 + 按 step_output 结构化。

    与 _build_prompt 的差异：
    - 网页搜索的原始结果通常是文本字段（summary / title），需从中提取信息
      并按 step_output 嵌套路径结构化（如 weather.weather_temperature →
      从 summary 中提取气温 → {{"weather": {{"weather_temperature": "25℃"}}}}）
    - step_output 中声明但无法从候选结果提取的字段，输出 null，不可省略
    """
    return f"""
    你是一个信息筛选与结构化助手。
    【任务说明】
    1. 从"候选结果(all_results)"列表，结合"步骤目标(step_goal)"筛选出满足目标的信息
    2. 按 step_output 中的嵌套路径结构化输出
    3. step_output 中声明但 all_results 里无对应数据的字段，输出 null，不可省略
    4. 如果(step_goal)没有明确说明保留数量，那么最终只返回一条最符合(step_goal)要求的答案

    【步骤输出字段 (step_output)】
    {input_data.step_output}

    【步骤目标 (step_goal)】
    {input_data.step_goal}

    【候选结果 (all_results) 共 {len(input_data.all_results)} 条】
    {json.dumps(input_data.all_results, ensure_ascii=False, indent=2)}

    【输出格式要求】
    - 顶层为 JSON 列表对象；
    - 严格保留 all_results 中字段的原始嵌套结构：若某字段在 all_results 中是 dict，输出中也必须保持相同的嵌套 dict，禁止展平或填空字符串；
    - step_output 中声明的所有字段（含嵌套子字段）必须出现在输出中，all_results 里无对应数据时输出 null；
    - 仅输出最终 JSON
"""


def _extract_step_info_from_context(context: Optional[OperatorContext]) -> tuple:
    """从 OperatorContext 中提取 step_goal 和 step_output。

    Returns:
        (step_goal, step_output) 元组
    """
    if not context:
        return None, None
    exec_ctx = context.execution_context
    if not exec_ctx:
        return None, None
    current_step = exec_ctx.current_step
    return current_step.step_goal, current_step.step_output


def _safe_load_raw_text(raw: str) -> Any:
    """解析 LLM 输出的结构化文本。

    使用 yaml.safe_load 解析；YAML 解析失败时异常自然抛出，由 dag_executor 异常边界统一处理。
    空文本输入时 yaml.safe_load 返回 None，调用方据此判断无结构化结果。
    """
    return yaml.safe_load(
        raw.strip()
        .removeprefix("```json")
        .removeprefix("```python")
        .removeprefix("```")
        .removesuffix("```")
    )


def _build_query_from_fields(
    params: Union[SongSearchParams, PlaylistSearchParams, AlbumSearchParams],
    field_names: List[str],
) -> str:
    """将 params 对象的指定细粒度字段拼接为 query 字符串。

    QQ 音乐 `fcg_music_custom_search.fcg` 只有 `w` 字段（=query），
    将细粒度字段拼接为自由文本以得到更像用户语义的搜索。
    空值字段自动跳过。

    Args:
        params: 算子参数对象（SongSearchParams/PlaylistSearchParams/AlbumSearchParams 等）
        field_names: 需拼接的字段名列表（按顺序拼接）

    Returns:
        拼接后的 query 字符串
    """
    parts = []
    for name in field_names:
        value = getattr(params, name, None)
        if value:
            parts.append(value)
    return " ".join(parts)


async def filter_and_structure_results(
    input_data: FilterAndStructureInput,
    prompt_builder: Callable[[BuildPromptInput], str] = _build_filter_prompt,
) -> FilterAndStructureOutput:
    """依据 step_goal 筛选 all_results，并按 step_output 做结构化输出。

    通用编排：提取 step_goal/step_output → 调用 prompt_builder 构造提示词 →
    ainvoke → 解析 → 包装 FilterAndStructureOutput。不同算子（POI/WebSearch/Music）
    共用此编排，仅 prompt_builder 不同。

    Args:
        input_data: 包含 all_results 和 context 的输入模型
        prompt_builder: 提示词构造器，接收 BuildPromptInput 返回 prompt 字符串

    Returns:
        FilterAndStructureOutput 结构化输出
    """
    step_goal, step_output = _extract_step_info_from_context(input_data.context)

    prompt_input = BuildPromptInput(
        all_results=input_data.all_results,
        step_goal=step_goal or "",
    ).model_copy(
        update={
            "step_output": step_output or [],
        }
    )
    prompt = prompt_builder(prompt_input)

    structured = await ainvoke(
        prompt, client=Client.client, model=Client.model, params=Client.params
    )

    structured_output = _safe_load_raw_text(structured.raw_text)

    return FilterAndStructureOutput(
        results=input_data.all_results,
    ).model_copy(
        update={
            "step_goal": step_goal,
            "step_output": step_output,
            "structured_output": structured_output,
        }
    )


def _build_condition_prompt(input_data: BuildConditionPromptInput) -> str:
    """构造条件判断 LLM 提示词：判断命中规则 + 按 then 模板填充字段值。

    rules_payload 携带 when + then，让 LLM 看到命中后需填充的字段模板；
    then 值可能含自然语言引用（如 $s2中评分最高的地面停车场地址），
    LLM 需综合 facts 全部候选解析引用并填入实际值。
    出参格式要求 LLM 回传 matched_index + result（填充后的 then 值）。
    """
    rules_payload = [
        {"index": i, "when": r.get("when", ""), "then": r.get("then", dict())}
        for i, r in enumerate(input_data.rules)
    ]
    return f"""
    你是一个条件判断助手。
    【任务说明】
    1. 通览"上游信息(facts)"中的全部条目，根据"条件规则表(rules)"按顺序判断哪个 when 条件成立
    2. 对命中规则的 then，按其字段描述填充实际值：then 值为自然语言引用（如 $s2中评分最高的地面停车场地址）时，综合 facts 全部候选解析后填入实际值；then 值为静态值时原样输出
    3. 规则可能涉及跨条目聚合（如"选评分最高的地面停车场"），需综合全部 facts 条目判断与填充
    4. 若所有规则均不成立，matched_index 输出 null，result 输出 null

    【步骤目标 (step_goal)】
    {input_data.step_goal}

    【上游信息 (facts) 共 {len(input_data.facts)} 条】
    {json.dumps(input_data.facts, ensure_ascii=False, indent=2)}

    【条件规则表 (rules) 共 {len(input_data.rules)} 条】
    {json.dumps(rules_payload, ensure_ascii=False, indent=2)}

    【输出格式要求】
    - 输出 JSON: {{"matched_index": 0 或 null, "result": {{命中规则 then 各字段填充后的值}}}}
    - matched_index 为命中规则索引（从 0 开始）；未命中时为 null
    - result 为命中规则 then 填充后的字典；未命中时为 null
    - 仅输出最终 JSON
"""


async def judge_condition(input_data: ConditionJudgeInput) -> ConditionOutput:
    """条件判断编排：提取 step_goal → 构造 prompt → ainvoke → 解析 → 取 result。

    与 filter_and_structure_results 模式一致：复用 Client 单例 + ainvoke +
    _safe_load_raw_text。LLM 输出 matched_index + result（填充后的 then 值），
    优先用 LLM 填充的 result（then 含自然语言引用时由 LLM 据 facts 解析填入实际值），
    回退到本地 rules[matched_index].then（then 为静态值、LLM 未填充时），
    再回退 default，保证结果稳定性。

    Args:
        input_data: 含 facts/rules/default/context 的输入模型

    Returns:
        ConditionOutput 条件判断结果
    """
    step_goal, _ = _extract_step_info_from_context(input_data.context)

    prompt_input = BuildConditionPromptInput(
        facts=input_data.facts,
        rules=input_data.rules,
        step_goal=step_goal or "",
    )
    prompt = _build_condition_prompt(prompt_input)

    structured = await ainvoke(
        prompt, client=Client.client, model=Client.model, params=Client.params
    )
    parsed = _safe_load_raw_text(structured.raw_text) or {}

    matched_index = parsed.get("matched_index")
    llm_result = parsed.get("result")
    if isinstance(matched_index, int) and 0 <= matched_index < len(input_data.rules):
        # 优先用 LLM 填充后的 result（then 含自然语言引用时由 LLM 据 facts 解析填入实际值），
        # 回退到本地 rules[matched_index].then（then 为静态值、LLM 未填充时）
        result = (
            llm_result
            if isinstance(llm_result, dict) and llm_result
            else input_data.rules[matched_index].then
        )
    else:
        result = input_data.default
    return ConditionOutput(**result)


def _build_validator_prompt(input_data: BuildValidatorPromptInput) -> str:
    """构造目标验证 LLM 提示词：判定 step_goal 达成 + 产出节点级改进点。

    参考 _build_condition_prompt 风格：分节标注 + JSON 输出格式要求。
    输入：当前步骤(step_goal/step_output) + 当前产出(current_output) + 历史步骤 +
          下游后继节点(期望字段/step_goal)。
    输出：goal_achieved + confidence + current_improvements + downstream_improvements + reasoning。
    """
    return f"""
    你是一个目标验证助手，负责判定当前步骤是否达成 step_goal，并产出节点级改进点。
    【任务说明】
    1. 通览"当前步骤目标(step_goal)"与"当前产出(current_output)"，判定 step_goal 是否达成
    2. 若未达成，产出"当前节点改进点(current_improvements)"：指明问题类型与改进建议
    3. 综合"下游后继节点(downstream_nodes)"期望从当前节点获取的字段(step_output)与各自 step_goal，
       判定当前产出是否足以支撑下游节点执行；若不足，产出"下游节点改进点(downstream_improvements)"
    4. 改进点的 issue_type 仅限: goal_not_achieved / output_insufficient / output_misaligned / downstream_blocker
    5. 改进点的 severity 仅限: low / medium / high

    【当前步骤目标 (step_goal)】
    {input_data.step_goal}

    【当前步骤出参字段 (step_output)】
    {input_data.step_output}

    【当前产出 (current_output)】
    {json.dumps(input_data.current_output, ensure_ascii=False, indent=2, default=str)}

    【已执行步骤历史 (step_history) 共 {len(input_data.step_history)} 条】
    {json.dumps(input_data.step_history, ensure_ascii=False, indent=2, default=str)}

    【下游后继节点 (downstream_nodes) 共 {len(input_data.downstream_nodes)} 个】
    {json.dumps(input_data.downstream_nodes, ensure_ascii=False, indent=2, default=str)}

    【输出格式要求】
    - 输出 JSON: {{"goal_achieved": true/false, "confidence": "high/medium/low", "current_improvements": [{{"node_id": "当前节点ID", "issue_type": "...", "description": "...", "severity": "..."}}], "downstream_improvements": [{{"node_id": "下游节点ID", "issue_type": "...", "description": "...", "severity": "..."}}], "reasoning": "判断依据简述"}}
    - goal_achieved 为 true 时，current_improvements 输出空列表 []
    - 下游节点无改进需要时，downstream_improvements 输出空列表 []
    - 仅输出最终 JSON
"""


async def validate_goal(input_data: ValidatorJudgeInput) -> ValidatorOutput:
    """目标验证编排：提取上下文 → 构造 prompt → ainvoke → 解析 → 构造 ValidatorOutput。

    与 judge_condition 模式一致：复用 Client 单例 + ainvoke + _safe_load_raw_text。
    从 ExecutionContext 提取当前步骤/历史/产出，与 params.downstream_nodes 合并后构造提示词。
    LLM 输出 JSON（goal_achieved/confidence/current_improvements/downstream_improvements/reasoning），
    解析后构造 ValidatorOutput。异常不捕获，自然向上抛出。
    """
    context = input_data.context
    step_goal = ""
    step_output: List[str] = []
    current_output: Any = None
    step_history: List[Any] = []
    if context is not None and context.execution_context is not None:
        exec_ctx = context.execution_context
        current_step = exec_ctx.current_step
        step_goal = current_step.step_goal
        step_output = list(current_step.step_output)
        step_history = [entry.model_dump() for entry in exec_ctx.step_history]
        current_node_id = current_step.node_id
        current_output = exec_ctx.results.get(current_node_id)

    downstream_nodes = (
        input_data.params.get("downstream_nodes", [])
        if isinstance(input_data.params, dict)
        else []
    )

    prompt_input = BuildValidatorPromptInput(
        step_goal=step_goal,
        step_output=step_output,
        current_output=current_output,
        step_history=step_history,
        downstream_nodes=downstream_nodes,
    )
    prompt = _build_validator_prompt(prompt_input)

    structured = await ainvoke(
        prompt, client=Client.client, model=Client.model, params=Client.params
    )
    parsed = _safe_load_raw_text(structured.raw_text) or {}
    return ValidatorOutput(**parsed)


def _build_memory_mock_prompt(input_data: BuildMemoryMockPromptInput) -> str:
    """构造记忆 Mock 提示词：根据 query 和 memory_type 生成一条简单的事实文本。"""
    return f"""
    你是一个记忆数据模拟器，根据查询要求 mock 出一条真实合理的记忆事实。

    【记忆类型含义】
    - preference: 用户偏好
    - history: 历史记录
    - context: 上下文信息
    - profile: 用户画像

    【步骤目标】
    {input_data.step_goal}

    【查询描述】
    {input_data.query}

    【记忆类型】
    {input_data.memory_type}

    【输出要求】
    直接输出目标实体，不要加任何解释或JSON格式，
    内容要具体真实，符合车内用户场景，直接可以被下游使用。
"""


async def generate_memory_mock(input_data: MemoryMockJudgeInput) -> MemoryRecallOutput:
    """记忆 Mock 编排：提取上下文 → 构造 prompt → ainvoke → 返回 MemoryRecallOutput。"""
    step_goal, _ = _extract_step_info_from_context(input_data.context)

    p = input_data.params
    memory_type = p.get("memory_type", "preference")
    query = p.get("query", "")
    prompt_input = BuildMemoryMockPromptInput(
        query=query,
        memory_type=memory_type,
        step_goal=step_goal or "",
    )
    prompt = _build_memory_mock_prompt(prompt_input)

    structured = await ainvoke(
        prompt, client=Client.client, model=Client.model, params=Client.params
    )
    facts = _safe_load_raw_text(structured.raw_text)

    if not facts:
        facts = f"用户{memory_type}：{query}"

    return MemoryRecallOutput(facts=facts)


def flatten_dict(data: Any) -> Dict[str, Any]:
    """将 BaseModel / dict / list 转换为 dict，保留嵌套结构，跳过 None 值。

    与 step_output 的嵌套声明对齐：例如 POISearchOutput.business: Optional[BusinessItem]
    这样的嵌套 BaseModel 转换后保留为嵌套 dict，使下游 $step_id.business.parking_type
    占位符能按 _resolve_with_diagnosis 的多层路径正确索引。
    旧实现把嵌套 dict 展平为单层（business.parking_type → business_parking_type），
    导致 step_output 中的 business 顶层 key 在数据中丢失，LLM 结构化时只能填空串。

    转换规则：
    - BaseModel → dict（递归转换内部所有 BaseModel 子项）
    - dict → 保留嵌套，递归转换内部 BaseModel 子项，跳过 None
    - list → 保留为 list，递归转换内部 BaseModel 子项
    - 标量 → 原样返回
    - 顶层非 dict / BaseModel 时返回空 dict（调用方约定 row 均为 dict 形态）

    Args:
        data: 待转换的结构（dict / list / BaseModel / 标量）

    Returns:
        保留嵌套结构的字典；顶层非 dict 时返回空字典
    """

    def _convert(v: Any) -> Any:
        """递归把 BaseModel 转 dict，保留 dict/list 嵌套结构，跳过 None 值"""
        if isinstance(v, BaseModel):
            return {
                k: _convert(item)
                for k, item in v.model_dump().items()
                if item is not None
            }
        if isinstance(v, dict):
            return {k: _convert(item) for k, item in v.items() if item is not None}
        if isinstance(v, list):
            return [_convert(item) for item in v]
        return v

    converted = _convert(data)
    return converted if isinstance(converted, dict) else {}


class POISearchExecutor(BaseExecutor):
    """POI搜索执行器 - 封装 poi_search_tool"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return POISearchParams

    async def _poi_single(self, p: POISearchParams) -> List[Dict[str, Any]]:
        """单参执行：POI 工具调用 + flatten_dict 转换。"""
        input_kwargs = {
            "query": p.poi_type,
            "city": p.city,
            "address": p.address,
            "radius": p.radius,
            "limit": p.limit,
        }
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(**input_kwargs)
        return [flatten_dict(row) for row in result]

    @validate_params
    async def execute(
        self,
        params: List[POISearchParams],
        context: Optional[OperatorContext] = None,
    ) -> FilterAndStructureOutput:
        nested = await parallel_map_params(self._poi_single, params)
        all_results: List[Dict[str, Any]] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item  # 上抛由 execute_operator 边界处理，记入 IssueReport
            all_results.extend(item)
        return await filter_and_structure_results(
            FilterAndStructureInput(all_results=all_results, context=context)
        )


class NavigationExecutor(BaseExecutor):
    """导航执行器 - 封装 NavigateTool"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return NavigationParams

    async def _navi_single(self, p: NavigationParams) -> NavigationOutput:
        """单参执行：导航工具调用 + 消息构造。"""
        p_dict = p.model_dump()
        destination = p_dict["destination"]
        command = nl_repr(p_dict)
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(command)
        navi_api_msg = "\n".join(
            [
                "command",
                command,
                "\nresult",
                result.message or result.error_msg,
                json.dumps(result.observation, ensure_ascii=False),
            ]
        )
        return NavigationOutput(message=navi_api_msg).model_copy(
            update={
                "destination": destination,
            }
        )

    @validate_params
    async def execute(
        self,
        params: List[NavigationParams],
        context: Optional[OperatorContext] = None,
    ) -> List[NavigationOutput]:
        nested = await parallel_map_params(self._navi_single, params)
        all_results: List[NavigationOutput] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.append(item)
        return all_results


class SongSearchExecutor(BaseExecutor):
    """单曲搜索"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return SongSearchParams

    @staticmethod
    def _build_effective_query(p: SongSearchParams) -> str:
        """将细粒度字段（song_name/singer_name/lyrics 等）拼为 query。"""
        return _build_query_from_fields(
            p,
            [
                "song_name",
                "singer_name",
                "lyrics",
                "genre",
                "language",
                "year_range",
                "mood",
            ],
        )

    async def _song_single(self, p: SongSearchParams) -> List[Dict[str, Any]]:
        """单参执行：actual_worker 调用 + flatten_dict 转换。"""
        effective_query = self._build_effective_query(p)
        limit: int = getattr(p, "limit", 5)
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(effective_query, criteria=None, limit=limit)
        items = result.songs if hasattr(result, "songs") else result
        return [flatten_dict(row) for row in items]

    @validate_params
    async def execute(
        self,
        params: List[SongSearchParams],
        context: Optional[OperatorContext] = None,
    ) -> FilterAndStructureOutput:
        nested = await parallel_map_params(self._song_single, params)
        all_results: List[Dict[str, Any]] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.extend(item)
        return await filter_and_structure_results(
            FilterAndStructureInput(all_results=all_results, context=context)
        )


class PlaylistSearchExecutor(BaseExecutor):
    """歌单搜索"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return PlaylistSearchParams

    @staticmethod
    def _build_effective_query(p: PlaylistSearchParams) -> str:
        """将细粒度字段（keyword/genre/mood 等）拼为 query。"""
        return _build_query_from_fields(
            p, ["keyword", "genre", "language", "year_range", "mood"]
        )

    async def _playlist_single(self, p: PlaylistSearchParams) -> List[Dict[str, Any]]:
        """单参执行：actual_worker 调用 + flatten_dict 转换。"""
        effective_query = self._build_effective_query(p)
        limit: int = getattr(p, "limit", 5)
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(effective_query, criteria=None, limit=limit)
        items = result.playlists if hasattr(result, "playlists") else result
        return [flatten_dict(row) for row in items]

    @validate_params
    async def execute(
        self,
        params: List[PlaylistSearchParams],
        context: Optional[OperatorContext] = None,
    ) -> FilterAndStructureOutput:
        nested = await parallel_map_params(self._playlist_single, params)
        all_results: List[Dict[str, Any]] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.extend(item)
        return await filter_and_structure_results(
            FilterAndStructureInput(all_results=all_results, context=context)
        )


class AlbumSearchExecutor(BaseExecutor):
    """专辑搜索"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return AlbumSearchParams

    @staticmethod
    def _build_effective_query(p: AlbumSearchParams) -> str:
        """将细粒度字段（album_name/singer_name/genre 等）拼为 query。"""
        return _build_query_from_fields(
            p, ["album_name", "singer_name", "genre", "language", "year_range"]
        )

    async def _album_single(self, p: AlbumSearchParams) -> List[Dict[str, Any]]:
        """单参执行：actual_worker 调用 + flatten_dict 转换。"""
        effective_query = self._build_effective_query(p)
        limit: int = getattr(p, "limit", 5)
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(effective_query, criteria=None, limit=limit)
        items = result.albums if hasattr(result, "albums") else result
        return [flatten_dict(row) for row in items]

    @validate_params
    async def execute(
        self,
        params: List[AlbumSearchParams],
        context: Optional[OperatorContext] = None,
    ) -> FilterAndStructureOutput:
        nested = await parallel_map_params(self._album_single, params)
        all_results: List[Dict[str, Any]] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.extend(item)
        return await filter_and_structure_results(
            FilterAndStructureInput(all_results=all_results, context=context)
        )


class AudioPlayExecutor(BaseExecutor):
    """音频播放执行器 - 封装 MediaTool

    根据 action 类型构建不同的自然语言指令，发送给 MediaTool 执行。
    - play: 播放指定内容（歌曲/歌单/专辑）
    - pause/resume/next/previous: 播放控制
    - set_volume: 音量调节
    - add_to_playlist: 加入播放列表
    """

    def _build_command(self, p: AudioPlayParams) -> str:
        """根据 action 和参数构建自然语言指令。"""
        action_def = next((a for a in AUDIO_PLAY_ACTIONS if a.action == p.action), None)
        template = action_def.command if action_def else p.action

        command = template.format(
            content_name=p.content_name or "",
            volume=p.volume if p.volume is not None else "",
        )

        # play 操作追加可选参数
        if p.action == "play":
            if p.start_position and p.start_position > 0:
                command += f" 从{int(p.start_position)}秒开始"
            if p.auto_continue is False:
                command += " 不自动播放下一首"

        return command

    @property
    def params_model(self) -> Type[BaseSchema]:
        return AudioPlayParams

    async def _audio_single(self, p: AudioPlayParams) -> AudioPlayOutput:
        """单参执行：MediaTool 调用 + 结果包装。"""
        action = p.action
        command = self._build_command(p)
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(command)
        # 兼容多种结果格式
        if hasattr(result, "model_dump"):
            data = result.model_dump()
        elif hasattr(result, "dict"):
            data = result.dict()
        else:
            data = result

        is_success = data.get("status") == "success"
        return AudioPlayOutput(
            status="success" if is_success else "failed",
            action=action,
        ).model_copy(
            update={
                "content_name": p.content_name,
                "is_playing": is_success and action in ("play", "resume"),
                "current_position": p.start_position
                if is_success and action == "play" and p.start_position
                else None,
                "duration": data.get("duration") if is_success else None,
                "volume": p.volume if is_success and action == "set_volume" else None,
                "message": f"执行成功: {'\n'.join([command, nl_repr(data.get('observation', dict()))])}"
                if is_success
                else f"执行失败: {command}",
            }
        )

    @validate_params
    async def execute(
        self,
        params: List[AudioPlayParams],
        context: Optional[OperatorContext] = None,
    ) -> List[AudioPlayOutput]:
        nested = await parallel_map_params(self._audio_single, params)
        all_results: List[AudioPlayOutput] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.append(item)
        return all_results


class CarControlExecutor(BaseExecutor):
    """车控执行器 - 封装 CarControlTool"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return CarControlParams

    async def _car_single(self, p: CarControlParams) -> CarControlOutput:
        """单参执行：车控工具调用 + 结果包装。"""
        command = nl_repr(p)
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(command)

        # 兼容多种结果格式
        if hasattr(result, "model_dump"):
            data = result.model_dump()
        elif hasattr(result, "dict"):
            data = result.dict()
        else:
            data = result

        return CarControlOutput(
            status=data.get("status", "success"),
            action=p.action,
        ).model_copy(
            update={
                "message": data.get("message", ""),
            }
        )

    @validate_params
    async def execute(
        self,
        params: List[CarControlParams],
        context: Optional[OperatorContext] = None,
    ) -> List[CarControlOutput]:
        nested = await parallel_map_params(self._car_single, params)
        all_results: List[CarControlOutput] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.append(item)
        return all_results


class WebSearchExecutor(BaseExecutor):
    """网页搜索执行器 - 封装 WebsearchTool"""

    @property
    def params_model(self) -> Type[BaseSchema]:
        return WebSearchParams

    async def _web_single(self, p: WebSearchParams) -> List[Dict[str, Any]]:
        """单参执行：网页搜索工具调用 + flatten_dict 转换。"""
        worker = getattr(self.tool, "actual_worker", self.tool)
        result = await worker(p.query)
        return [flatten_dict(row) for row in result]

    @validate_params
    async def execute(
        self,
        params: List[WebSearchParams],
        context: Optional[OperatorContext] = None,
    ) -> FilterAndStructureOutput:
        if not self.tool:
            raise RuntimeError("网页搜索工具未初始化")
        nested = await parallel_map_params(self._web_single, params)
        all_results: List[Dict[str, Any]] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.extend(item)
        return await filter_and_structure_results(
            FilterAndStructureInput(all_results=all_results, context=context)
        )


class ConditionExecutor(BaseExecutor):
    """条件算子-执行器：纯 LLM 计算，无需外部工具初始化

    与其他 Executor 不同：不依赖 self.tool，available 恒为 True；
    不使用 @validate_params — _merge_condition_params 将 facts 转为 List[Dict[str, str]]，
    与 ConditionParams.facts: List[str]（Plan 阶段类型）不兼容，因此 execute 直接接收 raw dict，
    手动转换 rules 为 ConditionRule 后构造 ConditionJudgeInput。
    """

    @property
    def params_model(self) -> Type[BaseSchema]:
        return ConditionParams

    @property
    def available(self) -> bool:
        """覆盖：condition 纯 LLM 计算，恒可用，不依赖外部工具注入"""
        return True

    async def execute(
        self,
        params: List[Dict[str, Any]],
        context: Optional[OperatorContext] = None,
    ) -> ConditionOutput:
        # _merge_condition_params 已合并为单条，facts 为 List[Dict[str, str]]，
        # key 为完整引用名（如 s1.weather.weather_temperature），保留解析时引用名直接传递
        # 不走 @validate_params：ConditionParams.facts: List[str] 无法验证 List[Dict] 类型
        if not params:
            raise ValueError("ConditionExecutor.execute 收到空 params 列表")
        p = params[0]
        # rules 为 node.params 序列化形态（List[dict]），统一转为 ConditionRule
        rules: List[ConditionRule] = p.get("rules", [])
        # facts 保留 _merge_condition_params 产出的引用名→值映射（List[Dict[str, str]]）
        facts: List[Dict[str, str]] = p.get("facts", [])
        default: Dict[str, Any] = p.get("default", {})
        return await judge_condition(
            ConditionJudgeInput(
                facts=facts,
                rules=rules,
                default=default,
                context=context,
            )
        )


class MemoryRecallExecutor(BaseExecutor):
    """记忆召回执行器 - LLM mock 记忆数据，无需外部工具初始化

    与 ConditionExecutor 类似：不依赖 self.tool，available 恒为 True；
    不使用 @validate_params — 直接接收 raw dict，调用 LLM 根据 MemoryRecallParams
    mock 出合理的记忆数据供下游算子消费，使 Plan 链路在无真实记忆接口时跑通。
    接口就绪后，将本执行器的 execute 替换为真实接口调用即可。
    """

    @property
    def params_model(self) -> Type[BaseSchema]:
        return MemoryRecallParams

    @property
    def available(self) -> bool:
        """覆盖：纯 LLM 计算，恒可用，不依赖外部工具注入"""
        return True

    async def execute(
        self,
        params: List[Dict[str, Any]],
        context: Optional[OperatorContext] = None,
    ) -> List[MemoryRecallOutput]:
        async def _memory_single(p: Dict[str, Any]) -> MemoryRecallOutput:
            return await generate_memory_mock(
                MemoryMockJudgeInput(
                    params=p,
                    context=context,
                )
            )

        nested = await parallel_map_params(_memory_single, params)
        all_results: List[MemoryRecallOutput] = []
        for item in nested:
            if isinstance(item, BaseException):
                raise item
            all_results.append(item)
        return all_results


class ValidatorExecutor(BaseExecutor):
    """目标验证执行器：纯 LLM 计算，无需外部工具初始化

    与 ConditionExecutor 一致：available 恒为 True，不使用 @validate_params
    （params 含 DownstreamNodeRef 列表，直接接收 raw dict）。
    从 ExecutionContext 提取当前步骤/历史/产出，与 params.downstream_nodes 合并后调用 validate_goal。
    """

    @property
    def params_model(self) -> Type[BaseSchema]:
        return ValidatorParams

    @property
    def available(self) -> bool:
        """覆盖：纯 LLM 计算，恒可用，不依赖外部工具注入"""
        return True

    async def execute(
        self,
        params: List[Dict[str, Any]],
        context: Optional[OperatorContext] = None,
    ) -> ValidatorOutput:
        if not params:
            raise ValueError("ValidatorExecutor.execute 收到空 params 列表")
        p = params[0]
        return await validate_goal(
            ValidatorJudgeInput(
                params=p,
                context=context,
            )
        )


def _unwrap_tool_for_dag_execution(tool: Any) -> Any:
    """Remove v2/clarify async wrappers so DAG nodes receive real results.

    DAG dependency injection needs the actual operator output, not an
    AsyncTaskReceipt. Wrappers in this codebase expose their wrapped tool as
    ``inner_tool``.
    """
    current = tool
    seen: set[int] = set()
    while hasattr(current, "inner_tool") and id(current) not in seen:
        seen.add(id(current))
        current = getattr(current, "inner_tool")
    return current


class ExecutorManager:
    """执行器管理器 - 类级共享状态，无需 __new__ 单例。

    _executors / _initialized 为类属性，所有实例共享同一份状态：
    任意 ExecutorManager() 实例读写均指向类级字典与标志。
    """

    _initialized = False
    _executors: Dict[str, BaseExecutor] = {
        # 地理检索层
        "POISearch": POISearchExecutor(),
        # 功能执行层
        "Navigation": NavigationExecutor(),
        "SongSearch": SongSearchExecutor(),
        "PlaylistSearch": PlaylistSearchExecutor(),
        "AlbumSearch": AlbumSearchExecutor(),
        "AudioPlay": AudioPlayExecutor(),
        "CarControl": CarControlExecutor(),
        # 通用检索层
        "WebSearch": WebSearchExecutor(),
        # 条件判断层（纯 LLM，无需外部工具初始化）
        "Condition": ConditionExecutor(),
        # 记忆召回层（纯转换，无需外部工具初始化）
        "MemoryRecall": MemoryRecallExecutor(),
        # 目标验证层（纯 LLM，无需外部工具初始化；仅 react 循环动态调用）
        "Validator": ValidatorExecutor(),
    }

    def initialize_executors(self, tools: List[Any]) -> None:
        """使用工具列表初始化执行器。

        工具 name 与 executor key 一致时注入工具：
        CarControl / AudioPlay / Navigation / WebSearch / POISearch /
        SongSearch / PlaylistSearch / AlbumSearch。

        以下执行器不依赖 tool 注入，无对应工具：
        - Condition / MemoryRecall / Validator：纯 LLM / 纯转换算子。
        """
        flat_tools = []
        for item in tools:
            if isinstance(item, list):
                flat_tools.extend(item)
            else:
                flat_tools.append(item)

        initialized = 0
        skipped = 0
        for tool in flat_tools:
            if not hasattr(tool, "name"):
                logger.warning(f"跳过非工具对象: {type(tool).__name__}")
                continue

            executor = self._executors.get(tool.name)
            if executor is None:
                logger.info(f"跳过工具（无匹配执行器，按设计无需注入）: {tool.name}")
                skipped += 1
                continue

            execution_tool = _unwrap_tool_for_dag_execution(tool)
            executor.initialize(execution_tool)
            logger.info(f"初始化工具: {tool.name}")
            initialized += 1

        ExecutorManager._initialized = True
        # 未注入工具的执行器：3 个纯 LLM/转换算子（Condition/MemoryRecall/Validator）
        no_inject = len(self._executors) - initialized
        logger.info(
            f"执行器初始化完成：注入 {initialized} 个工具，跳过 {skipped} 个工具，"
            f"共 {len(self._executors)} 个执行器可用（{no_inject} 个无需工具注入）"
        )

    def get_executor(self, executor_type: str) -> Optional[BaseExecutor]:
        """获取指定类型的执行器"""
        return self._executors.get(executor_type)

    def is_executor_available(self, executor_type: str) -> bool:
        """检查指定类型的执行器是否可用"""
        executor = self.get_executor(executor_type)
        return executor is not None and executor.available

    @property
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return ExecutorManager._initialized


# ==================== 便捷函数 ====================


async def execute_operator(
    operator_type: str,
    params: List[Dict[str, Any]],
    context: Optional[OperatorContext] = None,
) -> ExecutorResult:
    """执行算子的便捷函数

    Args:
        operator_type: 算子类型标识
        params: 参数列表（dict 形态，会在 validate_params 中转为 BaseModel）
        context: 算子执行上下文

    Returns:
        ExecutorResult 执行结果

    异常处理：不捕获异常，执行器内部异常自然向上抛出，
    由 DAGExecutor.execute 的 asyncio.Task 边界统一转为 ExceptionIssue，
    符合 AGENTS.md 第 3 条"无捕获·全记录·直抛出"。
    """
    manager = ExecutorManager()

    if not manager.is_initialized:
        logger.warning("执行器未初始化")

    executor = manager.get_executor(operator_type)

    if not executor or not manager.is_executor_available(operator_type):
        logger.warning(f"未找到可用的 {operator_type} 执行器")
        return ExecutorResult(success=False).model_copy(
            update={
                "error": f"执行器不可用: {operator_type}",
            }
        )
    result = await executor.execute(params, context)
    return ExecutorResult(success=True).model_copy(update={"data": result})


def setup_executors(chat_id: str = "dag_executor_chat_id") -> None:
    """显式初始化执行器（替代模块级副作用）。

    应在应用启动阶段调用，而非依赖 import 触发。
    """
    from projects.mind.toolset.dag import get_default_tools

    tools = get_default_tools(chat_id)
    logger.info(f"获取到 {len(tools)} 个工具")
    ExecutorManager().initialize_executors(tools)
    logger.info("执行器初始化成功")
