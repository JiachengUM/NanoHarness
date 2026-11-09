from typing import List, Optional, Type, Callable

from nanoai.model.qwen_llm import qwen
from pydantic import BaseModel, Field


class ExtractedContent(BaseModel):
    """默认的提炼结构化内容模型"""
    main_content: str = Field(..., description="主要内容")
    analysis_process: Optional[str] = Field(None, description="分析过程")
    summary_process: Optional[str] = Field(None, description="总结过程")
    thinking_process: Optional[str] = Field(None, description="思考过程")
    other_processes: Optional[List[str]] = Field(None, description="其他过程")


class PromptDrivenExtractor:
    """提示词驱动的模型输出结构化提炼器"""
    
    def __init__(self, model, enable_thinking, system_prompt: Optional[str] = None):
        """初始化提炼器
        
        Args:
            system_prompt: 自定义系统提示词，用于指导提炼过程
        """
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.model = model
        self.enable_thinking = enable_thinking
    
    def _default_system_prompt(self) -> str:
        """默认系统提示词"""
        return """你是一个专业的内容提炼助手，请对提供的文本进行结构化提炼。
        任务要求：
        1. 识别并提取文本中的主要内容
        2. 识别并提取文本中的分析过程、总结过程、思考过程
        3. 如有其他类型的过程，也请提取
        4. 请严格按照指定的JSON格式返回结果，不要添加任何额外的解释或说明
        """
    
    def _build_prompt(self, model_output: str, custom_prompt: Optional[str] = None, output_model_desc: Optional[str] = None) -> str:
        """构建提炼提示词
        
        Args:
            model_output: 模型的原始输出
            custom_prompt: 自定义提示词
            output_model_desc: 输出模型的描述，用于指导模型生成正确格式
            
        Returns:
            完整的提炼提示词
        """
        prompt_parts = []
        
        if custom_prompt:
            prompt_parts.append(custom_prompt)
        
        prompt_parts.append("请对以下模型输出进行结构化提炼：")
        prompt_parts.append(model_output)
        
        if output_model_desc:
            prompt_parts.append("输出格式：")
            prompt_parts.append(output_model_desc)
        
        return "\n\n".join(prompt_parts)
    
    def _generate_model_description(self, output_type: Type[BaseModel]) -> str:
        """生成模型描述，用于指导模型生成正确格式
        
        Args:
            output_type: 输出模型类型
            
        Returns:
            模型描述
        """
        # 获取模型字段信息
        fields = output_type.model_fields
        field_descs = []
        
        for field_name, field_info in fields.items():
            desc = field_name
            if field_info.description:
                desc = f"{field_name}: {field_info.description}"
            field_descs.append(desc)
        return "{\n" + ",\n".join(field_descs) + "\n}"
    
    def extract(self, model_output: str, custom_prompt: Optional[str] = None, 
                output_type: Type[BaseModel] = ExtractedContent) -> BaseModel:
        """提炼模型输出的结构化内容
        
        Args:
            model_output: 模型的原始输出
            custom_prompt: 自定义提示词，用于指导特定类型的提炼
            output_type: 输出模型类型，默认为ExtractedContent
            
        Returns:
            结构化提炼的内容
        """
        # 生成输出模型描述
        model_desc = self._generate_model_description(output_type)
        
        # 构建完整提示词
        prompt = self._build_prompt(model_output, custom_prompt, model_desc)
        
        try:
            # 调用模型进行结构化提炼
            result = qwen(
                prompt,
                messages_or_sys_prompt=self.system_prompt,
                model=self.model,
                enable_thinking=self.enable_thinking,
            )
            
            # 解析模型输出为结构化内容
            return output_type.model_validate_json(result.output)
        except Exception as e:
            # 简化示例，直接返回默认模型
            return output_type(
                main_content=model_output,
                analysis_process=None,
                summary_process=None,
                thinking_process=None,
                other_processes=None
            )
    
    def extract_with_custom_model(self, model_output: str, model_callable: Callable[[str], str],
                                 output_type: Type[BaseModel] = ExtractedContent) -> BaseModel:
        """使用自定义模型进行提炼
        
        Args:
            model_output: 模型的原始输出
            model_callable: 自定义模型调用函数，接收提示词返回结果
            output_type: 输出模型类型，默认为ExtractedContent
            
        Returns:
            结构化提炼的内容
        """
        # 生成输出模型描述
        model_desc = self._generate_model_description(output_type)
        
        # 构建完整提示词
        prompt = self._build_prompt(model_output, None, model_desc)
        
        try:
            result = model_callable(prompt)
            return output_type.model_validate_json(result)
        except Exception as e:
            # 简化示例，直接返回默认模型
            return output_type(
                main_content=model_output,
                analysis_process=None,
                summary_process=None,
                thinking_process=None,
                other_processes=None
            )

    # 便捷函数：直接提炼内容
    def extract_content(self, model_output: str, system_prompt: Optional[str] = None,
                       output_type: Type[BaseModel] = ExtractedContent) -> BaseModel:
        """便捷函数，直接提炼模型输出

        Args:
            model_output: 模型的原始输出
            system_prompt: 自定义系统提示词
            output_type: 输出模型类型，默认为ExtractedContent

        Returns:
            结构化提炼的内容
        """

        return self.extract(model_output, None, output_type)


    # 便捷函数：创建自定义提炼器
    def create_custom_extractor(self, output_type: Type[BaseModel], custom_prompt: Optional[str] = None) -> Callable[[str], BaseModel]:
        """创建自定义提炼器

        Args:
            output_type: 输出模型类型
            custom_prompt: 自定义提示词
            system_prompt: 自定义系统提示词

        Returns:
            提炼器函数
        """
        return self.create_custom_extractor(output_type, custom_prompt)
