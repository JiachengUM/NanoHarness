import logging
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from projects.uiagent.server.configs.trace_id_filter import TraceIdFilter

# 全局变量控制日志级别
log_verbose = True

# 获取根 logger
logger = logging.getLogger()

class ConsoleLoggerFormatter(logging.Formatter):
    """控制台带颜色格式，显示模块名、行号、服务名"""
    COLOR_CODES = {
        "DEBUG": "\033[36m",  # 青色
        "INFO": "\033[32m",  # 绿色
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 红色
        "CRITICAL": "\033[1;31m",  # 粗体红色
        "RESET": "\033[0m",  # 重置颜色
    }

    def __init__(self, service_name=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service_name = service_name or "unknown-service"

    def format(self, record):
        # 确保 filter 被调用
        super().format(record)

        color_code = self.COLOR_CODES.get(record.levelname, "")
        reset_code = self.COLOR_CODES["RESET"]
        log_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        # 如果有异常信息，追加换行 + 异常堆栈
        log_message = record.getMessage()
        if record.exc_info:
            log_message += "\n" + self.formatException(record.exc_info)
        elif record.exc_text:
            log_message += "\n" + record.exc_text

        # 从日志记录中获取 trace_id 字段（由 TraceIdFilter 注入），若没有则显示 traceId
        trace_id = getattr(record, "trace_id", "traceId")

        return f"{color_code}[{log_time}] [{record.levelname}] [{record.name}] [{record.lineno}] [{trace_id}]: {log_message}{reset_code}"

def init_logging(filename: str):
    # 清除已有 handlers，避免重复添加
    if logger.handlers:
        logger.handlers.clear()

    # 设置 logger 的基础级别
    logger.setLevel(logging.DEBUG if log_verbose else logging.INFO)

    # 日志文件路径处理（更安全）
    log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "/var/logs/volc-llm-nanoai-agent"))
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, filename)

    # 创建 TraceIdFilter 实例
    trace_id_filter = TraceIdFilter()

    # 先添加 filter 到 root logger
    logger.addFilter(trace_id_filter)

    # 文件日志处理器（DEBUG 级别）
    file_handler = TimedRotatingFileHandler(
        filename=log_file_path,
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        fmt='[%(asctime)s.%(msecs)03d] [%(levelname)s] [volc-llm-customized-agent] [%(name)s] [%(lineno)d] [%(trace_id)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)

    # 同时添加 filter 到 handler
    file_handler.addFilter(trace_id_filter)

    logger.addHandler(file_handler)

    # 控制台日志处理器（INFO 级别）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleLoggerFormatter(service_name='volc-llm-nanoai-agent'))

    # 同时添加 filter 到 handler
    console_handler.addFilter(trace_id_filter)

    logger.addHandler(console_handler)

    logger.info("Logging 初始化完成")
    print("当前 logger 的 filters：", logger.filters)