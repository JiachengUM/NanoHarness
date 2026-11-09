from pydantic import BaseModel, Field

__all__ = [
    "IntentClsOutput",
    "IntentClsRunTrajectory",
]

class IntentClsOutput(BaseModel):
    '''
    意图分类输出。
    '''
    intent_type: str = Field(default="", title="意图类型", description="意图分类结果")

    reason: str | None = Field(default=None, title="原因", description="分类的原因")


class IntentClsRunTrajectory(BaseModel):
    '''
    意图分类运行过程的中间结果轨迹。帮助理解算法执行过程，归因分析，debug，优化等。
    TODO: 细节完全是具体算法自行定义的。
    '''
    sys_prompt: str | None = Field(default=None, title="系统提示", description="系统提示")

    user_prompt: str | None = Field(default=None, title="用户提示", description="用户提示")
    
    #api_result: VolcengineIntentResult = Field(..., description="火山接口原始结果")
    #prompt_result: str | None = Field(default=None, description="最终使用的分类结果（类别名称）")
    #llm_raw_result: str | None = Field(default=None, description="LLM原始分类结果（类别名称）")
    #vehicle_check: bool | None = Field(default=None, description="车控清晰度检查结果，True表示动作和实体都清晰，False表示不清晰")
    #rag_result: RagSearchResult | None = Field(default=None, description="RAG多意图检索结果")
