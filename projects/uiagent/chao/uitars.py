"""
UI Agent 工具包 - 基于火山引擎方舟SDK的UI自动化助手
"""
import os
import base64
import json
from typing import Union, Dict, Any, List, Optional
from pathlib import Path

# 通过 pip install volcengine-python-sdk[ark] 安装方舟SDK
from volcenginesdkarkruntime import Ark

from prompt import UI_TARS_PROMPT
from prompt import UI_TARS_PROMPT_2
from prompt import UI_TARS_PROMPT_3


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
                 temperature: float = 0.0) -> Dict[str, Any]:
        """
        调用大语言模型进行推理
        
        Args:
            model: 模型名称
            messages: 消息列表
            temperature: 温度参数，控制输出随机性
            
        Returns:
            包含模型响应和元数据的字典
        """
        
        try:
            # 创建对话请求
            response = self.client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
                stream=False
            )
            
            
            return {
                "content": response.choices[0].message.content,
                "total_tokens": response.usage.total_tokens,
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "model": model,
                "success": True
            }
            
        except Exception as e:
            return {
                "content": None,
                "error": str(e),
                "success": False,
                "model": model
            }
    
    def uitars_call(self, image: Union[str, Path], query: str, prompt_type: str, language: str = "Chinese", model: str = "doubao-1-5-ui-tars-250428") -> Dict[str, Any]:
        """
        模型调用函数
        
        Args:
            image: 图片路径或Path对象
            query: 用户查询文本
            language: 回答语言
            model: 使用的模型名称
            
        Returns:
            包含分析结果的字典，格式如下：
            {
                "success": bool,           # 是否成功
                "content": str,            # 模型回答内容
                "error": str,              # 错误信息（如果有）
                "metadata": {              # 元数据
                    "total_tokens": int,   # 总token数
                    "model": str,          # 使用的模型
                    "image_format": str    # 图片格式
                }
            }
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
            else:
                system_prompt = UI_TARS_PROMPT_3.format(
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
            
            if result["success"]:
                return {
                    "success": True,
                    "content": result["content"],
                    "metadata": {
                        "total_tokens": result["total_tokens"],
                        "prompt_tokens": result["prompt_tokens"],
                        "completion_tokens": result["completion_tokens"],
                        "model": result["model"],
                        "image_format": image_format
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "content": None,
                    "metadata": {
                        "model": result["model"],
                        "image_format": image_format
                    }
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
                "metadata": {
                    "image_format": getattr(Path(image), 'suffix', 'unknown')[1:] if image else 'unknown'
                }
            }

    def uitars_call_with_prompt(self, image: Union[str, Path], query: str, prompt: str, language: str = "Chinese",
                    model: str = "doubao-1-5-ui-tars-250428") -> Dict[str, Any]:
        """
        模型调用函数-参数传入prompt

        Args:
            image: 图片路径或Path对象
            query: 用户查询文本
            language: 回答语言
            model: 使用的模型名称

        Returns:
            包含分析结果的字典，格式如下：
            {
                "success": bool,           # 是否成功
                "content": str,            # 模型回答内容
                "error": str,              # 错误信息（如果有）
                "metadata": {              # 元数据
                    "total_tokens": int,   # 总token数
                    "model": str,          # 使用的模型
                    "image_format": str    # 图片格式
                }
            }
        """
        try:
            # 编码图片
            base64_image = self.encode_image(image)
            image_path = Path(image)
            image_format = image_path.suffix[1:]  # 去掉点号

            # 构建系统提示
            if "instruction" in prompt and "language" in prompt:
                system_prompt = UI_TARS_PROMPT.format(
                    instruction=query,
                    language=language
                )
            else:
                system_prompt = prompt.format(
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

            if result["success"]:
                return {
                    "success": True,
                    "content": result["content"],
                    "metadata": {
                        "total_tokens": result["total_tokens"],
                        "prompt_tokens": result["prompt_tokens"],
                        "completion_tokens": result["completion_tokens"],
                        "model": result["model"],
                        "image_format": image_format
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "content": None,
                    "metadata": {
                        "model": result["model"],
                        "image_format": image_format
                    }
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
                "metadata": {
                    "image_format": getattr(Path(image), 'suffix', 'unknown')[1:] if image else 'unknown'
                }
            }

    def uitars_call_with_context(self, image: Union[str, Path], query: str, prompt: str, chat_id: str, language: str = "Chinese",
                    model: str = "doubao-1-5-ui-tars-250428") -> Dict[str, Any]:
        """
        模型调用函数-参数传入prompt and with context

        Args:
            image: 图片路径或Path对象
            query: 用户查询文本
            language: 回答语言
            model: 使用的模型名称

        Returns:
            包含分析结果的字典，格式如下：
            {
                "success": bool,           # 是否成功
                "content": str,            # 模型回答内容
                "error": str,              # 错误信息（如果有）
                "metadata": {              # 元数据
                    "total_tokens": int,   # 总token数
                    "model": str,          # 使用的模型
                    "image_format": str    # 图片格式
                }
            }
        """
        try:
            # 编码图片
            base64_image = self.encode_image(image)
            image_path = Path(image)
            image_format = image_path.suffix[1:]  # 去掉点号

            # 构建系统提示
            if "instruction" in prompt and "language" in prompt:
                system_prompt = UI_TARS_PROMPT.format(
                    instruction=query,
                    language=language
                )
            else:
                system_prompt = prompt.format(
                    instruction=query,
                )

            messages = []
            if not os.path.exists("context_cache_" + chat_id + ".json"):
                # 不存在
                messages.append(
                    {
                        "role": "user",
                        "content": system_prompt
                    }
                )
            else:
                with open("context_cache_" + chat_id + ".json", "r", encoding="utf-8") as file:
                    messages = json.load(file)
            # 构造消息
            messages.append(
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
            )

            # 调用LLM
            result = self.call_llm(model, messages)

            if result["success"]:
                # 模型结果保存至context_cache
                messages.append({
                    "role": "assistant",
                    "content": result["content"]
                })
                with open("context_cache_" + chat_id + ".json", "w", encoding="utf-8") as file:
                    json.dump(messages, file, ensure_ascii=False, indent=4)
                return {
                    "success": True,
                    "content": result["content"],
                    "metadata": {
                        "total_tokens": result["total_tokens"],
                        "prompt_tokens": result["prompt_tokens"],
                        "completion_tokens": result["completion_tokens"],
                        "model": result["model"],
                        "image_format": image_format
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result["error"],
                    "content": None,
                    "metadata": {
                        "model": result["model"],
                        "image_format": image_format
                    }
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
                "metadata": {
                    "image_format": getattr(Path(image), 'suffix', 'unknown')[1:] if image else 'unknown'
                }
            }

# 全局客户端实例
_client = None

def get_client() -> UITarsClient:
    """获取全局客户端实例"""
    global _client
    if _client is None:
        _client = UITarsClient()
    return _client

def uitars_call(image: Union[str, Path], query: str, prompt_type: str,
               language: str = "Chinese",
               model: str = "doubao-1-5-ui-tars-250428") -> Dict[str, Any]:
    """
    调用uitars模型
    
    Args:
        image: 图片路径
        query: 用户查询
        language: 回答语言
        model: 模型名称
        
    Returns:
        分析结果字典
    """
    client = get_client()
    return client.uitars_call(image, query, prompt_type, language, model)


def uitars_call_with_prompt(image: Union[str, Path], query: str, prompt: str,
                language: str = "Chinese",
                model: str = "doubao-1-5-ui-tars-250428") -> Dict[str, Any]:
    """
    调用uitars模型-参数中传入提示词

    Args:
        image: 图片路径
        query: 用户查询
        language: 回答语言
        model: 模型名称

    Returns:
        分析结果字典
    """
    client = get_client()
    return client.uitars_call_with_prompt(image, query, prompt, language, model)

def uitars_call_with_context(image: Union[str, Path], query: str, prompt: str, chat_id: str,
                language: str = "Chinese",
                model: str = "doubao-1-5-ui-tars-250428") -> Dict[str, Any]:
    """
    调用uitars模型-参数中传入提示词

    Args:
        image: 图片路径
        query: 用户查询
        language: 回答语言
        model: 模型名称

    Returns:
        分析结果字典
    """
    client = get_client()
    return client.uitars_call_with_context(image, query, prompt, chat_id, language, model)