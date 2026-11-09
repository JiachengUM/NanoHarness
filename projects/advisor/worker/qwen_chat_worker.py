from typing import Optional, Type, TypeVar

# 泛型类型变量
typing_T = TypeVar('T')
from nanoai.model.qwen_llm import qwen, qwen_output, QwenRunResult
from cabin_advisor.define.scenario import QAList, VehicleControlScene, InCarRole
from cabin_advisor.define.role import COMFORT_ADVISOR_PROFILES

class QwenChatWorker:
    """Qwen模型的ChatWorker适配类，用于智能座舱舒适场景分析和对话生成"""
    
    def __init__(self, model: Optional[str] = None, client: Optional[object] = None, role_profile_name: str = "scene_analyst"):
        """初始化QwenChatWorker
        
        Args:
            model: 模型名称，默认使用Qwen3-0.6B
            client: OpenAI客户端实例（兼容Qwen API）
            role_profile_name: 角色配置名称，用于获取系统提示词
        """
        self.model = model
        self.role_profile_name = role_profile_name
        self.role_profile = COMFORT_ADVISOR_PROFILES.get(role_profile_name, {})
        
        # 设置默认系统提示词
        if hasattr(self.role_profile, 'system_prompt'):
            self.system_prompt = self.role_profile.system_prompt
        else:
            # 默认系统提示词
            if role_profile_name == "scene_analyst":
                self.system_prompt = "你是一位智能座舱场景分析专家，擅长从对话数据中分析用户需求，识别具体的舒适场景，并转化为可执行的车控指令。"
            elif role_profile_name == "dialogue_generator":
                self.system_prompt = "你是一位智能座舱对话生成专家，能够根据车控场景描述和角色设定，生成自然流畅的对话流，模拟真实的用户与系统交互过程。"
            else:
                self.system_prompt = "你是一位智能座舱助手，能够帮助用户处理各种舒适场景需求。"
        
        # 初始化客户端
        self.client = client
    
    def execute(self, prompt: str, output_type: Optional[Type[typing_T]] = None) -> typing_T:
        """执行Qwen模型调用，返回生成结果
        
        Args:
            prompt: 输入提示词
            output_type: 输出类型，如果提供则使用结构化输出
            
        Returns:
            生成的结果，类型由output_type指定
        """
        if output_type is not None:
            # 使用结构化输出
            result: QwenRunResult = qwen_output(
                prompt,
                self.system_prompt,
                output_type=output_type,
                client=self.client,
                model=self.model,
                apply_chat_template=True,
                enable_thinking=False
            )
            return result.output
        else:
            # 使用普通文本输出
            result: QwenRunResult = qwen(
                prompt,
                self.system_prompt,
                client=self.client,
                model=self.model,
                apply_chat_template=True,
                enable_thinking=False
            )
            return result.output
    
    def analyze_dialogue_to_scene(self, qa_list: QAList, output_type: Type[VehicleControlScene]) -> VehicleControlScene:
        """分析对话数据，输出车控场景
        
        Args:
            qa_list: 对话列表
            output_type: 输出类型，必须是VehicleControlScene
            
        Returns:
            车控场景对象
        """
        # 构建输入文本
        dialogue_text = "\n".join([f"用户: {qa.question}\n系统: {qa.answer}" for qa in qa_list.qa_list])
        
        # 构建分析指令
        prompt = f"""请分析以下对话，确定对应的车辆控制场景：
{dialogue_text}

请返回包含以下信息的JSON：
- scenario_type: 场景类型，必须从["温度调节场景", "座椅调节场景", "灯光场景", "音频控制场景", "空气质量场景", "多模式组合场景"]中选择
- parameters: 场景参数，根据场景类型提供相应的参数
- description: 场景描述
- target_role: 目标角色，如"驾驶员"或"乘客"

示例输出：
{{"scenario_type": "温度调节场景", "parameters": {{"temperature": 22, "mode": "auto"}}, "description": "用户需要温度调节，建议设置为22°C自动模式", "target_role": "驾驶员"}}
"""
        
        # 执行场景分析
        return self.execute(prompt, output_type=output_type)
    
    def generate_dialogue_from_scene(self, scene: VehicleControlScene, role: InCarRole, output_type: Type[QAList]) -> QAList:
        """根据车控场景和角色设定，生成对话流
        
        Args:
            scene: 车控场景
            role: 车内角色
            output_type: 输出类型，必须是QAList
            
        Returns:
            对话列表对象
        """
        # 构建生成指令
        prompt = f"""请根据以下车辆控制场景和角色信息，生成多轮自然流畅的对话：

场景类型：{scene.scenario_type}
场景参数：{scene.parameters}
场景描述：{scene.description}
目标角色：{scene.target_role}

角色信息：
- 姓名：{role.name}
- 类型：{role.type}
- 偏好：{role.preferences}

对话要求：
1. 符合智能座舱的使用场景
2. 对话自然流畅，符合角色设定
3. 包含用户发起请求、助手响应、用户确认等典型交互
4. 每轮对话包含用户问题和助手回答
5. 请返回以下JSON格式，确保qa_list数组包含3个元素：
{{"qa_list": [{{"question": "用户问题", "answer": "助手回答"}}, ...]}}
"""
        
        # 执行对话生成
        return self.execute(prompt, output_type=output_type)
