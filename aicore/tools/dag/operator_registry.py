import logging
from typing import Dict, Type, Any, Optional, List
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from .base_classes import BaseOperator, OperatorResult, OperatorContext

from .operator_models import (
    POISearchParams, POISearchOutput,
    NavigationParams, NavigationOutput,
    SongSearchParams, SongSearchOutput,
    PlaylistSearchParams, PlaylistSearchOutput,
    AlbumSearchParams, AlbumSearchOutput,
    AudioPlayParams, AudioPlayOutput,
    CarControlParams, CarControlOutput,
    WebSearchParams, WebSearchOutput,
    ConditionParams, ConditionOutput,
    MemoryRecallParams, MemoryRecallOutput,
    ValidatorParams, ValidatorOutput,
    OperatorInfo, OperatorRegistryModel,
)

# ==================== 地理检索层算子 ====================
class POISearchOperator(BaseOperator):
    """POI搜索算子 - 原子能力：周边检索+LLM筛选"""

    @property
    def operator_type(self) -> str:
        return "POISearch"

    @property
    def input_model(self) -> Type[BaseModel]:
        return POISearchParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return POISearchOutput

    @property
    def description(self) -> str:
        return "POI搜索算子：支持周边检索+文本检索"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """搜索类算子不去重，保留 LLM 筛选后的原始结果"""
        return None

    @property
    def is_search_operator(self) -> bool:
        return True


# ==================== 功能执行层算子 ====================
class NavigationOperator(BaseOperator):
    """导航算子 - 原子能力：路线规划"""

    @property
    def operator_type(self) -> str:
        return "Navigation"

    @property
    def input_model(self) -> Type[BaseModel]:
        return NavigationParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return NavigationOutput

    @property
    def description(self) -> str:
        return "导航算子：路线规划，支持多种偏好设置和备选路线"


class SongSearchOperator(BaseOperator):
    """单曲搜索算子 - 原子能力：单曲检索"""

    @property
    def operator_type(self) -> str:
        return "SongSearch"

    @property
    def input_model(self) -> Type[BaseModel]:
        return SongSearchParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return SongSearchOutput

    @property
    def description(self) -> str:
        return "单曲搜索算子：支持歌曲名/歌手名/歌词/语言/流派/年代/氛围等多维度组合搜索，返回单曲列表"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """搜索类算子不去重，保留 LLM 筛选后的原始结果"""
        return None

    @property
    def is_search_operator(self) -> bool:
        return True


class PlaylistSearchOperator(BaseOperator):
    """歌单搜索算子 - 原子能力：歌单检索"""

    @property
    def operator_type(self) -> str:
        return "PlaylistSearch"

    @property
    def input_model(self) -> Type[BaseModel]:
        return PlaylistSearchParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return PlaylistSearchOutput

    @property
    def description(self) -> str:
        return "歌单搜索算子：支持主题关键词/语言/流派/年代/氛围等多维度组合搜索，返回歌单列表"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """搜索类算子不去重，保留 LLM 筛选后的原始结果"""
        return None

    @property
    def is_search_operator(self) -> bool:
        return True


class AlbumSearchOperator(BaseOperator):
    """专辑搜索算子 - 原子能力：专辑检索"""

    @property
    def operator_type(self) -> str:
        return "AlbumSearch"

    @property
    def input_model(self) -> Type[BaseModel]:
        return AlbumSearchParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return AlbumSearchOutput

    @property
    def description(self) -> str:
        return "专辑搜索算子：支持专辑名/歌手名/语言/流派/年代等多维度组合搜索，返回专辑列表"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """搜索类算子不去重，保留 LLM 筛选后的原始结果"""
        return None

    @property
    def is_search_operator(self) -> bool:
        return True


class AudioPlayOperator(BaseOperator):
    """音频播放算子 - 原子能力：媒体控制

    支持操作：play(播放)/pause(暂停)/resume(恢复)/next(下一首)/
    previous(上一首)/set_volume(调音量)/add_to_playlist(加入播放列表)
    """

    @property
    def operator_type(self) -> str:
        return "AudioPlay"

    @property
    def input_model(self) -> Type[BaseModel]:
        return AudioPlayParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return AudioPlayOutput

    @property
    def description(self) -> str:
        return """媒体控制算子：对歌曲、歌单、专辑的执行播放控制，支持播放、暂停、恢复、下一首、上一首、调音量、加入播放列表等操作"""


class CarControlOperator(BaseOperator):
    """车控算子 - 原子能力：车辆控制"""

    @property
    def operator_type(self) -> str:
        return "CarControl"

    @property
    def input_model(self) -> Type[BaseModel]:
        return CarControlParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return CarControlOutput

    @property
    def description(self) -> str:
        return "车控算子：执行车辆控制指令，如空调调节、座椅控制等"

    def _process_success_result(self, op_result: OperatorResult) -> Any:
        """车控算子特殊业务逻辑：从 results 列表取首项转为 CarControlOutput"""
        data = op_result.extract_data()
        if isinstance(data, dict):
            results_list = data.get("results", [])
            if results_list:
                first = results_list[0]
                output = CarControlOutput(**(first.model_dump() if isinstance(first, BaseModel) else first)).model_copy()
                data = output.model_dump()
        return data


