"""LLM 工具包初始化模块

本模块提供全局日志配置和工具函数，包括：
1. 文件日志
2. 控制台日志
3. 统一的日志格式
4. 支持不同模块的日志记录器
5. 提示词驱动的模型输出结构化提炼
6. Pydantic 模型转换工具
7. 提示词生成工具
"""

# 导入新的日志模块
from .logger import (
    get_logger,
    setup_logger,
    default_logger,
    agent_logger,
    scenario_logger,
    profile_logger,
    llm_logger,
    memory_logger,
    worker_logger,
    api_logger,
    parser_logger
)
from .to_prompt import to_kv_prompt, KeySource, ValueSource, KVOrder
# 导入其他工具模块
from .to_pydantic import ToPydanticConverter

# 保留原有接口的兼容性
logger = default_logger

# 导出所有功能
__all__ = [
    # 日志相关功能
    "logger",
    "setup_logger",
    "get_logger",
    "default_logger",
    "agent_logger",
    "scenario_logger",
    "profile_logger",
    "llm_logger",
    "memory_logger",
    "worker_logger",
    "api_logger",
    "parser_logger",
    # 提示词驱动提炼器
    "PromptDrivenExtractor",
    "ExtractedContent",
    # Pydantic 转换工具
    "ToPydanticConverter",
    # 提示词生成工具
    "to_kv_prompt",
    "KeySource",
    "ValueSource",
    "KVOrder"
]