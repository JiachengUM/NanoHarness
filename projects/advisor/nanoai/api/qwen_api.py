"""Qwen LLM API接口，使用FastAPI提供RESTful服务"""
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from nanoai.model.qwen_llm import qwen
from nanoai.model.qwen_llm import qwen_output, QwenRunResult
from pydantic import BaseModel, Field

from nanoai.utils import get_logger

logger = get_logger("api")
logger.debug("Starting Qwen API server...")

# 创建FastAPI应用
app = FastAPI(
    title="Qwen LLM Local API",
    description="提供Qwen模型的RESTful API接口，支持消息列表输入",
    version="1.0"
)

generate_kwargs = {
    "max_new_tokens": 10000,
    "do_sample": True,
    "temperature": 0.5,
    "top_p": 0.8,
    "top_k": 50,
    "repetition_penalty": 1.2
}

# 定义请求模型
class Message(BaseModel):
    """对话消息模型"""
    role: str = Field(..., description="角色，可以是user或system")
    content: str = Field(..., description="消息内容")

class QwenRequest(BaseModel):
    """Qwen API请求模型"""
    messages: List[Message] = Field(..., description="对话消息列表")
    enable_thinking: bool = Field(default=False, description="是否启用思考模式")
    model: Optional[str] = Field(default=None, description="模型名称，可以是远程API模型名称或本地Hugging Face模型ID")
    hf_token: Optional[str] = Field(default=None, description="Hugging Face访问令牌，用于访问私有模型")

# 定义响应模型
class QwenResponse(BaseModel):
    """Qwen API响应模型"""
    messages: List[Message] = Field(..., description="包含输入和生成输出的消息列表")
    success: bool = Field(..., description="请求是否成功")

@app.post("/v1/chat/completions", response_model=QwenResponse, summary="调用Qwen模型生成文本")
async def chat_completions(request: QwenRequest):
    """使用Qwen模型生成文本
    
    Args:
        request: 包含消息列表和其他参数的请求对象
    
    Returns:
        包含输入消息和生成文本的响应对象
    """
    try:
        # 提取消息内容
        messages = [msg.model_dump() for msg in request.messages]
        
        # 调用Qwen模型
        result: QwenRunResult = qwen(
                "",  # 输入为空，因为我们使用完整的消息列表
                messages,  # 直接传递完整的消息列表
                model=request.model,
                hf_token=request.hf_token,
                enable_thinking=request.enable_thinking,
                **generate_kwargs
            )
        # 将生成的文本添加到消息列表中
        response_messages = request.messages.copy()
        response_messages.append(Message(role="assistant", content=result.output))
        
        # 返回响应
        return QwenResponse(
            messages=response_messages,
            success=True
        )
    except Exception as e:
        import traceback
        error_message = f"模型调用失败: {str(e)}"
        logger.error(f"API Error: {error_message}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/health", summary="健康检查")
async def health_check():
    """检查API服务是否正常运行"""
    return {
        "status": "ok",
        "message": "Qwen LLM API is running"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
