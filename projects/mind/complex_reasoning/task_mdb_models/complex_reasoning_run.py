from pydantic import Field, BaseModel
from typing import Optional
from aicore.agents.events import ReActEvent
from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase


class AgentTraceDBSchema(BaseModel, TaskDataDocBase):
    """
    智能体运行轨迹。
    """
    from_case_id: Optional[str] = Field(default=None, title="轨迹所属case_id", description="如果一条轨迹是自动化评测从case库生成的，那么用这个和case_id关联。")
    from_user_id: Optional[str] = Field(default=None, title="轨迹所属user_id", description="如果一条轨迹是人工对话后保存生成的，那么这个和user_id关联。")
    trace: list[list[dict[str, dict]]] = Field(default_factory=list, title="智能体运行的轨迹", description="包括但不限于用户侧发言，智能体回复，思考，工具调用，工具结果等等，基本等价于事件的列表。dict里的key是事件类型，value是事件内容的dict。")
    create_time: Optional[str] = Field(default=None, title="轨迹的创建时间", description="轨迹创建时间。")
    # agent_id: Optional[str] = Field(default=None, title="轨迹所属agent_id", description="生成轨迹的agent的id。")

    class Settings:
        name = "complex_reasoning_run"  # MongoDB 集合名称