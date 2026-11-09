import asyncio

import pytest

from aicore.runtime.task import TaskProgress, TaskSuccess
from aicore.tools.dag.base_classes import DAGIR, DAGNode, ExecutionTrace, OperatorContext, OperatorType, PlanExecutionOutput
from aicore.tools.dag.dag_executor import DAGExecutor
from aicore.tools.dag.operator_registry import OperatorRegistry, OperatorResult
from aicore.tools.dag.plan_generator import PlanGeneratorOutput, StructuredPlan
from aicore.tools.dag.plan_processor import process_plan
from aicore.tools.dag.observer import DAGRenderFrame, build_dag_render_graph, emit_dag_frame
from aicore.v2.experiments.dag_v2 import DAGPlanV2StreamWorker

pytestmark = pytest.mark.asyncio


async def test_build_dag_render_graph_includes_rich_task_node_fields():
    first = DAGNode(node_id="s1").model_copy(
        update={
            "operator": OperatorType.WEB_SEARCH,
            "params": {"query": "CA1831 航班状态"},
            "dependencies": [],
            "step_goal": "查询 CA1831 航班状态和实际起飞时间",
            "step_output": ["flight_status", "actual_departure_time"],
        }
    )
    second = DAGNode(node_id="s2").model_copy(
        update={
            "operator": OperatorType.NAVIGATION,
            "params": {"destination": "$s1.airport"},
            "dependencies": ["s1"],
            "step_goal": "导航到首都机场 T3",
            "step_output": ["route"],
        }
    )
    dag_ir = DAGIR(goal="从北京朝阳站出发，查航班、天气、加油站并导航到机场 T3").model_copy(
        update={
            "nodes": {"s1": first, "s2": second},
            "entry_nodes": ["s1"],
            "exit_nodes": ["s2"],
        }
    )

    graph = build_dag_render_graph(
        dag_ir,
        statuses={"s1": "success", "s2": "running"},
        results={"s1": {"flight_status": "计划起飞", "actual_departure_time": "14:05"}},
        errors={},
        progress_per_node={"s1": 100, "s2": 45},
    )

    assert graph.goal == dag_ir.goal
    assert graph.nodes[0].model_dump() == {
        "id": "s1",
        "label": "查询 CA1831 航班状态和实际起飞时间",
        "operator_type": "web_search",
        "status": "success",
        "step_index": 1,
        "goal": "查询 CA1831 航班状态和实际起飞时间",
        "tool_name": "web_search",
        "arguments": {"query": "CA1831 航班状态"},
        "result_summary": "flight_status=计划起飞; actual_departure_time=14:05",
        "result": {"flight_status": "计划起飞", "actual_departure_time": "14:05"},
        "progress_percent": 100,
    }
    assert graph.nodes[1].step_index == 2
    assert graph.nodes[1].tool_name == "navigation"
    assert graph.nodes[1].arguments == {"destination": "$s1.airport"}
    assert graph.nodes[1].result_summary == "执行中"
    assert graph.nodes[1].progress_percent == 45


async def test_dag_executor_render_graph_arguments_prefer_resolved_params():
    first = DAGNode(node_id="s1").model_copy(
        update={
            "operator": OperatorType.WEB_SEARCH,
            "params": {"query": "候选地点"},
            "dependencies": [],
            "step_goal": "查询候选地点",
        }
    )
    node = DAGNode(node_id="s2").model_copy(
        update={
            "operator": OperatorType.NAVIGATION,
            "params": {"destination": "$s1.poi_name"},
            "dependencies": ["s1"],
            "step_goal": "导航到候选地点",
        }
    )
    dag_ir = DAGIR(goal="resolved args").model_copy(
        update={"nodes": {"s1": first, "s2": node}, "entry_nodes": ["s1"], "exit_nodes": ["s2"]}
    )
    executor = DAGExecutor(dag_ir)
    executor.traces["s2"] = ExecutionTrace(
        node_id="s2",
        operator_type="navigation",
        params={"destination": "$s1.poi_name"},
        resolved_params=[{"destination": "国贸大厦"}],
        status="running",
    )

    graph = build_dag_render_graph(
        dag_ir,
        statuses=executor._render_graph_statuses(),
        progress_per_node=executor._render_graph_progress(),
        arguments=executor._render_graph_arguments(),
    )

    by_id = {node.id: node for node in graph.nodes}
    assert by_id["s2"].arguments == {"destination": "国贸大厦"}


