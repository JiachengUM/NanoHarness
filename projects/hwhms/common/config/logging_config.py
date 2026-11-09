import logging
import os
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# 创建Logger对象
logger = logging.getLogger()

log_verbose = True

class CustomFormatter(logging.Formatter):
    """自定义日志格式化器，包含时间戳（带微秒）、线程名、请求唯一ID等信息"""

    def format(self, record):
        # 1. 处理时间格式（毫秒用点分隔）
        dt = datetime.fromtimestamp(record.created)
        asctime = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 用点分隔，截断后3位

        # 2. 构造日志消息（调整格式与示例一致）
        log_message = (
            f'[{asctime}] [{record.levelname}] [{"nanoai-hwhms"}] '
            f'[{record.module}] [{record.lineno}] [{uuid.uuid4()}]: {record.getMessage()}'
        )

        return log_message


def init_logging(filename: str):
    # 清除之前的处理器
    logger.handlers.clear()

    if not logger.handlers:
        # 设置日志级别
        logger.setLevel(logging.ERROR if not log_verbose else logging.INFO)

        # 文件处理器
        # 确保日志文件存在
        log_file = os.path.abspath('../' + filename)
        if not os.path.exists(log_file):
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, 'w'):
                pass

        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        formatter = CustomFormatter()
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_formatter = CustomFormatter()
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
