"""Plan处理模块 - 将PlanGeneratorOutput转换为DAG并执行

提供完整的Plan处理流程：
1. Plan验证结果解析
2. DAG IR构建
3. 安全扫描
4. DAG执行
5. 结果汇总

设计原则：
1. 模块化：每个步骤独立，易于测试和扩展
2. 安全优先：执行前必须通过安全扫描
3. 可追溯：保留完整的执行轨迹
4. 优雅降级：各环节失败时有明确的错误处理
"""

import logging
from typing import Optional, Tuple
from datetime import timedelta

from aicore.tools.dag.plan_generator import PlanGeneratorOutput
from aicore.tools.dag.safety_scanner import SafetyScanner
from aicore.tools.dag.dag_executor import DAGExecutor
from aicore.tools.dag.base_classes import DAGIR, ProcessResult
from aicore.tools.dag.operator_registry import OperatorContext
from aicore.tools.dag.observer import (
    DAGRenderFrame,
    build_dag_render_graph,
    emit_dag_frame,
)
from aicore.tools.dag.issues import IssueReport, IssueUtils

logger = logging.getLogger(__name__)


class PlanProcessor:
    """Plan处理器 - 封装完整的Plan处理流程"""

    def __init__(self):
        self.safety_scanner = SafetyScanner()

    async def process(
        self,
        plan_output: PlanGeneratorOutput,
        context: Optional[OperatorContext] = None,
    ) -> ProcessResult:
        """处理PlanGeneratorOutput，执行完整流程

        创建 IssueReport 贯穿各阶段，统一汇聚 safety/execution 类 Issue，
        最终通过 ProcessResult.issue_report 单一出口返回。

        装饰器化：通过 issue_scope 设置 ContextVar，使被 @capture_issues 装饰的
        检查函数（check_contradictions / scan）自动汇入 issue_report，无需手动 extend。
        """
        result = ProcessResult()
        issue_report = IssueReport()
        # 创建独立 IssueUtils 实例，通过 issue_scope 设置 ContextVar，
        # 使被 @capture_issues 装饰的检查函数自动汇入 issue_report
        issue_utils = IssueUtils(report=issue_report)

        with issue_utils.issue_scope():
            # Step 1: 构建DAG IR（将 dag_build 阶段的结构错误汇入 issue_report）
            result, ok = await self._build_dag_ir(plan_output, result, issue_report)
            if not ok:
                return result.model_copy(update={"issue_report": issue_report})

            # Step 2: 安全扫描（scan 装饰器自动汇入 SafetyIssue）
            result, ok = await self._scan_safety(result, issue_report)
            if not ok:
                return result.model_copy(update={"issue_report": issue_report})

            # Step 3: 执行DAG
            result, ok = await self._execute_dag(result, context, issue_report)
            if not ok:
                return result.model_copy(update={"issue_report": issue_report})

        return result.model_copy(
            update={
                "success": True,
                "stage": "completed",
                "issue_report": issue_report,
            }
        )

    async def _build_dag_ir(
        self,
        plan_output: PlanGeneratorOutput,
        result: ProcessResult,
        issue_report: IssueReport,
    ) -> Tuple[ProcessResult, bool]:
        """将PlanGeneratorOutput转换为DAG IR

        使用 from_plan_with_issues 将 dag_build 阶段的结构错误（缺 step_id / 缺 op）
        转为 ContradictionIssue 汇入 issue_report，通过统一出口返回，
        与 validation/safety_scan/execution 阶段的 issue 化处理一致。
        """
        # 使用 from_plan_with_issues 替代 from_plan，将结构错误 issue 化
        plan_dict = plan_output.model_dump()
        dag_ir, build_issues = DAGIR.from_plan_with_issues(plan_dict)
        if build_issues:
            issue_report.extend(build_issues)
            result = result.model_copy(
                update={
                    "stage": "dag_build",
                    "message": f"DAG IR构建失败:\n{issue_report.summary()}",
                }
            )
            logger.error(result.message)
            return result, False

        result = result.model_copy(
            update={
                "stage": "dag_build",
                "dag_ir": dag_ir,
            }
        )
        await emit_dag_frame(
            DAGRenderFrame(
                phase="build",
                message=f"DAG IR构建成功，{len(dag_ir.nodes)}个节点",
                progress_percent=25,
                graph=build_dag_render_graph(dag_ir),
                status="ready",
            )
        )
        logger.info(f"DAG IR构建成功，{len(dag_ir.nodes)}个节点")
        return result, True

    async def _scan_safety(
        self, result: ProcessResult, issue_report: IssueReport
    ) -> Tuple[ProcessResult, bool]:
        """对DAG进行安全扫描，将 SafetyIssue 汇入 issue_report"""
        if not result.dag_ir:
            result = result.model_copy(
                update={
                    "stage": "safety_scan",
                    "message": "DAG IR为空，无法进行安全扫描",
                }
            )
            logger.error(result.message)
            return result, False

        check_result = self.safety_scanner.scan(result.dag_ir)
        # scan 装饰器已在 issue_scope 内自动汇入 issue_report，无需手动 extend
        # issues 仅用于本地判断（是否有警告），issue_report 是统一出口
        issues = check_result.issues
        result = result.model_copy(
            update={
                "stage": "safety_scan",
            }
        )

        # 检查是否有严重问题（通过 issue_report 统一查询）
        if issue_report.has_critical():
            result = result.model_copy(
                update={"message": f"安全扫描发现严重问题:\n{issue_report.summary()}"}
            )
            logger.error(result.message)
            return result, False

        if issues:
            result = result.model_copy(
                update={"message": f"安全扫描发现警告:\n{issue_report.summary()}"}
            )
            logger.warning(result.message)
        else:
            result = result.model_copy(update={"message": "安全扫描通过"})
            logger.info(result.message)

        return result, True

    async def _execute_dag(
        self,
        result: ProcessResult,
        context: Optional[OperatorContext] = None,
        issue_report: Optional[IssueReport] = None,
    ) -> Tuple[ProcessResult, bool]:
        """执行DAG

        关键行为：
        - issue_report 传入 DAGExecutor.execute，执行阶段的 ExecutionIssue 汇入统一容器。

        成功判定（与 DAGExecutor._pick_ready_nodes 语义对齐）：
        - partial（执行成功但 step_goal 未达成）不算失败，下游节点可正常执行。
        - skipped（上游失败导致跳过）不算独立失败，其严重级别为 MEDIUM。
        - 只要存在 failed 节点即判失败；否则判成功。
        - message 统一用 issue_report.summary()，与 _scan_safety 保持单一出口一致。
        """
        if not result.dag_ir:
            result = result.model_copy(
                update={
                    "stage": "execution",
                    "message": "DAG IR为空，无法执行",
                }
            )
            logger.error(result.message)
            return result, False

        # 防御 issue_report 为 None：内部创建会导致执行阶段 Issue 丢失，需警告
        if issue_report is None:
            issue_report = IssueReport()
            logger.warning(
                "_execute_dag 未传入 issue_report，内部创建可能导致执行阶段 Issue 丢失"
            )

        # --- 创建或复用 OperatorContext ---
        if context is None:
            context = OperatorContext(
                request_id="plan_processor",
                timeout=timedelta(minutes=5),
            )

        # --- 创建执行器并执行（传入 issue_report 收集 ExecutionIssue） ---
        executor = DAGExecutor(result.dag_ir)
        execution_result = await executor.execute(context, issue_report)

        # 执行后用 executor 的最终 DAG 更新 result.dag_ir
        # D3：透传 executor.metrics（节点级执行统计）到 result.metrics，供下游 PlanExecutionOutput.metrics 引用
        result = result.model_copy(
            update={
                "stage": "execution",
                "dag_ir": executor.dag_ir,
                "execution_result": execution_result,
                "trace": dict(executor.traces),
                "metrics": executor.metrics,
            }
        )

        # 成功判定：存在 failed 节点即失败；partial/skipped 不算失败
        has_failure = any(
            trace.status == "failed" for trace in executor.traces.values()
        )
        if not has_failure:
            # 成功：message 用 issue_report.summary() 体现 partial/skipped 警告
            if not issue_report.is_empty():
                message = f"DAG执行成功（含警告）:\n{issue_report.summary()}"
            else:
                message = "DAG执行成功"
            result = result.model_copy(
                update={
                    "success": True,
                    "message": message,
                }
            )
            await emit_dag_frame(
                DAGRenderFrame(
                    phase="completed",
                    message=result.message,
                    progress_percent=100,
                    graph=build_dag_render_graph(
                        executor.dag_ir,
                        **executor.render_graph_snapshot(),
                    ),
                    status="success",
                )
            )
            logger.info(result.message)
            return result, True
        else:
            # 失败：message 用 issue_report.summary()，与 _scan_safety 保持单一出口一致
            message = (
                f"DAG执行失败:\n{issue_report.summary()}"
                if not issue_report.is_empty()
                else "DAG执行失败"
            )
            result = result.model_copy(
                update={
                    "success": False,
                    "message": message,
                }
            )
            await emit_dag_frame(
                DAGRenderFrame(
                    phase="failed",
                    message=result.message,
                    progress_percent=95,
                    graph=build_dag_render_graph(
                        executor.dag_ir,
                        **executor.render_graph_snapshot(),
                    ),
                    status="failed",
                )
            )
            logger.error(result.message)
            return result, False


# 便捷函数
async def process_plan(
    plan_output: PlanGeneratorOutput, context: Optional[OperatorContext] = None
) -> ProcessResult:
    """处理PlanGeneratorOutput的便捷函数"""
    processor = PlanProcessor()
    return await processor.process(plan_output, context)