async def test_build_dag_render_graph_truncates_long_result_summary():
    node = DAGNode(node_id="s1").model_copy(
        update={
            "operator": OperatorType.WEB_SEARCH,
            "dependencies": [],
            "step_goal": "查询航班状态",
        }
    )
    dag_ir = DAGIR(goal="result truncation").model_copy(
        update={"nodes": {"s1": node}, "entry_nodes": ["s1"], "exit_nodes": ["s1"]}
    )

    graph = build_dag_render_graph(
        dag_ir,
        statuses={"s1": "success"},
        results={"s1": {"answer": "CA1831 航班已于十四点零五分从北京首都机场实际起飞，当前预计准点到达目的地。"}},
    )

    assert graph.nodes[0].result_summary == "answer=CA1831 航班已于十四点零五分从北京首都机场实际..."
    assert graph.nodes[0].result == {
        "answer": "CA1831 航班已于十四点零五分从北京首都机场实际起飞，当前预计准点到达目的地。"
    }


async def test_dag_executor_render_results_prefer_raw_operator_output():
    node = DAGNode(node_id="s1").model_copy(
        update={
            "operator": OperatorType.WEB_SEARCH,
            "dependencies": [],
            "step_goal": "查询真实工具结果",
        }
    )
    dag_ir = DAGIR(goal="raw result").model_copy(
        update={"nodes": {"s1": node}, "entry_nodes": ["s1"], "exit_nodes": ["s1"]}
    )
    executor = DAGExecutor(dag_ir)
    executor.traces["s1"] = ExecutionTrace(
        node_id="s1",
        operator_type="web_search",
        output_data={"answer": "真实工具原始返回"},
        status="success",
    )
    executor.results["s1"] = {"answer": "汇总后的执行结果"}

    assert executor._render_graph_results()["s1"] == {"answer": "真实工具原始返回"}


async def test_dag_v2_stream_worker_installs_observer_without_worker_signature_pollution():
    async def fake_plan_worker(structured_plan: StructuredPlan) -> PlanExecutionOutput:
        await emit_dag_frame(
            DAGRenderFrame(
                phase="build",
                message="DAG构建完成",
                progress_percent=25,
            )
        )
        await emit_dag_frame(
            DAGRenderFrame(
                phase="completed",
                message="DAG执行完成",
                progress_percent=100,
            )
        )
        return PlanExecutionOutput(
            success=True,
            stage="completed",
            message="ok",
            goal=structured_plan.goal,
            steps=len(structured_plan.steps),
            dag_nodes=0,
        )

    worker = DAGPlanV2StreamWorker(plan_worker=fake_plan_worker)

    events = [
        event
        async for event in worker(
            structured_plan=StructuredPlan(goal="empty test plan", steps=[])
        )
    ]

    assert isinstance(events[0], TaskProgress)
    assert [event.progress.message for event in events if isinstance(event, TaskProgress)] == [
        "DAG任务已进入后台执行",
        "DAG构建完成",
        "DAG执行完成",
    ]
    assert all(
        event.progress.component == "dag" and event.progress.event == "snapshot"
        for event in events
        if isinstance(event, TaskProgress)
    )
    assert isinstance(events[-1], TaskSuccess)
    assert events[-1].result.success is True


async def test_dag_v2_stream_worker_cancels_background_plan_when_consumer_closes():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_plan_worker(structured_plan: StructuredPlan) -> PlanExecutionOutput:
        started.set()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        raise AssertionError("background plan should have been cancelled")

    worker = DAGPlanV2StreamWorker(plan_worker=fake_plan_worker)
    stream = worker(structured_plan=StructuredPlan(goal="cancel test", steps=[]))

    first_event = await anext(stream)
    assert isinstance(first_event, TaskProgress)
    await asyncio.wait_for(started.wait(), timeout=1)

    await stream.aclose()

    await asyncio.wait_for(cancelled.wait(), timeout=1)


