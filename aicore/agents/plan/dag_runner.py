from typing import Any, AsyncGenerator

from aicore.agents.plan.dag import DAG, Edge

type BareDag[NT] = DAG[NT, Edge[None]]


class DAGRunnerBase[NT]:
    def __init__(self):
        pass

    # 调用方需要确保 arguments 是符合对应 tool args_schema 要求的实例
    def run(self, dag: BareDag[NT]) -> AsyncGenerator[Any, None]:
        raise NotImplementedError()
        yield None  # 必须有yield，run才能被type checker识别为AsyncGenerator

    #@property
    #@abstractmethod
    #def tool_results(self) -> list[str]: ...
