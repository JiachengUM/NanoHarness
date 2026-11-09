"""DAG 工具模块 — 统一日志初始化

本模块在导入时为 ``aicore.tools.dag.*`` 命名空间下的所有子 logger
配置一个带文件名 / 行号的 fallback handler。若调用方已在根 logger
配置了 handler，则子 logger 借助 ``propagate = True`` 继承上层格式化器；
否则会自动添加一个控制台 handler，保证文件名和行号始终出现在日志中。
"""
import logging
import sys

_DAG_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"


def _setup_dag_logger() -> None:
    """为 ``aicore.tools.dag`` 命名空间配置一个带 filename:lineno 的 fallback handler。"""
    dag_root_logger = logging.getLogger("aicore.tools.dag")
    dag_root_logger.setLevel(logging.INFO)
    dag_root_logger.propagate = True

    # 遍历 logger 树：如果上层已有 handler，说明调用方做了统一配置，
    # 直接依赖上层 formatter 即可（我们已在 nanoai/utils/__init__.py
    # 的 LOG_FORMAT 中加入了 filename:lineno）。
    current = dag_root_logger
    has_effective_handler = False
    while current is not None:
        if current.handlers:
            has_effective_handler = True
            break
        if not current.propagate:
            break
        current = current.parent

    if has_effective_handler:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(_DAG_LOG_FORMAT))
    dag_root_logger.addHandler(handler)


_setup_dag_logger()

from .operator_registry import (
    OperatorContext,
    OperatorResult,
    BaseOperator,
    OperatorRegistry,
    POISearchOperator,
    WebSearchOperator,
    NavigationOperator,
    CarControlOperator
)
from .safety_scanner import SafetyScanner
from .dag_executor import DAGExecutor
from .base_classes import DAGNode, DAGIR, OperatorType, ExecutionTrace, SafetyIssue

__all__ = [
    "DAGNode",
    "DAGIR",
    "OperatorType",
    "OperatorContext",
    "OperatorResult",
    "BaseOperator",
    "OperatorRegistry",
    "POISearchOperator",
    "WebSearchOperator",
    "NavigationOperator",
    "CarControlOperator",
    "SafetyIssue",
    "SafetyScanner",
    "ExecutionTrace",
    "DAGExecutor",
]
