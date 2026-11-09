from typing import Optional

import requests
from cabin_advisor.define.role import COMFORT_ADVISOR_PROFILES
from cabin_advisor.define.scenario import (
    QAList, QAItem, VehicleControlScene, InCarRole, ComfortAdviceOutput
)
from cabin_advisor.parser_utils.parser import LenientJSONParser
from nanoai.utils.to_prompt import to_kv_prompt, KVOrder, KeySource, ValueSource, SchemaFilter
from nanoai.utils.to_pydantic import ToPydanticConverter
from pydantic import BaseModel

from nanoai.utils import get_logger

# 初始化日志记录器
logger = get_logger("worker")

# 使用Pydantic模型定义配置
class SchemaConfig(BaseModel):
    include_type: bool = False
    include_defaults: bool = False
    include_constraints: bool = True
    include_required: bool = True
    include_nested: bool = True
    include_format: bool = True
    include_description: bool = True

    class Config:
        # 允许从字典创建实例
        from_attributes = True


class ComfortAdvisorWorker:
    """智能座舱舒适场景Advisor工作器，使用Qwen模型"""

    def __init__(self, model: Optional[str] = None, client: Optional[object] = None, hf_token: Optional[str] = None, enable_thinking: bool = False, schema_config: Optional[SchemaConfig] = None):
        """初始化舒适场景Advisor工作器"""
        self.model = model
        self.enable_thinking = enable_thinking
        self.client = client
        self.hf_token = hf_token
        self.DEFAULT_ROLE = "驾驶员"
        # 初始化FastAPI服务地址
        # self.fastapi_url = "http://172.1.143.182:8000/v1/chat/completions"
        self.fastapi_url = "http://localhost:8000/v1/chat/completions"
        self.converter = ToPydanticConverter(model=self.model, enable_thinking=self.enable_thinking, fastapi_url=self.fastapi_url)
        # 初始化角色配置，避免重复获取
        self.role_profiles = COMFORT_ADVISOR_PROFILES
        self.parser = LenientJSONParser(model=self.model, enable_thinking=self.enable_thinking)
        self.schema_config = SchemaFilter(schema_config.dict())
        # 设置默认系统提示词
        self.default_scene_analyst_prompt = "你是一位智能座舱场景分析专家，擅长从对话数据中分析用户需求，识别具体的舒适场景，并转化为可执行的车控指令。"
        self.default_dialogue_generator_prompt = "你是一位智能座舱对话生成专家，能够根据车控场景描述和角色设定，生成自然流畅的对话流，模拟真实的用户与系统交互过程。"

    def json_to_instance_v1(self, df, name):
        # TODO 目前实现逻辑：输入是数据结构对象，例如嵌套json、dict、list、str，以提示词驱动方式通过调用qwen_api.py中的服务接口v1/chat/completions，输出padanmic模型；
        ## 提示词处理逻辑：首先分析数据结构，在键值对儿情况中，如果值是键的description，依据键值描述生成值的mock用例作为模型的example；如果值是具体用例时，依据键值信息生成值的description；
        ## 列表类型转化时检查嵌套，原则上列表中的元素为str，如果列表中的元素是具体用例，生成合适的字段名称、default值、description和example；str处理逻辑和列表的元素一样；
        ## 输出完整的padanmic模型，包括键作为字段名称、指向的数据类型、对应Field的default取键值对儿的值，description、example，尽可能保留原数据结构的语义特征。
        # TODO 不够高效，需要多次处理，有没有可能改成一次生成？需要测试来决定，甚至计算pydantic复杂度
        pydantic_model = self.converter.convert(df, model_name=name)
        instance = pydantic_model(**df)
        return instance
        
    def json_to_instance(self, df, name):
        # TODO V2一次性生成，未测
        # 一次生成Pydantic模型的实现
        # 输入是数据结构对象，例如嵌套json、dict、list、str
        # 使用一次LLM调用直接生成完整的Pydantic模型代码
        # 输出包含完整语义特征的Pydantic模型实例
        
        try:
            # 构建系统提示词，指导LLM生成正确的Pydantic模型
            system_prompt = """你是一位专业的数据结构分析师和Pydantic模型专家。请根据输入的数据结构生成完整的Pydantic模型代码。
            
生成规则：
1. 分析数据结构，识别键值对、列表、嵌套结构等
2. 在键值对情况中：
   - 如果值是键的description，依据键值描述生成值的mock用例作为模型的example
   - 如果值是具体用例时，依据键值信息生成值的description
3. 列表类型处理：
   - 检查嵌套，原则上列表中的元素为str
   - 如果列表中的元素是具体用例，生成合适的字段名称、default值、description和example
4. 输出完整的Pydantic模型代码，包括：
   - 键作为字段名称
   - 指向的数据类型
   - 对应Field的default取键值对儿的值
   - description
   - example
5. 尽可能保留原数据结构的语义特征
6. 只返回Pydantic模型代码，不包含其他解释性内容
7. 确保生成的代码可以直接执行
8. 处理嵌套结构，生成合适的嵌套Pydantic模型
9. 为列表类型生成正确的类型注解（使用List[T]）
10. 为所有导入包提供完整的导入语句
            
示例输入：
{"name": "用户信息", "age": 25, "hobbies": ["读书", "跑步"]}

示例输出：
from pydantic import BaseModel, Field
from typing import List

class UserInfo(BaseModel):
    name: str = Field(default="用户信息", description="用户的名称", example="用户信息")
    age: int = Field(default=25, description="用户的年龄", example=25)
    hobbies: List[str] = Field(default=["读书", "跑步"], description="用户的爱好列表", example=["读书", "跑步"])
            """
            
            # 构建用户提示词
            user_prompt = f"""请根据以下数据结构生成完整的Pydantic模型代码，模型名称为{name}：{df}
            """
            
            # 构建请求数据
            payload = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "enable_thinking": False,
                "model": self.model,
                "hf_token": self.hf_token,
            }
            
            # 发送请求到FastAPI服务
            response = requests.post(self.fastapi_url, json=payload)
            response.raise_for_status()
            
            # 解析响应数据
            result = response.json()
            
            # 提取生成的Pydantic模型代码
            generated_code = result['messages'][-1]['content']
            
            # 清理生成的代码（去除可能的markdown标记）
            generated_code = self.parser.safe_parse(generated_code)

            # 创建一个临时命名空间，用于执行生成的代码
            temp_namespace = {}
            
            # 执行生成的Pydantic模型代码
            exec(generated_code, temp_namespace)
            
            # 获取生成的模型类
            model_class = temp_namespace.get(name)
            if not model_class:
                # 如果直接获取失败，尝试获取模块中的模型类
                for key, value in temp_namespace.items():
                    if key == name:
                        model_class = value
                        break
            
            if not model_class:
                raise ValueError(f"无法从生成的代码中获取模型类{name}")
            
            # 用输入数据实例化该Pydantic模型并返回
            instance = model_class(**df)
            return instance
            
        except Exception as e:
            logger.error(f"json_to_instance_v2方法执行失败: {e}")
            # 如果v2方法失败，回退到原有的v1方法
            # return self.json_to_instance(df, name)

    def instance_to_prompt(self, df):
        schema = df.model_json_schema()
        json_df = self.schema_config.filter_schema(schema)
        return self.converter.generate_prompt_from_json_using_llm(json_df, model_name=df.__name__)

    def prompt_to_json(self, df):
        return self.converter.generate_json_from_context_using_llm(df)

    def analyze_dialogue_to_scene(self, qa_list: QAList, role: InCarRole=None, output_format: BaseModel=None) -> VehicleControlScene:
        """分析对话数据，输出车控场景"""
        # TODO 将对话转换为文本时需要识别代入角色
        # dialogue_text = "\n".join([f"用户: {qa.question}\n助手: {qa.answer}" for qa in qa_list.qa_list])
        dialogue_text = "\n".join([f"{qa.question}\n{qa.answer}\n{qa.think}" for qa in qa_list.qa_list])

        # 获取场景分析师的系统提示词
        scene_analyst_profile = self.role_profiles["scene_analyst"]
        sys_prompt = scene_analyst_profile.system_prompt or self.default_scene_analyst_prompt

        # 构建分析指令
        role_info = f"""\n\n{to_kv_prompt(model=role, key_source=KeySource.DESCRIPTION, value_source=ValueSource.VALUE) or self.DEFAULT_ROLE}"""
        output_format = to_kv_prompt(model=output_format, key_source=KeySource.DESCRIPTION, value_source=ValueSource.FIELD_NAME, order=KVOrder.VK)
        input_prompt = f"""请分析以下对话，确定对应的车辆控制场景：
                        {dialogue_text}{role_info}
                        请返回包含以下信息的JSON：
                        {output_format or ""}
                        """
        try:
            # 构建请求数据
            payload = {
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": input_prompt}
                ],
                "enable_thinking": False,
                "model": self.model,
                "hf_token": self.hf_token,
            }
            
            # 发送请求到FastAPI服务
            response = requests.post(self.fastapi_url, json=payload)
            response.raise_for_status()
            
            # 解析响应数据
            result = response.json()
            
            # 提取最后一条消息的内容（模型生成的文本）
            generated_text = result['messages'][-1]['content']
            # 将生成的JSON文本转换为VehicleControlScene对象
            # TODO 将解释说明过程放到think的pydantic里面去，enable_think=True的时候也将qwen自己的cot过程放到think对象的pydantic里面输出
            scene_data = self.parser.safe_parse(generated_text)
            # TODO 加个提示词驱动的方法，用于对模型输出的结构进行提炼，如果模型输出里有分析、总结、思考等过程时，将此类过程提炼出来一并输出
            scene = VehicleControlScene(**scene_data)
            return scene
        except Exception as e:
            # TODO 添加错误处理
            logger.error(f"场景分析模型调用失败: {e}")
            raise e
    
    def generate_dialogue_from_scene(self, scene: VehicleControlScene, role: InCarRole) -> QAList:
        """根据车控场景和角色设定，生成对话流"""
        # 获取对话生成器的系统提示词
        dialogue_generator_profile = self.role_profiles["dialogue_generator"]
        sys_prompt = dialogue_generator_profile.system_prompt or self.default_dialogue_generator_prompt
        
        # 构建生成指令
        input_prompt = f"""请根据以下车辆控制场景和角色信息，生成多轮自然流畅的对话：
                        {to_kv_prompt(model=scene, key_source=KeySource.DESCRIPTION, value_source=ValueSource.VALUE)}
                        对话要求：
                        1. 符合智能座舱的使用场景
                        2. 对话自然流畅，符合角色设定
                        3. 包含用户发起请求、助手响应、用户确认等典型交互
                        4. 每轮对话包含用户问题和助手回答
                        5. 请返回以下JSON格式：
                        {{"qa_list": [{{"question": "用户问题", "answer": "助手回答"}}, ...]}}
                        """
        try:
            # 构建请求数据
            payload = {
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": input_prompt}
                ],
                "enable_thinking": False,
                "model": self.model,
                "hf_token": self.hf_token
            }
            
            # 发送请求到FastAPI服务
            response = requests.post(self.fastapi_url, json=payload)
            response.raise_for_status()
            
            # 解析响应数据
            result = response.json()
            
            # 提取最后一条消息的内容（模型生成的文本）
            generated_text = result['messages'][-1]['content']
            
            # 将生成的JSON文本转换为QAList对象
            dialogue_data = self.parser.safe_parse(generated_text)

            # 创建QAItem列表
            qa_items = []
            for qa_dict in dialogue_data.get("qa_list", []):
                qa_items.append(QAItem(
                    question=qa_dict["question"],
                    answer=qa_dict["answer"]
                ))
            
            # 创建QAList对象
            dialogue = QAList(qa_list=qa_items)
            return dialogue
        except Exception as e:
            # TODO 添加错误处理
            raise e
    
    def analyze_comfort_to_advice(self, car_status: dict, inside_world: dict, outside_world: dict, qa_list: QAList, role: InCarRole, knowhow_standard: dict) -> ComfortAdviceOutput:
        """分析舒适场景，生成舒适建议"""
        # 将JSON数据转换为Pydantic模型
        car_status_model = self.to_instance(car_status, "CarStatus")
        inside_world_model = self.to_instance(inside_world, "InsideWorld")
        outside_world_model = self.to_instance(outside_world, "OutsideWorld")
        knowhow_standard_model = self.to_instance(knowhow_standard, "KnowhowStandard")
        
        # 构建事件描述文本
        event_description = "\n".join([f"事件：{qa.question}\n分析：{qa.think}" for qa in qa_list.qa_list])
        
        # 获取场景分析师的系统提示词
        scene_analyst_profile = self.role_profiles["scene_analyst"]
        sys_prompt = scene_analyst_profile.system_prompt or self.default_scene_analyst_prompt
        
        # 构建分析指令
        role_info = f"""\n\n角色信息：{to_kv_prompt(model=role, key_source=KeySource.DESCRIPTION, value_source=ValueSource.VALUE) or self.DEFAULT_ROLE}"""
        # 构建舒适分析维度和原则文本
        comfort_dimensions_text = "\n".join([f"- {dim['dimension']}：{dim['description']}" for dim in knowhow_standard['comfort_dimensions']])
        comfort_principles_text = "\n".join([f"- {principle}" for principle in knowhow_standard['comfort_principles']])
        
        input_prompt = f"""请根据以下车内外环境数据、车辆状态、事件描述、角色信息和舒适分析标准，分析当前舒适性问题并生成建议：

# 车辆状态
{car_status}

# 车内环境
{inside_world}

# 车外环境
{outside_world}

# 事件描述
{event_description}

# 角色信息
{role_info}

# 舒适分析维度
{comfort_dimensions_text}

# 舒适原则
{comfort_principles_text}

请根据以上信息，按照以下步骤进行分析：
1. 结合事件描述和车内外环境，分析当前舒适性问题
2. 参考舒适分析维度和原则，生成针对性的舒适建议
3. 将分析过程和问题存入current_issue，建议结果存入suggestion
4. 请返回以下JSON格式：
{{"current_issue": "分析过程和问题", "suggestion": "建议结果"}}
"""
        
        try:
            # 构建请求数据
            payload = {
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": input_prompt}
                ],
                "enable_thinking": False,
                "model": self.model,
                "hf_token": self.hf_token,
            }
            
            # 发送请求到FastAPI服务
            response = requests.post(self.fastapi_url, json=payload)
            response.raise_for_status()
            
            # 解析响应数据
            result = response.json()
            
            # 提取最后一条消息的内容（模型生成的文本）
            generated_text = result['messages'][-1]['content']
            # 将生成的JSON文本转换为ComfortAdviceOutput对象
            advice_data = self.parser.safe_parse(generated_text)
            advice = ComfortAdviceOutput(**advice_data)
            return advice
        except Exception as e:
            # TODO 添加错误处理
            logger.error(f"舒适分析模型调用失败: {e}")
            raise e
