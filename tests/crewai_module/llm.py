from crewai.llm import LLM
import os
import dotenv
dotenv.load_dotenv()

# 为crewai创建Ark LLM配置
def llm_client(**kwargs) -> LLM:
    """
    创建用于crewai的Ark LLM配置
    
    Args:
        **kwargs: 模型配置参数
    Returns:
        用于crewai的LLM对象
    """
    
    # 创建并返回LLM对象
    return LLM(
        model=os.getenv("MODEL"),
        provider="openai",  # 使用openai兼容模式
        api_key=os.getenv("ARK_API_KEY"),
        base_url=os.getenv("BASE_URL"),
        temperature=kwargs.get("temperature", 0.7),
        max_tokens=kwargs.get("max_tokens", 1000)
    )
