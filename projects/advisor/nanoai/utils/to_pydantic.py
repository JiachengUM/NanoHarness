import json
from typing import Dict, List, Any, Type, Optional

import requests
from cabin_advisor.parser_utils.parser import LenientJSONParser
from pydantic import BaseModel, Field, create_model


class ToPydanticConverter:
    """将JSON数据结构转换为Pydantic模型的转换器"""
    
    def __init__(self, model, enable_thinking, fastapi_url: Optional[str] = None):
        """初始化转换器
        
        Args:
            fastapi_url: 可选的FastAPI服务URL，用于调用外部服务生成description和example
        """
        self.enable_thinking = enable_thinking
        self.model_id = model
        self.fastapi_url = fastapi_url
        self.parser = LenientJSONParser(model=model, enable_thinking=enable_thinking)

    def convert(self, data: Any, model_name: str = "GeneratedModel") -> Type[BaseModel]:
        """将数据转换为Pydantic模型
        
        Args:
            data: 输入数据，可以是dict、list、str等
            model_name: 生成的主模型名称
            
        Returns:
            生成的Pydantic模型类
        """
        # 处理不同类型的数据
        if isinstance(data, dict):
            return self._convert_dict(data, model_name)
        elif isinstance(data, list):
            # 如果是列表，创建一个包含该列表的模型
            return self._convert_list(data, model_name)
        else:
            # 基本类型，创建一个包含该类型的模型
            return self._create_scalar_model(data, model_name)
    
    def _convert_dict(self, data: Dict[str, Any], model_name: str) -> Type[BaseModel]:
        """将字典转换为Pydantic模型
        
        Args:
            data: 输入字典
            model_name: 生成的模型名称
            
        Returns:
            生成的Pydantic模型类
        """
        fields = {}
        
        for key, value in data.items():
            # 生成字段描述、示例和英文别名
            description, example, alias = self._generate_field_info(key, value)
            
            # 获取字段类型
            field_type = self._get_field_type(value, f"{model_name}{key.title()}")
            
            # 添加字段到模型，包含alias
            fields[key] = (field_type, Field(default=value, description=description, example=example, alias=alias))
        
        return self._create_model(model_name, fields)
    
    def _convert_list(self, data: List[Any], model_name: str) -> Type[BaseModel]:
        """将列表转换为Pydantic模型
        
        Args:
            data: 输入列表
            model_name: 生成的模型名称
            
        Returns:
            生成的Pydantic模型类
        """
        if not data:
            # 空列表，创建一个包含List[str]的模型
            return create_model(
                model_name,
                items=(List[str], Field(default=[], description="空列表", example=[]))
            )
        
        # 检查列表元素类型
        first_item = data[0]
        if isinstance(first_item, str):
            # 列表元素是字符串，生成合适的字段名称和描述
            field_name = "items"
            description, example, alias = self._generate_field_info("items", data)
            
            return create_model(
                model_name,
                **{field_name: (List[str], Field(default=data, description=description, example=example, alias=alias))}
            )
        elif isinstance(first_item, dict):
            # 列表元素是字典，生成嵌套模型
            item_model = self._convert_dict(first_item, f"{model_name}Item")
            field_name = "items"
            description, example, alias = self._generate_field_info("items", data)
            
            return create_model(
                model_name,
                **{field_name: (List[item_model], Field(default=data, description=description, example=example, alias=alias))}
            )
        else:
            # 其他类型，生成相应的列表模型
            field_type = type(first_item)
            field_name = "items"
            description, example, alias = self._generate_field_info("items", data)
            
            return create_model(
                model_name,
                **{field_name: (List[field_type], Field(default=data, description=description, example=example, alias=alias))}
            )
    
    def _create_scalar_model(self, data: Any, model_name: str) -> Type[BaseModel]:
        """将基本类型转换为Pydantic模型
        
        Args:
            data: 输入数据
            model_name: 生成的模型名称
            
        Returns:
            生成的Pydantic模型类
        """
        field_type = type(data)
        description, example, alias = self._generate_field_info("value", data)
        
        return create_model(
            model_name,
            value=(field_type, Field(default=data, description=description, example=example, alias=alias))
        )
    
    def _get_field_type(self, value: Any, model_name: str) -> Type:
        """获取字段的数据类型
        
        Args:
            value: 字段值
            model_name: 生成的模型名称
            
        Returns:
            字段的数据类型
        """
        if isinstance(value, dict):
            # 嵌套字典，递归转换为模型
            return self._convert_dict(value, model_name)
        elif isinstance(value, list):
            if not value:
                # 空列表，默认为List[str]
                return List[str]
            else:
                # 非空列表，获取第一个元素的类型
                item_type = self._get_field_type(value[0], f"{model_name}Item")
                return List[item_type]
        elif isinstance(value, bool):
            return bool
        elif isinstance(value, int):
            return int
        elif isinstance(value, float):
            return float
        else:
            return str
    
    def _generate_field_info(self, key: str, value: Any) -> tuple[str, Any, str]:
        """生成字段的描述、示例和英文别名
        
        Args:
            key: 字段名
            value: 字段值
            
        Returns:
            (description, example, alias) 元组
        """
        if self._is_description(value):
            # 值是键的description，生成example
            description = value
            example = self._generate_example_from_description(key, value)
        else:
            # 值是具体用例，生成description
            description = self._generate_description_from_example(key, value)
            example = value
        
        # 生成英文别名
        alias = self._generate_alias(key)
        
        return description, example, alias
    
    def _is_description(self, value: Any) -> bool:
        """判断值是否为键的描述
        
        Args:
            value: 字段值
            
        Returns:
            True if value is a description, False otherwise
        """
        # 简单判断：如果是字符串，长度较长，且不是JSON或列表格式，则认为是描述
        if isinstance(value, str):
            return len(value) > 20 and not value.startswith("{") and not value.startswith("[")
        return False
    
    def _generate_example_from_description(self, key: str, description: str) -> Any:
        """根据描述生成示例值
        
        Args:
            key: 字段名
            description: 字段描述
            
        Returns:
            生成的示例值
        """
        if not self.fastapi_url:
            # 没有API URL，返回默认值
            return f"示例{key}"
        
        try:
            # 构建请求数据
            messages = [
                {
                    "role": "system",
                    "content": "你是一个数据结构分析专家，需要根据字段描述生成合适的示例值。"
                },
                {
                    "role": "user",
                    "content": f"请为以下字段生成一个示例值：\n字段名：{key}\n字段描述：{description}\n\n请只返回示例值，不要包含其他内容。"
                }
            ]
            
            # 调用qwen_api.py的v1/chat/completions接口
            response = requests.post(self.fastapi_url, json={"model":self.model_id, "messages": messages, "enable_thinking": self.enable_thinking})
            
            if response.status_code == 200:
                result = response.json()
                content = result["messages"][-1]["content"].strip()
                # 尝试解析为JSON，如果失败则返回字符串
                try:
                    return json.loads(content)
                except:
                    return content
            else:
                return f"示例{key}"
        except Exception as e:
            print(f"调用API生成示例失败: {e}")
            return f"示例{key}"
    
    def _generate_description_from_example(self, key: str, example: Any) -> str:
        """根据示例值生成描述
        
        Args:
            key: 字段名
            example: 字段示例值
            
        Returns:
            生成的描述
        """
        if not self.fastapi_url:
            # 没有API URL，返回字段名作为描述
            return key
        
        try:
            # 构建请求数据
            messages = [
                {
                    "role": "system",
                    "content": "你是一个数据结构分析专家，需要根据字段示例值生成合适的描述。"
                },
                {
                    "role": "user",
                    "content": f"请为以下字段生成一个详细描述：\n字段名：{key}\n字段示例值：{example}\n\n请只返回简洁精准的描述文本，不要包含其他内容。"
                }
            ]
            
            # 调用qwen_api.py的v1/chat/completions接口
            response = requests.post(self.fastapi_url, json={"model":self.model_id, "messages": messages, "enable_thinking": self.enable_thinking})
            
            if response.status_code == 200:
                result = response.json()
                return result["messages"][-1]["content"].strip()
            else:
                return key
        except Exception as e:
            print(f"调用API生成描述失败: {e}")
            return key
    
    def _generate_alias(self, key: str) -> str:
        """生成字段的英文别名
        
        Args:
            key: 字段名
            
        Returns:
            生成的英文别名
        """
        if not self.fastapi_url:
            # 没有API URL，返回驼峰命名的键作为别名
            # 将下划线命名转换为驼峰命名
            parts = key.split('_')
            return parts[0] + ''.join(part.title() for part in parts[1:])
        
        try:
            # 构建请求数据
            messages = [
                {
                    "role": "system",
                    "content": "你是一个数据结构分析专家，需要将中文字段名翻译成合适的英文别名。"
                },
                {
                    "role": "user",
                    "content": f"请将以下中文字段名翻译成合适的英文别名，使用驼峰命名法（首字母小写，后续单词首字母大写），不要包含其他内容：\n字段名：{key}"
                }
            ]
            
            # 调用qwen_api.py的v1/chat/completions接口
            response = requests.post(self.fastapi_url, json={"model":self.model_id, "messages": messages, "enable_thinking": self.enable_thinking})
            
            if response.status_code == 200:
                result = response.json()
                return result["messages"][-1]["content"].strip()
            else:
                # 服务调用失败，返回驼峰命名的键作为别名
                parts = key.split('_')
                return parts[0] + ''.join(part.title() for part in parts[1:])
        except Exception as e:
            print(f"调用API生成英文别名失败: {e}")
            # 发生异常，返回驼峰命名的键作为别名
            parts = key.split('_')
            return parts[0] + ''.join(part.title() for part in parts[1:])
    
    def _create_model(self, model_name: str, fields: Dict[str, tuple]) -> Type[BaseModel]:
        """创建Pydantic模型类
        
        Args:
            model_name: 模型名称
            fields: 模型字段字典
            
        Returns:
            生成的Pydantic模型类
        """
        # 使用pydantic的create_model函数创建模型
        return create_model(model_name, **fields)
    
    def _generate_pydantic_from_json(self, json_schema: Dict[str, Any], model_name: str = "GeneratedModel") -> str:
        """将Pydantic模型的model_json_schema生成的JSON转换为结构化提示词
        
        Args:
            json_schema: Pydantic模型的model_json_schema生成的JSON
            model_name: 模型名称
            
        Returns:
            结构化的提示词字符串
        """
        prompt_parts = []
        
        def _process_field(field_name: str, field_schema: Dict[str, Any], indent: int = 0) -> str:
            """处理单个字段，带有缩进"""
            field_parts = []
            prefix = "  " * indent
            
            # 获取字段基本信息
            field_type = field_schema.get("type", "any")
            field_description = field_schema.get("description", field_name)
            
            # 处理引用类型
            if "$ref" in field_schema:
                ref_path = field_schema["$ref"]
                if "#/$defs/" in ref_path:
                    ref_model = ref_path.split("#/$defs/")[-1]
                    field_parts.append(f"{prefix}- **{field_name}** ({ref_model}): {field_description}")
                return "\n".join(field_parts)
            
            # 处理组合类型
            if "oneOf" in field_schema or "anyOf" in field_schema:
                combo_key = "oneOf" if "oneOf" in field_schema else "anyOf"
                combo_types = []
                for option in field_schema[combo_key]:
                    if "type" in option:
                        combo_types.append(option["type"])
                    elif "$ref" in option:
                        ref_path = option["$ref"]
                        ref_model = ref_path.split("#/$defs/")[-1]
                        combo_types.append(ref_model)
                type_str = " | ".join(combo_types)
                field_parts.append(f"{prefix}- **{field_name}** ({type_str}): {field_description}")
                return "\n".join(field_parts)
            
            # 处理基本类型
            if field_type == "array":
                # 处理数组类型
                items = field_schema.get("items", {})
                if "$ref" in items:
                    ref_path = items["$ref"]
                    item_type = ref_path.split("#/$defs/")[-1]
                    field_parts.append(f"{prefix}- **{field_name}** (列表[{item_type}]): {field_description}")
                elif "type" in items:
                    item_type = items["type"]
                    field_parts.append(f"{prefix}- **{field_name}** (列表[{item_type}]): {field_description}")
                else:
                    field_parts.append(f"{prefix}- **{field_name}** (列表): {field_description}")
            
            elif field_type == "object":
                # 处理嵌套对象
                if "properties" in field_schema:
                    # 内联对象，生成嵌套描述
                    field_parts.append(f"{prefix}- **{field_name}** (对象): {field_description}")
                    for nested_field, nested_schema in field_schema["properties"].items():
                        nested_desc = _process_field(nested_field, nested_schema, indent + 1)
                        field_parts.append(nested_desc)
                else:
                    field_parts.append(f"{prefix}- **{field_name}** (对象): {field_description}")
            
            else:
                # 基本类型
                field_parts.append(f"{prefix}- **{field_name}** ({field_type}): {field_description}")
            
            # 添加字段约束
            constraints = []
            if "enum" in field_schema:
                enum_values = ", ".join([str(v) for v in field_schema["enum"]])
                constraints.append(f"可选值: {enum_values}")
            
            if "minLength" in field_schema:
                constraints.append(f"最小长度: {field_schema['minLength']}")
            
            if "maxLength" in field_schema:
                constraints.append(f"最大长度: {field_schema['maxLength']}")
            
            if "minimum" in field_schema:
                constraints.append(f"最小值: {field_schema['minimum']}")
            
            if "maximum" in field_schema:
                constraints.append(f"最大值: {field_schema['maximum']}")
            
            if "pattern" in field_schema:
                constraints.append(f"格式: {field_schema['pattern']}")
            
            if constraints:
                field_parts[-1] += f" 【{', '.join(constraints)}】"
            
            return "\n".join(field_parts)
        
        # 处理主模型
        model_description = json_schema.get("description", f"{model_name}模型")
        prompt_parts.append(f"### {model_name}")
        prompt_parts.append(model_description)
        prompt_parts.append("")
        
        # 处理properties
        properties = json_schema.get("properties", {})
        if properties:
            prompt_parts.append("#### 字段定义")
            prompt_parts.append("")
            
            for field_name, field_schema in properties.items():
                field_desc = _process_field(field_name, field_schema)
                prompt_parts.append(field_desc)
            
            prompt_parts.append("")
        
        # 处理required字段
        required = json_schema.get("required", [])
        if required:
            required_fields = ", ".join(required)
            prompt_parts.append(f"#### 必填字段")
            prompt_parts.append(f"{required_fields}")
            prompt_parts.append("")
        
        # 处理嵌套模型定义
        if "$defs" in json_schema:
            for def_name, def_schema in json_schema["$defs"].items():
                # 添加嵌套模型描述
                def_description = def_schema.get("description", f"{def_name}模型")
                prompt_parts.append(f"### {def_name}")
                prompt_parts.append(def_description)
                prompt_parts.append("")
                
                # 处理嵌套模型的properties
                def_properties = def_schema.get("properties", {})
                if def_properties:
                    prompt_parts.append("#### 字段定义")
                    prompt_parts.append("")
                    
                    for field_name, field_schema in def_properties.items():
                        field_desc = _process_field(field_name, field_schema)
                        prompt_parts.append(field_desc)
                    
                    prompt_parts.append("")
                
                # 处理嵌套模型的required字段
                def_required = def_schema.get("required", [])
                if def_required:
                    def_required_fields = ", ".join(def_required)
                    prompt_parts.append(f"#### 必填字段")
                    prompt_parts.append(f"{def_required_fields}")
                    prompt_parts.append("")
        
        return "\n".join(prompt_parts)
    
    def generate_prompt_from_json(self, json_schema: Dict[str, Any], model_name: str = "GeneratedModel") -> str:
        """将Pydantic模型的model_json_schema生成的JSON转换为结构化提示词
        
        Args:
            json_schema: Pydantic模型的model_json_schema生成的JSON
            model_name: 模型名称
            
        Returns:
            结构化的提示词字符串
        """
        return self._generate_pydantic_from_json(json_schema, model_name)
    
    def generate_prompt_from_model(self, model: Type[BaseModel]) -> str:
        """从Pydantic模型生成结构化提示词
        
        Args:
            model: Pydantic模型类
            
        Returns:
            结构化的提示词字符串
        """
        # 获取模型的JSON schema
        json_schema = model.model_json_schema()
        # 生成提示词
        return self._generate_pydantic_from_json(json_schema, model.__name__)
    
    def generate_prompt_from_json_using_llm(self, json_schema: Dict[str, Any], model_name: str = "GeneratedModel") -> str:
        """通过LLM将Pydantic模型的model_json_schema生成的嵌套JSON转换成结构化的提示词表示（公共方法）
        
        Args:
            json_schema: Pydantic模型的model_json_schema生成的JSON
            model_name: 模型名称
            
        Returns:
            结构化的提示词字符串
        """
        return self._generate_prompt_from_json_using_llm(json_schema, model_name)
    
    def generate_prompt_from_model_using_llm(self, model: Type[BaseModel]) -> str:
        """通过LLM从Pydantic模型生成结构化提示词（公共方法）
        
        Args:
            model: Pydantic模型类
            
        Returns:
            结构化的提示词字符串
        """
        # 获取模型的JSON schema
        json_schema = model.model_json_schema()
        # 生成提示词
        return self._generate_prompt_from_json_using_llm(json_schema, model.__name__)
    
    def _generate_prompt_from_json_using_llm(self, json_schema: Dict[str, Any], model_name: str = "GeneratedModel") -> str:
        """通过LLM将Pydantic模型的model_json_schema生成的嵌套JSON转换成结构化的提示词表示（私有方法）
        
        Args:
            json_schema: Pydantic模型的model_json_schema生成的JSON
            model_name: 模型名称
            
        Returns:
            结构化的提示词字符串
        """
        if not self.fastapi_url:
            # 如果没有LLM API URL，使用默认的提示词生成逻辑
            return self._generate_pydantic_from_json(json_schema, model_name)
        
        try:
            # 构建系统提示词
            system_prompt = """你是一个专业的数据结构分析师和提示词工程师。请将Pydantic模型的JSON Schema转换为结构化的提示词表示。

转换规则：
1. 以清晰、结构化的方式描述模型及其所有字段
2. 包含模型名称、描述、字段定义（名称、类型、描述）、必填字段等信息
3. 处理嵌套模型，为每个嵌套模型创建独立的章节
4. 对于数组类型，明确说明元素类型
5. 对于引用类型，正确关联到对应的模型
6. 使用Markdown格式，包括标题、列表、加粗等格式
7. 保持提示词简洁明了，便于LLM理解和使用
8. 包含所有重要的约束信息（如最小值、最大值、枚举值等）

请根据输入的JSON Schema生成高质量的结构化提示词。"""
            
            # 构建用户提示词
            user_prompt = f"""请根据以下Pydantic模型的JSON Schema生成结构化提示词：

模型名称：{model_name}
JSON Schema：
{json.dumps(json_schema, ensure_ascii=False, indent=2)}

请严格按照转换规则生成提示词，确保所有信息都被正确包含和格式化。"""
            
            # 构建请求数据
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            # 调用LLM API
            response = requests.post(self.fastapi_url, json={"model":self.model_id, "messages": messages, "enable_thinking": self.enable_thinking})
            
            if response.status_code == 200:
                result = response.json()
                return result["messages"][-1]["content"].strip()
            else:
                # API调用失败，使用默认逻辑
                return self._generate_pydantic_from_json(json_schema, model_name)
        except Exception as e:
            print(f"调用LLM生成提示词失败: {e}")
            # 发生异常，使用默认逻辑
            return self._generate_pydantic_from_json(json_schema, model_name)
    
    def generate_json_from_context_using_llm(self, context: str) -> Dict[str, Any]:
        """通过LLM将文本上下文转换为结构化的嵌套JSON表示
        
        Args:
            context: 输入的文本上下文
            model_name: 生成的JSON模型名称（用于提示词中）
            
        Returns:
            结构化的嵌套JSON字典
        """
        if not self.fastapi_url:
            # 如果没有LLM API URL，返回空字典
            return {}
        
        try:
            # 构建系统提示词
            system_prompt = """你是一个专业的数据结构分析师和JSON格式化专家。请将输入的文本上下文转换为结构化的嵌套JSON表示。

转换规则：
1. 仔细阅读文本上下文，提取所有关键信息
2. 识别实体、属性和它们之间的关系
3. 使用合适的JSON结构来表示这些信息（包括嵌套结构）
4. 使用有意义的键名，优先使用英文驼峰命名法
5. 确保JSON格式正确，包含必要的括号和引号
6. 只返回JSON内容，不包含任何解释或说明文字
7. 保持JSON结构简洁明了，避免冗余信息
8. 对于数组类型，使用方括号[]表示
9. 对于对象类型，使用花括号{}表示
10. 确保所有值都有适当的数据类型（字符串、数字、布尔值、数组、对象）

请根据输入的文本上下文生成高质量的结构化JSON。"""
            
            # 构建用户提示词
            user_prompt = f"""请将以下文本上下文转换为结构化的嵌套JSON表示：

文本上下文：
{context}

请严格按照转换规则生成JSON，确保格式正确且只包含JSON内容。"""
            
            # 构建请求数据
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            # 调用LLM API
            response = requests.post(self.fastapi_url, json={"model": self.model_id, "messages": messages, "enable_thinking": self.enable_thinking})
            
            if response.status_code == 200:
                result = response.json()
                json_content = result["messages"][-1]["content"].strip()
                # 解析生成的JSON
                return self.parser.parse(json_content)
            else:
                # API调用失败，返回空字典
                return {}
        except Exception as e:
            print(f"调用LLM生成JSON失败: {e}")
            # 发生异常，返回空字典
            return {}
