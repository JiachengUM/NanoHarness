from enum import Enum
from typing import Any, Dict, Callable, Optional, Union, Literal

from pydantic import BaseModel

from nanoai.utils.nl_repr import nl_repr


class KeySource(str, Enum):
    """键来源选项"""
    DESCRIPTION = "description"
    ALIAS = "alias"
    FIELD_NAME = "field_name"
    ANNOTATION = "annotation"


class ValueSource(str, Enum):
    """值来源选项"""
    VALUE = "value"  # 字段值
    DESCRIPTION = "description"  # 字段描述
    ALIAS = "alias"  # 字段别名
    FIELD_NAME = "field_name"  # 字段名
    ANNOTATION = "annotation"  # 新增注解来源


class KVOrder(str, Enum):
    """KV顺序选项"""
    KV = "kv"  # 键在前
    VK = "vk"  # 值在前


def get_field_constraints(field) -> str:
    """获取字段的约束条件并转换为中文描述"""
    if not hasattr(field, 'field_info'):
        return ""

    constraints = []
    field_info = field.field_info

    # 数值范围约束
    if hasattr(field_info, 'gt') and field_info.gt is not None:
        constraints.append(f"大于{field_info.gt}")
    if hasattr(field_info, 'ge') and field_info.ge is not None:
        constraints.append(f"大于等于{field_info.ge}")
    if hasattr(field_info, 'lt') and field_info.lt is not None:
        constraints.append(f"小于{field_info.lt}")
    if hasattr(field_info, 'le') and field_info.le is not None:
        constraints.append(f"小于等于{field_info.le}")
    if hasattr(field_info, 'multiple_of') and field_info.multiple_of is not None:
        constraints.append(f"{field_info.multiple_of}的倍数")

    # 字符串长度约束
    if hasattr(field_info, 'min_length') and field_info.min_length is not None:
        constraints.append(f"最小长度{field_info.min_length}")
    if hasattr(field_info, 'max_length') and field_info.max_length is not None:
        constraints.append(f"最大长度{field_info.max_length}")

    # 正则表达式约束
    if hasattr(field_info, 'pattern') and field_info.pattern is not None:
        pattern_str = str(field_info.pattern)
        # 简化正则表达式显示
        if pattern_str.startswith('^') and pattern_str.endswith('$'):
            pattern_str = pattern_str[1:-1]
        constraints.append(f"格式: {pattern_str}")

    # 枚举值约束
    if hasattr(field_info, 'enum_values') and field_info.enum_values:
        enum_str = "、".join(str(v) for v in field_info.enum_values[:5])
        if len(field_info.enum_values) > 5:
            enum_str += f"等{len(field_info.enum_values)}个选项"
        constraints.append(f"可选值: {enum_str}")

    # 必填/可选约束
    if hasattr(field, 'is_required'):
        if not field.is_required:
            constraints.append("可选")
        else:
            constraints.append("必填")
    elif hasattr(field_info, 'default') and field_info.default is not None:
        constraints.append("可选")
    else:
        constraints.append("必填")

    # 默认值
    if hasattr(field_info, 'default') and field_info.default is not None:
        default = field_info.default
        if callable(default):
            try:
                default_value = default()
                constraints.append(f"默认值: {default_value}")
            except:
                constraints.append("有默认值")
        else:
            constraints.append(f"默认值: {default}")
    elif hasattr(field_info, 'default_factory') and field_info.default_factory is not None:
        constraints.append("有默认值")

    # 其他常见约束
    if hasattr(field_info, 'min_items') and field_info.min_items is not None:
        constraints.append(f"最少{field_info.min_items}个元素")
    if hasattr(field_info, 'max_items') and field_info.max_items is not None:
        constraints.append(f"最多{field_info.max_items}个元素")

    if hasattr(field_info, 'unique_items') and field_info.unique_items:
        constraints.append("元素必须唯一")

    if hasattr(field_info, 'allow_inf_nan') and not field_info.allow_inf_nan:
        constraints.append("不允许无限大或非数字")

    if hasattr(field_info, 'strip_whitespace') and field_info.strip_whitespace:
        constraints.append("自动去除首尾空格")

    if hasattr(field_info, 'to_lower') and field_info.to_lower:
        constraints.append("自动转换为小写")

    if hasattr(field_info, 'to_upper') and field_info.to_upper:
        constraints.append("自动转换为大写")

    return "，".join(constraints) if constraints else ""


