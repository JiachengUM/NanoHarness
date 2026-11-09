"""LLM 工具包初始化模块

本模块提供全局日志配置，包括：
1. 文件日志
2. 控制台日志
3. 统一的日志格式
"""

import logging
import os
from typing import Final

# 日志配置常量
LOG_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
LOG_FILE: Final[str] = "llm.log"
LOG_LEVEL: Final[int] = logging.DEBUG


def setup_logger(
    name: str = "llm_global_logger",
    log_file: str | None = None,
    log_level: int = LOG_LEVEL,
    console_log_level: int = logging.INFO,
    log_format: str = LOG_FORMAT,
) -> logging.Logger:
    """设置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径，如果为 None 则不创建文件日志
        log_level: 文件日志级别
        console_log_level: 控制台日志级别，默认为 INFO
        log_format: 日志格式

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
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
logger = setup_logger(log_file=LOG_FILE)

# 导出日志记录器
__all__ = ["logger", "setup_logger"]
