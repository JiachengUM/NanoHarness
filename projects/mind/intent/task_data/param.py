from pydantic import BaseModel, Field

from projects.mind.intent.alg.prompt import IntentClsPrompt

__all__ = [
    "LLMParam",
    "IntentClsParam",
]

class LLMParam(BaseModel):
    '''很难有跨算法任务的通用llm param定义，似乎只能每个任务各自定义'''

    model: str = Field(..., title="模型", description="LLM模型")
    
    temperature: float = Field(default=0.3, title="温度", description="温度参数")
    
    top_p: float = Field(default=0.7, title="Top P", description="Top P参数")


class IntentClsParam(BaseModel):
    '''
    意图分类算法参数。
    TODO: 细节完全取决于具体算法实现。
    '''

    prompt: IntentClsPrompt = Field(..., title="提示", description="意图分类提示")
    
    llm_param: LLMParam = Field(..., title="LLM参数", description="LLM参数")
