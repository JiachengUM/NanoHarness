import uuid

from beanie import PydanticObjectId
from typing import Any, List, Optional
import asyncio

from jinja2 import Template

from aicore.agents.experiments.base import AgentBase, RunResult
from aicore.agents.experiments.user_profile import UserProfile
from aicore.utils.nl_repr.core import nl_repr_safe
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import Judge
from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.enums.task import (
    AgentType,
    TaskRunItemStatus,
    TaskRunStatus,
)
from projects.mind.test_backend.core.errors import raise_app_error, ErrorCode
from projects.mind.test_backend.mdb_models.task import (
    Evaluation,
    TaskDoc,
    TaskRunDoc,
    TaskRunItem,
    TaskRunItemDoc,
)
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.test_backend.repositories import mdb_service
from projects.mind.test_backend.service.agent.react import get_tool_map
from projects.sgm_prod.core import AgentDoStreamRequest, SGMAgent, StreamChunk

SKILL_PROFILE_TYPE = "skills"


# 复杂推理数据集处理器实现
class DatasetProcessor:
    """复杂推理数据集处理器"""

    async def get_dataset_items(
        self, dataset_id: PydanticObjectId
    ) -> List[ComplexReasoningCaseDoc]:
        """获取复杂推理数据集项列表"""
        return await mdb_service.get_list(
            ComplexReasoningCaseDoc, query={"dataset_id": dataset_id}, sort="_id"
        )

    def extract_query(self, item: ComplexReasoningCaseDoc) -> Optional[str]:
        """从复杂推理数据集项中提取查询内容"""
        try:
            return item.user_query_lists[0][0].content
        except Exception:
            return None

    def get_user_profile(
        self, item: ComplexReasoningCaseDoc
    ) -> Optional[str | UserProfile]:
        """获取用户画像"""
        return (
            item.context_config.get("user_profile", None)
            if item.context_config
            else None
        )


# 评价器实现
class Evaluator:
    """复杂推理评价器"""

    def __init__(self, agent_type: str = "BaseAgent"):
        self.agent_type = agent_type

    async def evaluate(
        self,
        item: ComplexReasoningCaseDoc,
        query: str,
        result: RunResult | List[StreamChunk],
    ) -> Evaluation:
        """评价任务执行结果"""
        judge = Judge()

        history_for_judge = self.get_history_for_judge(query, result)
        is_pass, reason = await judge.ajudge(item, history_for_judge)

        return Evaluation(
            is_pass=is_pass,
            comment=reason,
        )

    def get_history_for_judge(
        self, query: str, result: RunResult | List[StreamChunk]
    ) -> str:
        """构建供评价器使用的会话记录内容"""
        if self.agent_type == "BaseAgent":
            return self._get_base_agent_history_for_judge(query, result)
        elif self.agent_type == AgentType.SGM_AGENT:
            return self._get_sgm_agent_history_for_judge(query, result)

    def _get_base_agent_history_for_judge(self, query: str, result: RunResult) -> str:
        history: list[dict[str, Any]] = [{"role": "user", "content": query}]

        for event in result.events:
            if event.type == "react.tool_call.start":
                history.append({
                    "role": "function_call",
                    "name": event.name,
                    "arguments": event.arguments,
                })

            if event.type == "react.tool_results.done":
                for tool_result in event.tool_results:
                    history.append({
                        "role": "function_call_output",
                        "content": tool_result,
                    })
            if event.type == "react.text.done":
                history.append(
                    {
                        "role": "assistant",
                        "content": event.text,
                    }
                )

        return nl_repr_safe(history).strip()
        # return nl_repr_safe(result.response.message_history)

    def _get_sgm_agent_history_for_judge(
        self, query: str, result: List[StreamChunk]
    ) -> str:
        history: list[dict[str, str]] = [{"role": "user", "content": query}]

        content = ""
        for chunk in result:
            if chunk.content:
                content += chunk.content
            if chunk.observation:
                history.append(
                    {
                        "role": chunk.plugin_name or "observation",
                        "content": chunk.observation,
                    }
                )
        if content:
            history.append(
                {
                    "role": "assistant",
                    "content": content,
                }
            )

        return nl_repr_safe(history).strip()


