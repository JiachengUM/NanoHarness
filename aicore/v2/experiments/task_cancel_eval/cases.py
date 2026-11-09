"""取消任务能力测评用例与确定性业务工具模拟。

本数据集只测试 Agent 是否正确理解并执行“取消异步任务”：

- 是否在正确的轮次调用取消工具；
- 是否选中正确的异步任务；
- 目标不唯一时是否澄清；
- 没有目标、任务已结束或用户否定取消时是否拒绝误调用。

天气、地点搜索和车控不是本测评的对象。这里保留它们的真实工具 schema
和真实 ``TaskManager`` 提交流程，仅替换外部业务 worker，以消除网络请求、
真实业务结果和不可控耗时：

- 天气与地点搜索默认永久等待，用来稳定模拟 pending/running 异步任务；
- ``WorkerSimulation.weather_completes`` 可让天气立即完成，用来覆盖终态任务；
- 车控立即成功，用来提供一个同步工具干扰项。

使用方式：

1. 从 ``CANCEL_TOOL_CASES`` 选择单条或全量 case；
2. 用 ``build_simulated_business_tools`` 构造确定性业务工具；
3. 在 ``task_cancel_eval.eval`` 中追加待测取消工具并构造 Agent；
4. 交给 ``task_cancel_eval.runner`` 运行，runner 会同时观察模型发出的
   原始取消工具参数和真实 ``TaskManager.cancel_task`` 调用，并按每轮
   expectation 判分；需要验证候选规模时可设置
   ``expected_active_tasks_after``。

新增取消工具版本时不应复制 case 或 worker，只需新增 Agent adapter。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import anyio

from aicore.runtime.task import TaskManager
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.v2.experiments.poi_search_v2 import (
    PoiSearchOutput,
    poi_search_v2_tool,
)
from aicore.v2.experiments.sgm_tools_v2 import (
    car_control_v2_tool,
)
from aicore.v2.experiments.weather_v2 import (
    WeatherSearchOutput,
    weather_search_v2_tool,
)
from projects.sgm_prod.tools.CarControl import CarControlOutput

__all__ = [
    "CANCEL_TOOL_CASES",
    "CancelCaseTurn",
    "CancelDecision",
    "CancelExpectation",
    "CancelToolCase",
    "ExpectedCancelOutcome",
    "ExpectedCancelTarget",
    "WorkerSimulation",
    "build_simulated_business_tools",
]


type CancelDecision = Literal["none", "call", "clarify", "reject"]
type ExpectedCancelOutcome = Literal["accepted", "already_terminal"]


@dataclass(frozen=True)
class ExpectedCancelTarget:
    tool_name: str
    argument_contains: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CancelExpectation:
    decision: CancelDecision
    targets: tuple[ExpectedCancelTarget, ...] = ()
    outcomes: tuple[ExpectedCancelOutcome, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        if not self.note:
            raise ValueError("每一轮都必须写明取消意图预期")
        if self.decision == "call":
            if not self.targets:
                raise ValueError("call 预期必须包含取消目标")
            if len(self.targets) != len(self.outcomes):
                raise ValueError("每个取消目标都必须有对应 outcome")
        elif self.targets or self.outcomes:
            raise ValueError(f"{self.decision} 预期不能包含取消目标或 outcome")


@dataclass(frozen=True)
class CancelCaseTurn:
    query: str
    delay: float
    expectation: CancelExpectation
    expected_active_tasks_after: int | None = None

    def __post_init__(self) -> None:
        if (
            self.expected_active_tasks_after is not None
            and self.expected_active_tasks_after < 0
        ):
            raise ValueError("expected_active_tasks_after 不能小于 0")


@dataclass(frozen=True)
class WorkerSimulation:
    """描述某个 case 需要的特殊 worker 完成行为。"""

    weather_completes: bool = False


@dataclass(frozen=True)
class CancelToolCase:
    """一组共享同一对话历史和 worker 模拟配置的多轮取消用例。"""

    turns: tuple[CancelCaseTurn, ...]
    simulation: WorkerSimulation = WorkerSimulation()


def _target(
    tool_name: str,
    **argument_contains: str,
) -> ExpectedCancelTarget:
    return ExpectedCancelTarget(
        tool_name=tool_name,
        argument_contains=tuple(argument_contains.items()),
    )


def _none(note: str) -> CancelExpectation:
    return CancelExpectation(decision="none", note=note)


def _clarify(note: str) -> CancelExpectation:
    return CancelExpectation(decision="clarify", note=note)


def _reject(note: str) -> CancelExpectation:
    return CancelExpectation(decision="reject", note=note)


def _call(
    *targets: ExpectedCancelTarget,
    outcomes: tuple[ExpectedCancelOutcome, ...] | None = None,
    note: str,
) -> CancelExpectation:
    return CancelExpectation(
        decision="call",
        targets=targets,
        outcomes=outcomes or tuple("accepted" for _ in targets),
        note=note,
    )


WEATHER_HONG_KONG = _target("天气查询工具", query="香港")
WEATHER_BEIJING = _target("天气查询工具", query="北京")
WEATHER_GUANGZHOU = _target("天气查询工具", query="广州")
WEATHER_SHANGHAI = _target("天气查询工具", query="上海")
POI_SHANGHAI_HOTEL = _target(
    "地点搜索工具",
    query="酒店",
    city="上海",
)
POI_HONG_KONG_HOTEL = _target(
    "地点搜索工具",
    query="酒店",
    city="香港",
)
POI_JAPANESE_RESTAURANT = _target("地点搜索工具", query="日料")
POI_HEMA = _target("地点搜索工具", query="盒马")
POI_HOTPOT = _target("地点搜索工具", query="火锅")
POI_SHANGHAI_PRIVATE_ROOM_CAFE = _target(
    "地点搜索工具",
    query="咖啡",
    city="上海",
    criteria="有包间",
)


CANCEL_TOOL_CASES: dict[str, CancelToolCase] = {
    "running_task_cancel": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "帮我在上海徐家汇找一家适合入住的酒店，人均100左右",
                0.0,
                _none("提交酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "停掉酒店查询",
                9.0,
                _call(POI_SHANGHAI_HOTEL, note="正常取消运行中的酒店查询"),
            ),
        ),
    ),
    "ambiguous_cancel_multiple_tasks": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港今天的天气，上海徐家汇找一家适合入住的酒店，人均100左右",
                0.0,
                _none("并行提交天气和酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消任务",
                9.0,
                _clarify("天气和酒店均可取消，目标不唯一，必须反问澄清"),
            ),
        ),
    ),
    "targeted_cancel_one_of_many": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港今天的天气，上海徐家汇找一家适合入住的酒店，人均100左右",
                0.0,
                _none("并行提交天气和酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消酒店查询",
                9.0,
                _call(
                    POI_SHANGHAI_HOTEL,
                    note="只取消酒店查询，香港天气继续执行",
                ),
            ),
        ),
    ),
    "cancel_already_terminal_task": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查一下香港今天的天气",
                0.0,
                _none("提交天气查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消刚才天气",
                20.0,
                _reject("天气结果已经回灌，已完成任务不能再次调用取消工具"),
            ),
        ),
        simulation=WorkerSimulation(weather_completes=True),
    ),
    "single_task_status_query": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查一下香港今天的天气",
                0.0,
                _none("提交天气查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "现在查到哪了",
                5.0,
                _none("这是进度查询，不是取消意图"),
            ),
        ),
    ),
    "modify_task_supersedes_old": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "帮我在香港找一家人均100的酒店",
                0.0,
                _none("提交香港酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "换成上海的",
                5.0,
                _call(
                    POI_HONG_KONG_HOTEL,
                    note="修改任务应先取消旧香港酒店查询，再提交上海查询",
                ),
            ),
        ),
    ),
    "modify_poi_add_filters": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "帮我查一家日料店，人均200吧",
                0.0,
                _none("提交日料查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "换成人均100左右、安静的",
                5.0,
                _call(
                    POI_JAPANESE_RESTAURANT,
                    note="增加筛选条件属于修改，应先取消旧日料查询",
                ),
            ),
        ),
    ),
    "double_cancel_same_task": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "帮我在上海徐家汇找一家适合入住的酒店，人均100左右",
                0.0,
                _none("提交酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消酒店查询",
                15.0,
                _call(POI_SHANGHAI_HOTEL, note="第一次正常取消酒店查询"),
            ),
            CancelCaseTurn(
                "再取消一次酒店查询",
                15.0,
                _reject("第一次已经取消成功，不应再次调用取消工具"),
            ),
        ),
    ),
    "cancel_then_late_result_should_not_backfill": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查一下香港今天的天气",
                0.0,
                _none("提交天气查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消天气查询",
                5.0,
                _call(WEATHER_HONG_KONG, note="正常取消运行中的天气查询"),
            ),
            CancelCaseTurn(
                "刚才取消后还有结果回来吗？",
                10.0,
                _none("核对取消结果，不应再次调用取消工具"),
            ),
        ),
    ),
    "double_cancel_ask_history": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "帮我在上海徐家汇找一家适合入住的酒店，人均100左右",
                0.0,
                _none("提交酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消酒店查询",
                15.0,
                _call(POI_SHANGHAI_HOTEL, note="第一次正常取消酒店查询"),
            ),
            CancelCaseTurn(
                "再取消一次酒店查询",
                15.0,
                _reject("第一次已经取消成功，不应再次调用取消工具"),
            ),
            CancelCaseTurn(
                "诶之前查了啥？",
                5.0,
                _none("历史查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "还是再查一下吧",
                5.0,
                _none("重新提交酒店查询，不应调用取消工具"),
            ),
        ),
    ),
    "cancel_all_then_new_task_same_turn": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港过去7天的天气，再找一家上海徐家汇酒店人均100",
                0.0,
                _none("并行提交天气和酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "都取消，然后查一下上海明天的天气",
                7.0,
                _call(
                    WEATHER_HONG_KONG,
                    POI_SHANGHAI_HOTEL,
                    note="取消全部旧任务；上海天气是新的独立查询",
                ),
            ),
        ),
    ),
    "cancel_one_then_follow_other": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港今天的天气，再找一家上海徐家汇酒店人均100",
                0.0,
                _none("并行提交天气和酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消天气查询",
                3.0,
                _call(
                    WEATHER_HONG_KONG,
                    note="只取消香港天气，酒店查询继续执行",
                ),
            ),
            CancelCaseTurn(
                "那酒店找到了吗？",
                3.0,
                _none("跟进未取消的酒店查询，不应调用取消工具"),
            ),
        ),
    ),
    "cancel_task_which_not_right": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港今天的天气，再找一家上海徐家汇酒店人均100",
                0.0,
                _none("并行提交香港天气和上海酒店查询"),
            ),
            CancelCaseTurn(
                "别查上海的天气了",
                5.0,
                _reject("历史中没有上海天气任务，不能猜测或取消其他任务"),
            ),
        ),
    ),
    "ambiguous_clarify_then_cancel": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港今天的天气，再找一家上海徐家汇酒店人均100",
                0.0,
                _none("并行提交天气和酒店查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "先不用了，别查了",
                7.0,
                _clarify("天气和酒店均可取消，必须反问目标"),
            ),
            CancelCaseTurn(
                "酒店",
                5.0,
                _call(
                    POI_SHANGHAI_HOTEL,
                    note="用户澄清后只取消酒店查询",
                ),
            ),
        ),
    ),
    "cancel_control_not_async_task": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "找一家上海徐家汇附近的盒马超市评分高的，然后空调开到我喜欢的温度",
                0.0,
                _none("提交盒马查询并同步执行车控，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "别开空调了，取消取消",
                7.0,
                _reject("目标是同步车控，不应误取消仍在执行的地点查询"),
            ),
        ),
    ),
    "cancel_search_with_sync_control": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "找一家上海徐家汇附近的盒马超市评分高的，然后空调开到我喜欢的温度",
                0.0,
                _none("提交盒马查询并同步执行车控，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "别查了",
                7.0,
                _call(POI_HEMA, note="取消仍在异步执行的盒马查询"),
            ),
        ),
    ),
    "same_tool_two_instances_targeted_cancel": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查香港今天的天气，再查上海今天的天气",
                0.0,
                _none("同一工具提交两个不同城市的天气任务"),
            ),
            CancelCaseTurn(
                "取消上海天气",
                3.0,
                _call(
                    WEATHER_SHANGHAI,
                    note="只取消上海天气，香港天气继续执行",
                ),
            ),
        ),
    ),
    "same_argument_collision_needs_clarification": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "在上海找一家酒店，人均100；再找一家上海评分4分，人均100的西班牙餐厅",
                0.0,
                _none("同一工具提交两个参数相近的地点任务"),
            ),
            CancelCaseTurn(
                "取消那个",
                5.0,
                _clarify("两个地点任务都可能匹配，必须反问具体目标"),
            ),
        ),
    ),
    "negative_cancel_utterance": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查一下香港今天的天气",
                0.0,
                _none("提交天气查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "先不用取消，查到了再告诉我",
                0.5,
                _none("明确否定取消，天气任务应继续执行"),
            ),
        ),
    ),
    "cancel_without_active_task": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "取消任务",
                0.0,
                _reject("历史中没有任务占位回执，不能调用取消工具"),
            ),
        ),
    ),
    "cancel_then_restart_same_goal": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查一下香港今天的天气",
                0.0,
                _none("提交天气查询，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消天气查询",
                0.5,
                _call(WEATHER_HONG_KONG, note="正常取消香港天气查询"),
            ),
            CancelCaseTurn(
                "重新查香港天气",
                0.5,
                _none("重新提交新的天气查询，不应再次取消旧任务"),
            ),
        ),
    ),
    "async_and_sync": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "打开车窗，然后查一下上海今天的天气，我需要带伞吗？"
                " 再在上海徐汇滨江附近找一家人均100的火锅店",
                0.0,
                _none("同步车控与两个异步查询并行，不应调用取消工具"),
            ),
            CancelCaseTurn(
                "取消火锅店",
                8.0,
                _call(
                    POI_HOTPOT,
                    note="只取消火锅店查询，天气查询不受影响",
                ),
            ),
        ),
    ),
    "five_active_easy_unique_target": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请同时查香港、北京、广州今天的天气，"
                "再找上海徐家汇附近的酒店和火锅店",
                0.0,
                _none("并行提交五个差异明显的异步任务"),
                expected_active_tasks_after=5,
            ),
            CancelCaseTurn(
                "取消火锅店查询",
                5.0,
                _call(
                    POI_HOTPOT,
                    note="五个活跃任务中取消具有唯一关键词的火锅店查询",
                ),
            ),
        ),
    ),
    "five_active_same_tool_target": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请同时查香港、北京、广州、上海和深圳今天的天气",
                0.0,
                _none("同一天气工具并行提交五个不同城市任务"),
                expected_active_tasks_after=5,
            ),
            CancelCaseTurn(
                "取消广州天气查询",
                5.0,
                _call(
                    WEATHER_GUANGZHOU,
                    note="五个同工具实例中按城市取消广州天气",
                ),
            ),
        ),
    ),
    "conjunctive_target_not_expressible": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "分别查找上海的酒店、北京的酒店和上海的餐厅",
                0.0,
                _none("提交三个字段交叉重叠的地点任务"),
                expected_active_tasks_after=3,
            ),
            CancelCaseTurn(
                "取消上海的酒店查询",
                5.0,
                _call(
                    POI_SHANGHAI_HOTEL,
                    note=(
                        "目标需要同时结合城市和地点类型；"
                        "单个字段都不能唯一标识"
                    ),
                ),
            ),
        ),
    ),
    "non_string_argument_target": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "在上海徐家汇分别找两家咖啡店，"
                "一家要求安静，另一家要求有包间",
                0.0,
                _none("提交两个只在 criteria 列表上不同的地点任务"),
                expected_active_tasks_after=2,
            ),
            CancelCaseTurn(
                "取消有包间的咖啡店查询，安静的继续",
                5.0,
                _call(
                    POI_SHANGHAI_PRIVATE_ROOM_CAFE,
                    note="根据非字符串 criteria 参数取消有包间的任务",
                ),
            ),
        ),
    ),
    "cancel_subset_of_five": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请同时查香港、北京、广州今天的天气，"
                "再找上海徐家汇附近的酒店和火锅店",
                0.0,
                _none("并行提交五个异步任务"),
                expected_active_tasks_after=5,
            ),
            CancelCaseTurn(
                "取消北京天气和火锅店查询，其他继续",
                5.0,
                _call(
                    WEATHER_BEIJING,
                    POI_HOTPOT,
                    note="五个活跃任务中准确取消两个目标",
                ),
            ),
        ),
    ),
    "stale_task_id_history": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请同时查香港、北京、广州、上海和深圳今天的天气",
                0.0,
                _none("提交五个会快速完成的天气任务，制造历史 task_id"),
            ),
            CancelCaseTurn(
                "再帮我找上海徐家汇附近的酒店",
                20.0,
                _none("天气均已结束后提交一个新的酒店任务"),
                expected_active_tasks_after=1,
            ),
            CancelCaseTurn(
                "取消现在这个酒店查询",
                5.0,
                _call(
                    POI_SHANGHAI_HOTEL,
                    note="不能从历史中误选已经完成的天气 task_id",
                ),
            ),
        ),
        simulation=WorkerSimulation(weather_completes=True),
    ),
    "restart_same_goal_cancel_new_instance": CancelToolCase(
        turns=(
            CancelCaseTurn(
                "请查一下香港今天的天气",
                0.0,
                _none("提交第一个香港天气任务"),
                expected_active_tasks_after=1,
            ),
            CancelCaseTurn(
                "取消天气查询",
                0.5,
                _call(
                    WEATHER_HONG_KONG,
                    note="取消第一个香港天气任务",
                ),
            ),
            CancelCaseTurn(
                "重新查香港天气",
                0.5,
                _none("重新提交同目标的新天气任务"),
            ),
            CancelCaseTurn(
                "再取消刚重新提交的香港天气",
                0.5,
                _call(
                    WEATHER_HONG_KONG,
                    note="必须取消新实例，不能复用第一次的旧 task_id",
                ),
            ),
        ),
    ),
}


def build_simulated_business_tools(
    *,
    task_manager: TaskManager,
    case: CancelToolCase,
) -> list[TaskToolProtocolGeneral]:
    """按 case 构造业务工具，只 mock worker，不 mock 工具和任务运行时。

    返回的工具仍通过正式的 async tool wrapper 向 ``TaskManager`` 提交任务，
    因此占位回执、pending/running 状态、取消执行和结果回灌路径均为真实实现。
    """

    async def weather_worker(
        query: str,
        criteria: list[str] | None = None,
    ) -> WeatherSearchOutput:
        if not case.simulation.weather_completes:
            await anyio.sleep_forever()
        return WeatherSearchOutput(message=f"[模拟完成] 天气查询: {query}")

    async def poi_worker(
        query: str,
        city: str | None = None,
        address: str | None = None,
        criteria: list[str] | None = None,
        radius: int = 3000,
    ) -> PoiSearchOutput:
        await anyio.sleep_forever()
        return PoiSearchOutput(message=f"[模拟完成] 地点搜索: {query}")

    async def car_control_worker(command: str) -> CarControlOutput:
        return CarControlOutput(
            status="success",
            message=f"[模拟执行] {command}",
        )

    return [
        weather_search_v2_tool(
            worker=weather_worker,
            timeout=None,
            task_manager=task_manager,
        ),
        poi_search_v2_tool(
            worker=poi_worker,
            timeout=None,
            task_manager=task_manager,
        ),
        car_control_v2_tool(
            worker=car_control_worker,
            timeout=None,
            task_manager=task_manager,
        ),
    ]