def to_kv_prompt(
        model: BaseModel,
        key_source: Union[KeySource, Literal["description", "alias", "field_name"]] = KeySource.DESCRIPTION,
        value_source: Union[ValueSource, Literal["value", "description", "alias", "field_name"]] = ValueSource.VALUE,
        value_formatter: Optional[Callable[[Any], str]] = nl_repr,
        order: Union[KVOrder, Literal["kv", "vk"]] = KVOrder.KV,
        include_constraints: bool = True
) -> str:
    """将模型转换为KV结构的提示词，包含约束条件
    Args:
        model: Pydantic模型实例
        key_source: 键的来源，可选值为 "description"、"alias" 或 "field_name"
        value_source: 值的来源，可选值为 "value"、"description"、"alias" 或 "field_name"
        value_formatter: 值格式化函数，接收字段值，返回格式化后的字符串
        order: 键值顺序，"kv"表示键在前，"vk"表示值在前
        include_constraints: 是否包含约束条件
    """
    # 将字符串转换为枚举（如果是字符串的话）
    if isinstance(key_source, str):
        key_source = KeySource(key_source.lower())
    if isinstance(value_source, str):
        value_source = ValueSource(value_source.lower())
    if isinstance(order, str):
        order = KVOrder(order.lower())
    items = []
    for field_name, field in model.model_fields.items():
        # 获取键
        if key_source == KeySource.DESCRIPTION and field.description:
            key = field.description
        elif key_source == KeySource.ALIAS and field.alias:
            key = field.alias
        else:
            key = field_name
        # 获取值
        if value_source == ValueSource.VALUE:
            raw_value = getattr(model, field_name)
        elif value_source == ValueSource.DESCRIPTION:
            raw_value = field.description
        elif value_source == ValueSource.ALIAS:
            raw_value = field.alias
        else:  # value_source == ValueSource.FIELD_NAME
            raw_value = field_name
        # 处理None值
        if raw_value is None:
            value_str = ""
        elif value_formatter:
            value_str = value_formatter(raw_value)
        else:
            value_str = str(raw_value)
        # 获取约束条件
        constraint_str = ""
        if include_constraints:
            constraints = get_field_constraints(field)
            constraint_str = f"（{constraints}）" or ""
        # 根据order参数决定顺序
        if order == KVOrder.VK:
            items.append(f"{value_str}：{key}{constraint_str}")
        else:  # 默认KV顺序
            items.append(f"{key}：{value_str}{constraint_str}")
    return "\n".join(items)


