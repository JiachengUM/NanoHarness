"""Voice Test 全链路日志工具。

独立挂 StreamHandler（stdout），不落盘、不复用 nanoai.utils.logger，
避免 llm.log 无限增长撑爆磁盘。在线 log 服务从 stdout 采集即可。

每个模块用 `get_vt_logger(<name>)` 拿一个子 logger，名字形如 `vt.<name>`，
日志格式带文件名:行号 + 模块名，便于按模块 grep。
"""
from __future__ import annotations

import logging
import sys
import uuid

_LOG_FMT = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def get_vt_logger(name: str) -> logging.Logger:
    """获取 vt.<name> 子 logger。

    只挂 StreamHandler(stdout)，不落盘。
    通过 logger 名字 `vt.<name>` 区分模块，便于 grep。
    """
    logger = logging.getLogger(f"vt.{name}")
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter(_LOG_FMT, datefmt=_DATEFMT))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def new_session_id() -> str:
    """生成 6 位短 id，用于 WS session 全链路串联。"""
    return uuid.uuid4().hex[:6]


def new_run_id() -> str:
    """生成 4 位短 id，用于单个 case 执行的全链路串联（区分同一连接内多 case 多轮）。"""
    return uuid.uuid4().hex[:4]
