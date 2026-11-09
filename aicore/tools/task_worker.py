from collections.abc import AsyncGenerator
from typing import Any

from anyio import fail_after, get_cancelled_exc_class
from pydantic import BaseModel

from aicore.runtime.task import TaskAStreamWorkerGeneral
from aicore.tools.protocol import TaskToolProtocolGeneral
from aicore.utils.misc import model_to_dict


def bind_task_tool_worker(
    tool: TaskToolProtocolGeneral,
    validated_arguments: BaseModel,
) -> TaskAStreamWorkerGeneral:
    """Bind validated arguments and execution policy to a tool's real worker."""
    factory = tool.stream_worker_factory(**model_to_dict(validated_arguments))

    async def run_task() -> AsyncGenerator[Any, None]:
        try:
            with fail_after(tool.timeout):
                async for item in factory():
                    yield item
        except get_cancelled_exc_class():
            # Cancellation is a runtime lifecycle outcome, not a tool error.
            raise
        except TimeoutError:
            raise TimeoutError(f"任务 {tool.name} 超时") from None
        except Exception as exc:
            if tool.on_error:
                raise RuntimeError(tool.on_error(exc)) from exc
            raise

    return run_task


__all__ = ["bind_task_tool_worker"]