class SchemaFilter:
    """可配置的Schema过滤器"""

    def __init__(self,
                 include_type: bool = True,
                 include_constraints: bool = True,
                 include_required: bool = True,
                 include_nested: bool = True,
                 include_defaults: bool = False,
                 include_format: bool = False,
                 include_description: bool = True):
        self.include_type = include_type
        self.include_constraints = include_constraints
        self.include_required = include_required
        self.include_nested = include_nested
        self.include_defaults = include_defaults
        self.include_format = include_format
        self.include_description = include_description

        # 定义要保留的约束类型
        self.constraint_keys = {
            "enum", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
            "multipleOf", "minLength", "maxLength", "pattern", "minItems",
            "maxItems", "uniqueItems", "minProperties", "maxProperties"
        }

        if self.include_format:
            self.constraint_keys.add("format")

    def filter_schema(self, model_schema: Dict[str, Any]) -> Dict[str, Any]:
        """过滤schema并合并$ref引用"""
        if not isinstance(model_schema, dict):
            return model_schema
        
        # 首先提取所有定义
        all_defs = {}
        if "$defs" in model_schema:
            all_defs.update(model_schema["$defs"])
        if "definitions" in model_schema:
            all_defs.update(model_schema["definitions"])
        
        # 创建一个副本，避免修改原始schema
        schema_copy = model_schema.copy()
        
        # 移除$defs和definitions，避免重复处理
        for key in ["$defs", "definitions"]:
            if key in schema_copy:
                del schema_copy[key]
        
        # 先过滤schema
        filtered_schema = self._filter_schema(schema_copy)
        
        # 合并$ref引用
        merged_schema = self._resolve_refs(filtered_schema, all_defs)
        
        return merged_schema
    
    def _filter_schema(self, model_schema: Dict[str, Any]) -> Dict[str, Any]:
        """过滤schema"""
        if not isinstance(model_schema, dict):
            return model_schema
        
        result = {}

        # 添加description
        if self.include_description and "description" in model_schema:
            result["description"] = model_schema["description"]

        if self.include_type:
            result["type"] = model_schema.get("type", "object")

        properties = model_schema.get("properties", {})
        if properties:
            result["properties"] = {}
            for field_name, field_schema in properties.items():
                result["properties"][field_name] = self._filter_field(field_schema)

        if self.include_required:
            required = model_schema.get("required", [])
            if required:
                result["required"] = required

        # 处理组合类型
        for combo_key in ["oneOf", "anyOf", "allOf", "not"]:
            if combo_key in model_schema:
                combo_value = model_schema[combo_key]
                processed_value = None
                
                if isinstance(combo_value, list):
                    # 过滤空列表，只处理非空列表
                    filtered_items = []
                    for item in combo_value:
                        filtered_item = self._filter_schema(item)
                        # 只有非空字典或非字典类型才添加
                        if filtered_item or not isinstance(filtered_item, dict):
                            filtered_items.append(filtered_item)
                    
                    if filtered_items:
                        # 如果只有一个元素且是字典，可以考虑扁平化
                        if len(filtered_items) == 1 and isinstance(filtered_items[0], dict):
                            # 对于"not"类型，不能扁平化，因为它需要明确的否定结构
                            if combo_key != "not":
                                processed_value = filtered_items[0]
                            else:
                                processed_value = filtered_items
                        else:
                            processed_value = filtered_items
                
                elif isinstance(combo_value, dict):
                    # 处理单个字典
                    filtered_dict = self._filter_schema(combo_value)
                    if filtered_dict:  # 只添加非空字典
                        processed_value = filtered_dict
                
                # 只有处理后的值非空才添加到结果中
                if processed_value is not None:
                    result[combo_key] = processed_value

        # 添加constraints
        if self.include_constraints:
            for key in self.constraint_keys:
                if key in model_schema:
                    result[key] = model_schema[key]

        return result
    
    def _filter_field(self, field_schema: Dict[str, Any]) -> Dict[str, Any]:
        """过滤单个字段"""
        if not isinstance(field_schema, dict):
            return field_schema
        
        result = {}

        # 添加description
        if self.include_description and "description" in field_schema:
            result["description"] = field_schema["description"]

        # 处理引用 - 暂时保留，后续由_resolve_refs处理
        if "$ref" in field_schema:
            result["$ref"] = field_schema["$ref"]
            return result

        # 添加type
        if self.include_type and "type" in field_schema:
            result["type"] = field_schema["type"]
            
            # 处理不同类型
            self._handle_type_specific(result, field_schema)

        # 处理组合类型
        for combo_key in ["oneOf", "anyOf", "allOf", "not"]:
            if combo_key in field_schema:
                combo_value = field_schema[combo_key]
                processed_value = None
                
                if isinstance(combo_value, list):
                    # 过滤空列表，只处理非空列表
                    filtered_items = []
                    for item in combo_value:
                        filtered_item = self._filter_field(item)
                        # 只有非空字典或非字典类型才添加
                        if filtered_item or not isinstance(filtered_item, dict):
                            filtered_items.append(filtered_item)
                    
                    if filtered_items:
                        # 如果只有一个元素且是字典，可以考虑扁平化
                        if len(filtered_items) == 1 and isinstance(filtered_items[0], dict):
                            # 对于"not"类型，不能扁平化，因为它需要明确的否定结构
                            if combo_key != "not":
                                processed_value = filtered_items[0]
                            else:
                                processed_value = filtered_items
                        else:
                            processed_value = filtered_items
                
                elif isinstance(combo_value, dict):
                    # 处理单个字典
                    filtered_dict = self._filter_field(combo_value)
                    if filtered_dict:  # 只添加非空字典
                        processed_value = filtered_dict
                
                # 只有处理后的值非空才添加到结果中
                if processed_value is not None:
                    result[combo_key] = processed_value

        # 添加约束
        if self.include_constraints:
            for key in self.constraint_keys:
                if key in field_schema:
                    result[key] = field_schema[key]

        # 添加默认值
        if self.include_defaults and "default" in field_schema:
            result["default"] = field_schema["default"]

        return result
    
    def _handle_type_specific(self, result: Dict[str, Any], field_schema: Dict[str, Any]) -> None:
        """处理类型特定的schema"""
        field_type = field_schema["type"]
        
        if field_type == "array" and "items" in field_schema:
            items = field_schema["items"]
            if isinstance(items, list):
                # 处理tuple类型（固定长度数组）
                result["items"] = [self._filter_field(item) for item in items]
            elif isinstance(items, dict):
                # 处理普通数组
                result["items"] = self._filter_field(items)
        
        elif field_type == "object":
            # 递归处理object类型的properties
            if "properties" in field_schema:
                result["properties"] = {}
                for prop_name, prop_schema in field_schema["properties"].items():
                    result["properties"][prop_name] = self._filter_field(prop_schema)
            
            # 处理additionalProperties
            if "additionalProperties" in field_schema:
                additional_props = field_schema["additionalProperties"]
                if isinstance(additional_props, dict):
                    result["additionalProperties"] = self._filter_field(additional_props)
                else:
                    result["additionalProperties"] = additional_props
        
        elif field_type == "integer" or field_type == "number":
            # 数值类型的约束已经在constraint_keys中处理
            pass
        
        elif field_type == "string":
            # 字符串类型的约束已经在constraint_keys中处理
            pass
        
        elif field_type == "boolean":
            # boolean类型没有特殊约束
            pass
        
        elif field_type == "null":
            # null类型没有特殊约束
            pass
    
    def _resolve_refs(self, schema: Any, all_defs: Dict[str, Any]) -> Any:
        """递归解析并合并$ref引用"""
        if not isinstance(schema, dict):
            return schema
        
        # 检查是否为引用
        if "$ref" in schema:
            ref_path = schema["$ref"]
            
            # 从$ref中提取定义名称
            def_name = None
            if "#/$defs/" in ref_path:
                def_name = ref_path.split("#/$defs/")[-1]
            elif "#/definitions/" in ref_path:
                def_name = ref_path.split("#/definitions/")[-1]
            elif "/" in ref_path:
                # 处理其他格式的引用
                def_name = ref_path.split("/")[-1]
            
            if def_name and def_name in all_defs:
                # 获取原始定义并递归解析
                original_def = all_defs[def_name]
                resolved_def = self._filter_schema(original_def)
                resolved_def = self._resolve_refs(resolved_def, all_defs)
                
                # 合并原始schema的其他属性
                for key, value in schema.items():
                    if key != "$ref":
                        resolved_def[key] = value
                
                return resolved_def
            else:
                # 找不到定义，返回原始schema
                return schema
        
        # 递归处理schema中的所有属性
        keys_to_remove = []
        for key, value in schema.items():
            if isinstance(value, dict):
                resolved_value = self._resolve_refs(value, all_defs)
                if resolved_value:  # 只保留非空字典
                    schema[key] = resolved_value
                else:
                    keys_to_remove.append(key)
            elif isinstance(value, list):
                resolved_items = []
                for item in value:
                    resolved_item = self._resolve_refs(item, all_defs)
                    if resolved_item or not isinstance(resolved_item, dict):
                        resolved_items.append(resolved_item)
                
                if resolved_items:
                    # 扁平化处理：如果只有一个字典元素，且不是"not"类型，则直接使用该字典
                    if len(resolved_items) == 1 and isinstance(resolved_items[0], dict):
                        if key != "not":
                            schema[key] = resolved_items[0]
                        else:
                            schema[key] = resolved_items
                    else:
                        schema[key] = resolved_items
                else:
                    keys_to_remove.append(key)
        
        # 移除空值
        for key in keys_to_remove:
            del schema[key]
        
        return schema
    