async def test_dag_v2_stream_worker_emits_failed_frame_for_failed_plan_output():
    async def fake_plan_worker(structured_plan: StructuredPlan) -> PlanExecutionOutput:
        return PlanExecutionOutput(
            success=False,
            stage="exception",
            message="任务执行失败: ValueError: 算子 weather查询工具 不在白名单中",
        )

    worker = DAGPlanV2StreamWorker(plan_worker=fake_plan_worker)

    events = [
        event
        async for event in worker(
            structured_plan=StructuredPlan(goal="invalid operator test", steps=[])
        )
    ]

    progress_frames = [
        event.progress
        for event in events
        if isinstance(event, TaskProgress)
    ]
    failed_frame = progress_frames[-1]

    assert failed_frame.phase == "failed"
    assert failed_frame.status == "failed"
    assert failed_frame.progress_percent == 100
    assert failed_frame.graph is None
    assert "weather查询工具" in failed_frame.message
    assert failed_frame.detail["stage"] == "exception"
    assert isinstance(events[-1], TaskSuccess)
    assert events[-1].result.success is False


async def test_plan_processor_emits_only_render_snapshots():
    emitted: list[DAGRenderFrame] = []

    worker = DAGPlanV2StreamWorker(
        plan_worker=lambda structured_plan: process_plan(  # type: ignore[return-value]
            PlanGeneratorOutput(goal=structured_plan.goal, steps=[]),
        )
    )

    async for event in worker(StructuredPlan(goal="empty", steps=[])):
        if isinstance(event, TaskProgress) and event.progress.message != "DAG任务已进入后台执行":
            emitted.append(event.progress)

    assert [frame.phase for frame in emitted] == ["build", "failed"]
    assert [frame.message for frame in emitted] == [
        "DAG IR构建成功，0个节点",
        "DAG执行失败: 无节点 trace，但 execution_result 为空或整体未通过成功检查",
    ]
    assert emitted[0].graph is not None
    assert emitted[0].graph.nodes == []
    assert emitted[0].graph.edges == []


async def test_dag_executor_emits_node_snapshot_observations(monkeypatch):
    emitted: list[DAGRenderFrame] = []

    class FakeOperator:
        async def execute(self, params_list, context):
            return OperatorResult(success=True).model_copy(
                update={
                    "data": {"answer": "ok"},
                    "node_id": context.metadata["node_id"],
                }
            )

    monkeypatch.setattr(
        OperatorRegistry,
        "get_operator",
        classmethod(lambda cls, operator_type: FakeOperator()),
    )

    node = DAGNode(node_id="s1").model_copy(
        update={
            "operator": OperatorType.WEB_SEARCH,
            "params": {"query": "hello"},
            "dependencies": [],
            "step_output": ["answer"],
        }
    )
    dag_ir = DAGIR(goal="node progress test").model_copy(
        update={
            "nodes": {"s1": node},
            "entry_nodes": ["s1"],
            "exit_nodes": ["s1"],
        }
    )

    async def fake_plan_worker(structured_plan: StructuredPlan) -> PlanExecutionOutput:
        result = await DAGExecutor(dag_ir).execute(OperatorContext(request_id="dag-executor-test"))
        assert result == {"s1": {"answer": "ok"}}
        return PlanExecutionOutput(success=True, stage="completed", message="ok")

    worker = DAGPlanV2StreamWorker(plan_worker=fake_plan_worker)
    async for event in worker(StructuredPlan(goal="node progress test", steps=[])):
        if isinstance(event, TaskProgress) and event.progress.active_node_id:
            emitted.append(event.progress)

    assert [frame.status for frame in emitted] == [
        "running",
        "success",
    ]
    assert emitted[0].active_node_id == "s1"
    assert emitted[0].graph is not None
    assert emitted[0].graph.nodes[0].operator_type == "web_search"
    assert emitted[1].graph is not None
    assert emitted[1].graph.nodes[0].result_summary == "answer=ok"
    assert emitted[1].graph.nodes[0].result == {"answer": "ok"}
