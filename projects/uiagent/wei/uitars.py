"""
UI Agent 工具包 - 基于火山引擎方舟SDK的UI自动化助手
"""
import os
import base64
from typing import Union, Dict, Any, List, Optional
from pathlib import Path

# 通过 pip install volcengine-python-sdk[ark] 安装方舟SDK
from volcenginesdkarkruntime import Ark

# 导入本地模块
from .prompt import UI_TARS_PROMPT, UI_TARS_PROMPT_2
from .pydantic_models import ModelResponse, ResponseMetadata, ModelErrorResponse, ModelSuccessResponse

class UITarsClient:
    """UI Agent 客户端类"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化UITars客户端
        
        Args:
            api_key: 火山引擎API密钥，如果不提供则从环境变量ARK_API_KEY读取
        """
        if api_key is None:
            api_key = os.getenv("ARK_API_KEY", "REDACTED")
        
        self.client = Ark(api_key=api_key)

    
    def encode_image(self, image_path: Union[str, Path]) -> str:
        """
        将图片文件编码为Base64字符串
        
        Args:
            image_path: 图片文件路径
            
        Returns:
            Base64编码的图片字符串
            
        Raises:
            FileNotFoundError: 当图片文件不存在时
            ValueError: 当文件不是有效图片格式时
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        
        # 检查文件扩展名
        valid_extensions = {'.png', '.jpg', '.jpeg', 'png'}
        if image_path.suffix.lower() not in valid_extensions:
            raise ValueError(f"不支持的图片格式: {image_path.suffix}")
        
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def call_llm(self, model: str, messages: List[Dict[str, Any]], 
                 temperature: float = 0.0) -> Union[ModelSuccessResponse, ModelErrorResponse]:
        """
        调用大语言模型进行推理
        
        Args:
            model: 模型名称
            messages: 消息列表
            temperature: 温度参数，控制输出随机性
            
        Returns:
            ModelSuccessResponse对象或ModelErrorResponse对象
        """
        
        try:
            # 创建对话请求
            response = self.client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
                stream=False
            )
            
            
            return ModelSuccessResponse(
                content=response.choices[0].message.content,
                total_tokens=response.usage.total_tokens,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                model=model,
                success=True
            )
            
        except Exception as e:
            return ModelErrorResponse(
                content=None,
                error=str(e),
                success=False,
                model=model
            )
    
    def uitars_call(self, image: Union[str, Path], query: str, custom_prompt: str, prompt_type: str = "official", language: str = "Chinese", model: str = "doubao-1-5-ui-tars-250428") -> ModelResponse:
        """
        模型调用函数
        
        Args:
            image: 图片路径或Path对象
            query: 用户查询文本
            language: 回答语言
            model: 使用的模型名称
            
        Returns:
            ModelResponse对象，包含分析结果
        """
        try:
            # 编码图片
            base64_image = self.encode_image(image)
            image_path = Path(image)
            image_format = image_path.suffix[1:]  # 去掉点号
            
            # 构建系统提示
            if prompt_type == "official":
                system_prompt = UI_TARS_PROMPT.format(
                    instruction=query,
                    language=language
                )
            elif prompt_type == "custom_prompt":
                system_prompt = custom_prompt.format(
                    instruction=query,
                )
            
            # 构造消息
            messages = [
                {
                    "role": "user",
                    "content": f"{system_prompt}"
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/{image_format};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
            
            # 调用LLM
            result = self.call_llm(model, messages)

            if isinstance(result, ModelSuccessResponse):
                return ModelResponse(
                    success=True,
                    content=result.content,
                    error=None,
                    metadata=ResponseMetadata(
                        total_tokens=result.total_tokens,
                        model=result.model,
                        image_format=image_format
                    )
                )
            else:
                print("++++++++++++++++++++++++++++++++++++")

                return ModelResponse(
                    success=False,
                    content=None,
                    error=result.error,
                    metadata=ResponseMetadata(
                        total_tokens=0,
                        model=result.model,
                        image_format=image_format
                    )
                )
                
        except FileNotFoundError as e:
            # 图片文件不存在时直接抛出异常
            raise e
        except Exception as e:
            return ModelResponse(
                success=False,
                content=None,
                error=str(e),
                metadata=ResponseMetadata(
                    total_tokens=0,
                    model=model,
                    image_format=getattr(Path(image), 'suffix', 'unknown')[1:] if image else 'unknown'
                )
            )

# 全局客户端实例
_client = None

def get_client() -> UITarsClient:
    """获取全局客户端实例"""
    global _client
    if _client is None:
        _client = UITarsClient()
    return _client

def uitars_call(image: Union[str, Path], query: str, custom_prompt: str, prompt_type: str,
               language: str = "Chinese",
               model: str = "doubao-1-5-ui-tars-250428") -> ModelResponse:
    """
    调用uitars模型
    
    Args:
        image: 图片路径
        query: 用户查询
        language: 回答语言
        model: 模型名称
        
    Returns:
        ModelResponse对象，包含分析结果
    """
    client = get_client()
    return client.uitars_call(image, query, custom_prompt, prompt_type, language, model)
