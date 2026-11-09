"""项目日志模块，提供针对不同模块的日志记录功能"""
import logging
import os
from typing import Final

# 日志配置常量
LOG_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
LOG_FILE: Final[str] = "nanoai.log"
LOG_LEVEL: Final[int] = logging.DEBUG

# 模块名称映射
MODULE_NAMES = {
    "agent": "AGENT",
    "scenario": "SCENARIO",
    "profile": "PROFILE",
    "llm": "LLM",
    "memory": "MEMORY",
    "worker": "WORKER",
    "api": "API",
    "parser": "PARSER",
    "default": "DEFAULT"
}

def setup_logger(
    name: str = "nanoai",
    module_type: str = "default",
    log_file: str | None = None,
    log_level: int = LOG_LEVEL,
    console_log_level: int = logging.INFO,
    log_format: str = LOG_FORMAT,
) -> logging.Logger:
    """设置日志记录器

    Args:
        name: 日志记录器名称
        module_type: 模块类型，用于区分不同模块的日志
        log_file: 日志文件路径，如果为 None 则不创建文件日志
        log_level: 文件日志级别
        console_log_level: 控制台日志级别，默认为 INFO
        log_format: 日志格式

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 构建完整的logger名称，包含模块类型
    module_suffix = MODULE_NAMES.get(module_type, MODULE_NAMES["default"])
    logger_name = f"{name}.{module_suffix}"
    
    logger = logging.getLogger(logger_name)
    logger.setLevel(min(log_level, console_log_level))

    # 清除现有的处理器
    logger.handlers.clear()

    # 创建格式化器
    formatter = logging.Formatter(log_format)

    # 添加控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 如果指定了日志文件，添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# 创建默认的全局日志记录器
default_logger = setup_logger(log_file=LOG_FILE)

# 创建各模块的日志记录器
agent_logger = setup_logger(module_type="agent", log_file=LOG_FILE)
scenario_logger = setup_logger(module_type="scenario", log_file=LOG_FILE)
profile_logger = setup_logger(module_type="profile", log_file=LOG_FILE)
llm_logger = setup_logger(module_type="llm", log_file=LOG_FILE)
memory_logger = setup_logger(module_type="memory", log_file=LOG_FILE)
worker_logger = setup_logger(module_type="worker", log_file=LOG_FILE)
api_logger = setup_logger(module_type="api", log_file=LOG_FILE)
parser_logger = setup_logger(module_type="parser", log_file=LOG_FILE)

def get_logger(module_type: str = "default") -> logging.Logger:
    """获取指定模块的日志记录器

    Args:
        module_type: 模块类型

    Returns:
        logging.Logger: 对应的日志记录器
    """
    logger_map = {
        "agent": agent_logger,
        "scenario": scenario_logger,
        "profile": profile_logger,
        "llm": llm_logger,
        "memory": memory_logger,
        "worker": worker_logger,
        "api": api_logger,
        "parser": parser_logger,
        "default": default_logger
    }
    
    return logger_map.get(module_type, default_logger)

__all__ = [
    "get_logger",
    "setup_logger",
    "default_logger",
    "agent_logger",
    "scenario_logger",
    "profile_logger",
    "llm_logger",
    "memory_logger",
    "worker_logger",
    "api_logger",
    "parser_logger"
]