from pydantic import BaseModel, Field


class ResponseMetadata(BaseModel):
    total_tokens: int = Field(description="总token数")
    model: str = Field(description="使用的模型")
    image_format: str = Field(description="图片格式")
    
class ModelSuccessResponse(BaseModel):
    content: str = Field(description="模型回答内容")
    total_tokens: int = Field(description="总token数")
    prompt_tokens: int = Field(description="输入token数")
    completion_tokens: int = Field(description="输出token数")
    model: str = Field(description="使用的模型")
    success: bool = Field(description="是否成功")
    
class ModelErrorResponse(BaseModel):
    content: None = Field(None, description="模型回答内容，出错时为None")
    error: str = Field(description="错误信息")
    success: bool = Field(False, description="是否成功，出错时为False")
    model: str = Field(description="使用的模型")

class ModelResponse(BaseModel):
    success: bool = Field(description="是否成功")
    content: str | None = Field(default=None, description="模型回答内容")
    error: str | None = Field(default=None, description="错误信息（如果有）")
    metadata: ResponseMetadata | None = Field(default=None, description="元数据")

class UsageInfo(BaseModel):
    total_tokens: int = Field(description="总token数")
    prompt_tokens: int = Field(description="输入token数")
    completion_tokens: int = Field(description="输出token数")