class TaskRunner:
    """任务执行器，负责执行测试任务"""

    def __init__(
        self,
        dataset_processor: DatasetProcessor,
        evaluator: Optional[Evaluator] = None,
        concurrency: int = 1,
        agent_type: str = "BaseAgent",
    ):
        """初始化任务执行器"""
        self.dataset_processor = dataset_processor
        self.evaluator = evaluator
        self.agent_type = agent_type
        self.concurrency = max(1, concurrency)  # 确保并发数至少为1
        self.chat_id = f"sgm_test_{uuid.uuid4().hex[:8]}"

    async def run_task(self, task: TaskDoc) -> TaskRunDoc:
        """执行完整任务"""

        print(f"开始执行任务: {task.id}, 任务名称: {task.name}")

        # 1. 创建任务运行记录
        task_run = await mdb_service.create(
            model=TaskRunDoc,
            data=TaskRunDoc(
                task_id=task.id,
                status=TaskRunStatus.RUNNING,
            ),
        )

        # 2. 获取数据集项
        print(f"获取数据集项，数据集ID: {task.dataset_id}")
        dataset_items = await self.dataset_processor.get_dataset_items(task.dataset_id)
        print(f"获取到 {len(dataset_items)} 个数据集项")

        # 3. 并行执行所有任务项，控制并发数量
        try:
            semaphore = asyncio.Semaphore(self.concurrency)

            # 定义一个异步函数来执行单个任务项，并使用信号量控制并发
            async def run_with_semaphore(item):
                async with semaphore:
                    return await self._run_single_item(
                        task.model_copy(deep=True), task_run, item
                    )

            # 创建所有任务
            tasks = [run_with_semaphore(item) for item in dataset_items]

            # 等待所有任务完成
            await asyncio.gather(*tasks)

            # 更新任务状态
            task_run.status = TaskRunStatus.COMPLETED
            return await self.update_task_run(task_run)

        except Exception as e:
            # 处理执行过程中的异常
            print(f"任务 {task.name} 执行失败: {e}")
            task_run.status = TaskRunStatus.FAILED
            task_run.metadata = task_run.metadata or {}
            task_run.metadata["error"] = str(e)

            return await self.update_task_run(task_run)

    async def _run_single_item(
        self, task: TaskDoc, task_run: TaskRunDoc, item: ComplexReasoningCaseDoc
    ) -> TaskRunItemDoc:
        """执行单个任务项"""
        # 1. 创建任务项运行记录
        run_item = await mdb_service.create(
            model=TaskRunItemDoc,
            data=TaskRunItem(
                task_run_id=task_run.id,
                dataset_item_id=item.id,
                status=TaskRunItemStatus.RUNNING,
            ),
        )
        print(f"开始执行任务项: {run_item.id}, 数据集项[{item.id}]: {item.case_id}")

        # 2. 提取查询内容
        query = self.dataset_processor.extract_query(item)
        # TODO: 如果query不为空，则不需要if not query. 如果没有query,则直接raise
        if not query:
            run_item.status = TaskRunItemStatus.SKIPPED
            run_item.metadata = run_item.metadata or {}
            run_item.metadata["error"] = "没有有效的query内容"
            return await self.update_task_run_item(run_item)

        # 3. 初始化Agent
        try:
            agent = self.build_agent(task, item)
        except Exception as e:
            run_item.status = TaskRunItemStatus.FAILED
            run_item.metadata = run_item.metadata or {}
            run_item.metadata["error"] = f"Agent初始化失败: {e}"
            return await self.update_task_run_item(run_item)

        # 4. 执行任务项
        try:
            result = await self.agent_run(agent, item)
            run_item.status = TaskRunItemStatus.COMPLETED
            run_item.answer = result

            # 5. 执行评价（如果有评价器）
            if self.evaluator:
                run_item.status = TaskRunItemStatus.EVALUATING
                await self.update_task_run_item(run_item)

                try:
                    run_item.llm_evaluation = await self.evaluator.evaluate(
                        item, query, result
                    )
                    run_item.status = TaskRunItemStatus.COMPLETED
                except Exception as e:
                    run_item.status = TaskRunItemStatus.FAILED
                    run_item.metadata = run_item.metadata or {}
                    run_item.metadata["error"] = f"评价器执行异常: {e}"
        except Exception as e:
            run_item.status = TaskRunItemStatus.FAILED
            run_item.metadata = run_item.metadata or {}
            run_item.metadata["error"] = f"Agent执行异常: {e}"

        return await self.update_task_run_item(run_item)

    async def agent_run(
        self, agent: AgentBase, item: ComplexReasoningCaseDoc
    ) -> RunResult | List[StreamChunk]:
        query = self.dataset_processor.extract_query(item)

        if self.agent_type == AgentType.BASE_AGENT:
            return await agent.astream_run(query, event_listeners=[])
        if self.agent_type == AgentType.SGM_AGENT:
            req = AgentDoStreamRequest(
                chat_id=self.chat_id,
                question_id=self.chat_id,
                query=query,
                intent_type="复杂推理",
                car_info={},
            )
            result = []
            full_content = ""
            async for chunk in agent.astream_chunks(req):
                result.append(chunk)
                full_content += chunk.content

            result.append(StreamChunk(debug_info={"full_content": full_content}))

            return result

    def build_agent(
        self, task: TaskDoc, item: ComplexReasoningCaseDoc
    ) -> AgentBase | SGMAgent:
        if self.agent_type == AgentType.BASE_AGENT:
            return self._build_base_agent(task, item)
        elif self.agent_type == AgentType.SGM_AGENT:
            return self._build_sgm_agent(task, item)

    def _build_base_agent(
        self, task: TaskDoc, item: ComplexReasoningCaseDoc
    ) -> AgentBase:
        """根据任务配置构建Agent实例"""
        tool_name = (
            item.context_config.get("tool_name") if item.context_config else None
        )
        if tool_name:
            task.config.tools_names = tool_name

        collection_name = (
            item.context_config.get("collection_name") if item.context_config else None
        )
        profile_types = (
            item.context_config.get("profile_types") if item.context_config else None
        )
        system_prompt_profile_types = (
            item.context_config.get("system_prompt_profile_types")
            if item.context_config
            else None
        )
        search_profile_types = (
            item.context_config.get("search_profile_types")
            if item.context_config
            else None
        )
        resolved_system_prompt_profile_types = (
            system_prompt_profile_types
            if system_prompt_profile_types is not None
            else profile_types
        )
        resolved_search_profile_types = (
            search_profile_types
            if search_profile_types is not None
            else [SKILL_PROFILE_TYPE]
        )
        profile_limit = (
            item.context_config.get("profile_limit") if item.context_config else None
        )
        user_id = item.context_config.get("user_id") if item.context_config else None
        assistant_id = (
            item.context_config.get("assistant_id") if item.context_config else None
        )

        try:
            if collection_name:
                task.config.memory.consumer.config.collection_id.collection_name = (
                    collection_name
                )
                task.config.memory.producer.config.collection_id.collection_name = (
                    collection_name
                )
            if resolved_system_prompt_profile_types is not None:
                task.config.memory.consumer.config.system_prompt_profile_types = resolved_system_prompt_profile_types
            if resolved_search_profile_types is not None:
                task.config.memory.consumer.config.search_profile_types = resolved_search_profile_types
            if profile_limit:
                task.config.memory.consumer.config.profile_limit = profile_limit
            if user_id:
                task.config.memory.user_info.user_id = user_id
            if assistant_id:
                task.config.memory.user_info.assistant_id = assistant_id

        except Exception as e:
            print(f"更新memory collection_name失败: {e}")

        if isinstance(task.config.system_prompt, str):
            if not item.context_config.get("user_profile") and task.config.user_profile:
                item.context_config["user_profile"] = nl_repr_safe(
                    task.config.user_profile
                )
            template = Template(task.config.system_prompt)
            system_prompt = template.render(**item.context_config)
            task.config.system_prompt = system_prompt
            print(f"system_prompt: {task.config.system_prompt}")

        tools = {
            name: get_tool_map()[name]
            for name in task.config.tools_names
            if name in get_tool_map()
        }

        task.config.tools_names = [
            name for name in task.config.tools_names if name in tools
        ]

        return AgentBase.create(task.config, tool_registry=tools)

    def _build_sgm_agent(
        self, task: TaskDoc, item: ComplexReasoningCaseDoc
    ) -> SGMAgent:
        # TODO: 把这里的逻辑移到外部，这里只接受task.config参数
        if not item.context_config.get("user_profile") and task.config.user_profile:
            item.context_config["user_profile"] = nl_repr_safe(
                task.config.user_profile
            )
        template = Template(task.config.system_prompt)
        system_prompt = template.render(**item.context_config)
        # task.config.system_prompt = system_prompt
        print(f"system_prompt: {system_prompt}")

        return SGMAgent.build(
            chat_id=self.chat_id, system_prompt=system_prompt
        )

    async def update_task_run(self, task_run: TaskRunDoc):
        """更新任务运行记录"""
        return await mdb_service.update(
            model=TaskRunDoc, doc_id=task_run.id, data=task_run
        )

    async def update_task_run_item(self, run_item: TaskRunItemDoc):
        """更新任务项运行记录"""
        return await mdb_service.update(
            model=TaskRunItemDoc, doc_id=run_item.id, data=run_item
        )