# ==================== 通用检索层算子 ====================
class WebSearchOperator(BaseOperator):
    """信息检索算子 - 原子能力：多领域信息查询"""

    @property
    def operator_type(self) -> str:
        return "WebSearch"

    @property
    def input_model(self) -> Type[BaseModel]:
        return WebSearchParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return WebSearchOutput

    @property
    def description(self) -> str:
        return "信息检索算子：支持多领域信息查询"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """搜索类算子不去重，保留 LLM 筛选后的原始结果"""
        return None

    @property
    def is_search_operator(self) -> bool:
        return True


# ==================== 条件判断层算子 ====================
class ConditionOperator(BaseOperator):
    """条件算子-算子：从上游信息做条件分支判断

    复用 _build_prompt 模式（ainvoke + _safe_load），LLM 从 facts 提取
    结构化关键字段并判断命中规则索引，本地取 then 作为 result。
    非搜索类算子（不产出 SearchStrategyIssue），不去重。
    """

    @property
    def operator_type(self) -> str:
        return "Condition"

    @property
    def input_model(self) -> Type[BaseModel]:
        return ConditionParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return ConditionOutput

    @property
    def description(self) -> str:
        return "条件判断算子：从上游信息提取结构化字段并判断条件分支（输入结构必须遵循条件算子结构），输出命中的结果"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        """非搜索类算子，不去重"""
        return None

    @property
    def is_search_operator(self) -> bool:
        return False


# ==================== 记忆召回层算子 ====================
class MemoryRecallOperator(BaseOperator):
    """记忆召回算子 - 原子能力：动态获取后台记忆数据

    当前记忆数据接口未就绪，算子不真正调用接口，
    而是将请求参数转换为向用户索取信息的提问（status='pending_user_input'）。
    非搜索类算子（不产出 SearchStrategyIssue），不去重。
    """

    @property
    def operator_type(self) -> str:
        return "MemoryRecall"

    @property
    def input_model(self) -> Type[BaseModel]:
        return MemoryRecallParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return MemoryRecallOutput

    @property
    def description(self) -> str:
        return "记忆召回算子：动态获取后台记忆数据（接口未就绪时返回向用户索取信息的提问）"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        return None

    @property
    def is_search_operator(self) -> bool:
        return False


# ==================== 目标验证算子 ====================
class ValidatorOperator(BaseOperator):
    """目标验证算子：在 react 循环中动态调用，基于 step_goal + 执行历史 + 下游需求
    做结构化目标达成判定，产出节点级改进点（当前节点 + 下游后继节点）。

    纯 LLM 计算（无外部工具依赖），非搜索类算子，不去重。
    仅由 DAGExecutor 动态调用，不进入 PlanStep Union（LLM 不可显式规划）。
    """

    @property
    def operator_type(self) -> str:
        return "Validator"

    @property
    def input_model(self) -> Type[BaseModel]:
        return ValidatorParams

    @property
    def output_model(self) -> Type[BaseModel]:
        return ValidatorOutput

    @property
    def description(self) -> str:
        return "目标验证算子：基于step_goal和执行过程验证目标完成情况，返回节点级改进点（含下游后继节点改进）"

    @property
    def dedup_fields(self) -> Optional[List[str]]:
        return None

    @property
    def is_search_operator(self) -> bool:
        return False


# ==================== 算子注册表 ====================
class OperatorRegistry:
    """算子注册表，单例模式，按类型注册和查询算子"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._operators: Dict[str, BaseOperator] = {}
            cls._instance._register_operators()
        return cls._instance

    def _register_operators(self):
        """注册所有算子"""
        operators = [
            POISearchOperator(),
            NavigationOperator(),
            SongSearchOperator(),
            PlaylistSearchOperator(),
            AlbumSearchOperator(),
            AudioPlayOperator(),
            CarControlOperator(),
            WebSearchOperator(),
            ConditionOperator(),
            MemoryRecallOperator(),
            ValidatorOperator()
        ]

        for op in operators:
            self._operators[op.operator_type] = op

        logger.info(f"算子注册完成，共 {len(self._operators)} 个算子")

    @classmethod
    def _ensure_instance(cls):
        """确保单例已初始化"""
        if cls._instance is None:
            cls._instance = cls()

    @classmethod
    def get_operator(cls, operator_type: str) -> Optional[BaseOperator]:
        """获取指定类型的算子"""
        cls._ensure_instance()
        return cls._instance._operators.get(operator_type)

    @classmethod
    def get_registry_model(cls) -> OperatorRegistryModel:
        """获取注册表的Pydantic模型表示"""
        cls._ensure_instance()

        operators = {
            op_type: OperatorInfo(
                operator_type=op.operator_type,
                description=op.description,
                input_model=op.input_model,
                output_model=op.output_model,
            )
            for op_type, op in cls._instance._operators.items()
        }
        return OperatorRegistryModel().model_copy(update={"operators": operators})
