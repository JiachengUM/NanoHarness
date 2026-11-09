import re
from contextvars import ContextVar
import logging

# 你的 trace_id_context
trace_id_context: ContextVar[str] = ContextVar("trace_id", default="")

class TraceIdFilter(logging.Filter):
    def filter(self, record):
        # 从上下文中获取 trace_id
        trace_id = trace_id_context.get()

        # 去掉前缀 "trace_id="，并去掉所有 "-"
        cleaned_trace_id = re.sub(r'^trace_id=|-', '', trace_id)

        # 设置到 record 上
        record.trace_id = cleaned_trace_id
        return True