def create_task_runner(
    dataset_processor: Optional[DatasetProcessor] = None,
    evaluator: Optional[Evaluator] = None,
    concurrency: int = 1,
    agent_type: AgentType = AgentType.BASE_AGENT,
) -> TaskRunner:
    """创建任务执行器实例"""
    if not dataset_processor:
        dataset_processor = DatasetProcessor()

    if not evaluator:
        evaluator = Evaluator(agent_type=agent_type)

    return TaskRunner(dataset_processor, evaluator, concurrency, agent_type=agent_type)


async def run_task(task_id: PydanticObjectId):
    """执行任务的对外接口"""
    # 1. 获取待执行任务
    task = await mdb_service.get_by_id(TaskDoc, task_id)
    if not task:
        return raise_app_error(ErrorCode.NOT_FOUND, 404, f"未找到任务: {task_id}")

    # 2. 创建任务执行器，执行任务(后台运行)
    concurrency = (
        task.metadata.get("concurrency", 2) if task.metadata else 2
    )  # 从元信息中获取并发数，默认2
    agent_type = (
        task.metadata.get("agent_type", AgentType.BASE_AGENT)
        if task.metadata
        else AgentType.BASE_AGENT
    )
    task_runner = create_task_runner(concurrency=concurrency, agent_type=agent_type)
    asyncio.create_task(task_runner.run_task(task))

    return


async def test_run_task():
    await init_db()
    # task_id = PydanticObjectId("69dde53adb7cc2bfe54e2268") # sgm agent
    task_id = PydanticObjectId("69dde558acd80b0c331e8796") # base agent

    task = await mdb_service.get_by_id(TaskDoc, task_id)
    if not task:
        return print(f"未找到任务: {task_id}")
    concurrency = task.metadata.get("concurrency", 2) if task.metadata else 2
    task_runner = create_task_runner(concurrency=concurrency)
    await task_runner.run_task(task)


if __name__ == "__main__":
    asyncio.run(test_run_task())

# python -m projects.mind.test_backend.service.task.task_run_service