# 使用示例
if __name__ == "__main__":
    from cabin_advisor.worker.comfort_advisor_worker import ComfortAdvisorWorker
    from pydantic import BaseModel, Field
    from typing import List, Optional, Union, Dict
    from nanoai.utils import get_logger
    
    # 定义复杂的测试模型，确保生成带有$ref的schema
    class Address(BaseModel):
        """地址模型"""
        street: str = Field(description="街道地址")
        city: str = Field(description="城市")
        zip_code: str = Field(description="邮政编码")
    
    class Product(BaseModel):
        """产品模型"""
        id: str = Field(description="产品ID")
        name: str = Field(description="产品名称")
        price: float = Field(description="产品价格")
    
    class OrderItem(BaseModel):
        """订单项模型"""
        product: Product = Field(description="产品信息")
        quantity: int = Field(description="数量")
    
    class User(BaseModel):
        """用户模型"""
        name: str = Field(description="用户名", min_length=2, max_length=4)
        age: Optional[int] = Field(None, description="年龄", ge=30)
        email: str = Field(description="邮箱", pattern="^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$")
        addresses: List[Address] = Field(description="地址列表")
        orders: List[OrderItem] = Field(description="订单列表")
        metadata: Dict[str, Union[str, int, bool]] = Field(description="元数据")


    # 初始化日志记录器
    logger = get_logger("parser")

    # 初始化Worker
    model_path = "F:/Download/qwen3-1.7B"
    # model_path = "/Users/chris-macbookair/Downloads/qwen3/qwen3-0.6B"
    worker = ComfortAdvisorWorker(model=model_path, hf_token="REDACTED")
    try:
        logger.info("=== 开始测试SchemaFilter ===")
        
        # 获取原始schema
        logger.info("获取原始schema...")
        schema = User.model_json_schema()
        logger.info("原始schema获取成功")
        
        # 检查是否包含$defs
        if "$defs" in schema:
            logger.info(f"原始schema包含$defs: {list(schema['$defs'].keys())}")
        
        # 创建过滤器
        logger.info("创建SchemaFilter...")
        filter_config = SchemaFilter(
            include_type=False,
            include_defaults=False,
            include_constraints=True,
            include_required=True,
            include_nested=True,
            include_format=True,
            include_description=True
        )
        logger.info("SchemaFilter创建成功")
        
        # 过滤并合并schema
        logger.info("过滤并合并schema...")

        # filtered_json = filter_config.filter_schema(schema)
        filtered_json = worker.parser.read_json(path="user_complete_data.json")
        prompt = worker.json_to_prompt(filtered_json, User.__name__)
        logger.info(prompt)
        logger.info("json转换to_prompt成功\n\n")
        json_content = worker.prompt_to_json(prompt)
        logger.info(json_content)
        logger.info("prompt转换to_json成功\n\n")
        pydantic_df = worker.json_to_instance(json_content, User.__name__)
        logger.info(pydantic_df)
        logger.info("json转换pydantic成功\n\n")
        logger.info("Schema过滤并合并成功")
        # TODO 输入的数据结构中能够根据树状目标对可能缺失的字段名称、值、描述做推测

        # 检查结果
        logger.info("检查结果...")
        if "$defs" not in filtered_json and "definitions" not in filtered_json:
            logger.info("结果中已移除$defs和definitions")
        
        # 检查是否有剩余的$ref
        import json
        schema_str = json.dumps(filtered_json)
        if "$ref" in schema_str:
            logger.info(f"结果中仍包含$ref引用: {schema_str.count('$ref')}处")
        else:
            logger.info("结果中已无$ref引用")
        
        logger.info("=== 测试完成 ===")
        logger.info("=== 合并后的Schema结果 ===")
        logger.info(json.dumps(filtered_json, ensure_ascii=False, indent=2))
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
