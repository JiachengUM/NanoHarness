#!/usr/bin/env python3
"""使用llm_output函数生成用户画像、聊天机器人描述和任务"""

import sys
import asyncio
import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from nanoai.model.llm import llm_output
from nanoai.utils.nl_repr import nl_repr
from nanoai.chat.define import ChatAgentProfile, ChatTask

# 导入 chat_cli.py 的批量处理函数
sys.path.append(str(Path(__file__).parent.parent.parent / "examples"))
from chat_cli import gen_chat_parameters
from nanoai.utils.async_utils import amap, with_param_parse_async

class Scenario:
    """简单的场景类，用于兼容chat_cli.py的接口"""
    def __init__(self, name):
        self.name = name
    
    def __str__(self):
        return self.name
    
    def __repr__(self):
        return f"Scenario('{self.name}')"
    
    def __hash__(self):
        return hash(self.name)
    
    def __eq__(self, other):
        if isinstance(other, Scenario):
            return self.name == other.name
        return False

class UserProfile(BaseModel):
    """用户画像模型"""
    name: str = Field(..., description="用户姓名")
    age: int = Field(..., description="用户年龄", ge=18, le=80)
    gender: str = Field(..., description="用户性别")
    occupation: str = Field(..., description="职业")
    education: str = Field(..., description="教育背景")
    location: str = Field(..., description="居住地")
    interests: str = Field(..., description="兴趣爱好")
    personality: str = Field(..., description="性格特点")
    communication_style: str = Field(..., description="沟通风格")
    lifestyle: str = Field(..., description="生活方式")

class ChatBotDescription(BaseModel):
    """聊天机器人描述模型"""
    name: str = Field(..., description="机器人名称")
    role: str = Field(..., description="机器人角色")
    description: str = Field(..., description="角色描述")
    expertise: str = Field(..., description="专业领域")
    persona: str = Field(..., description="人设特点")
    language_style: str = Field(..., description="语言风格")
    capabilities: List[str] = Field(..., description="能力列表")
    target_users: str = Field(..., description="目标用户群体")

class TaskInfo(BaseModel):
    """任务信息模型"""
    brief: str = Field(..., description="任务简述")
    guidelines: List[str] = Field(..., description="执行指导原则")
    detail: str = Field(..., description="任务详述")

def generate_user_profile(scenario: str, user_index: int = 0) -> UserProfile:
    """生成用户画像"""
    import random
    import time
    
    # 增加随机性，确保每次生成不同的姓名
    random.seed(time.time() + user_index * 1000)
    
    prompt = f"""
    请为"{scenario}"场景生成一个真实的用户画像。
    
    重要要求：
    1. 符合中国用户的特征
    2. 与场景相关
    3. 信息丰富且真实可信
    4. 包含所有必需字段
    5. 性格特点要真实自然，避免过于客套或正式的性格
    6. 沟通风格要直接、简洁，像真实用户一样，不要过度礼貌
    7. 生活方式要贴近普通人的日常，避免过于理想化
    8. 用户不会过度感谢或说客套话，对话风格要自然随意
    9. 用户可能会直接表达需求，不会说"太感谢了"、"非常有用"等客套话
    10. 用户不会说"再次感谢"、"祝你也有个美好的一天"、"有空再聊"、"祝你也有个好心情"、"谢谢你的介绍"、"之后有其他问题还来联系你"、"谢谢！如果有其他需要，我会再联系你"等过于客套的结束语
    11. 用户可能会简单回应"好的"、"知道了"、"行"等，不会长篇大论地感谢
    12. 用户知道自己在和AI助手对话，不会说对真人说的话，如"有空再聊"、"祝你也有个好心情"、"之后有问题再来找你"等
    13. 用户不会说"谢谢"或任何感谢的话，对话结束时只说"好的"、"知道了"即可
    14. 严格禁止：绝对不能说"谢谢"、"感谢"、"联系你"、"再找你"等任何客套话
    
    多样性要求（这是第{user_index + 1}个用户）：
    1. 请使用一个常见但不重复的姓名，避免使用"李明"、"张三"等过于常见的姓名
    2. 年龄要在22-40岁之间，但要与之前生成的用户有明显差异
    3. 职业要多样化，不要都是"软件工程师"，可以考虑产品经理、设计师、运营、销售、教师、医生、律师、创业者等不同职业
    4. 居住城市要多样化，不要都选择北京，可以考虑上海、深圳、杭州、广州、成都、武汉、西安、南京等不同城市
    5. 性格特点要多样化，可以是内向/外向、理性/感性、谨慎/冒险、专注/多面手等不同组合
    6. 兴趣爱好要与场景相关但要有个人特色，避免千篇一律
    7. 生活方式要体现不同的人生阶段和状态，比如刚毕业的年轻人、有家庭的中年人、事业有成的成功人士等
    
    请确保这个用户画像与之前生成的用户有明显差异，体现真实用户的多样性。
    """
    
    result = llm_output(
        prompt,
        output_type=UserProfile,
        strategy="auto"
    )
    
    return result.output

def generate_chatbot_description(scenario: str) -> ChatBotDescription:
    """生成聊天机器人描述"""
    prompt = f"""
    请为"{scenario}"场景设计一个专业的聊天机器人。
    要求：
    1. 角色定位清晰
    2. 专业能力突出
    3. 人设特点鲜明
    4. 语言风格适合场景
    5. 能力列表具体实用
    6. 目标用户明确
    """
    
    result = llm_output(
        prompt,
        output_type=ChatBotDescription,
        strategy="auto"
    )
    
    return result.output

def generate_task_info(scenario: str, chatbot_desc: ChatBotDescription) -> TaskInfo:
    """生成任务信息"""
    prompt = f"""
    请为"{scenario}"场景设计一个具体的任务，该任务将由以下聊天机器人执行：
    
    机器人信息：
    - 名称：{chatbot_desc.name}
    - 角色：{chatbot_desc.role}
    - 专长：{chatbot_desc.expertise}
    - 人设：{chatbot_desc.persona}
    
    要求：
    1. brief: 任务简述，要明确体现出需要帮助用户达成什么目标，不要换行
    2. guidelines: 执行指导原则列表，每条要求清晰独立，效果可量化
    3. detail: 任务详述，包含任务背景和成功标准
    """
    
    result = llm_output(
        prompt,
        output_type=TaskInfo,
        strategy="auto"
    )
    
    return result.output

def convert_to_chat_components(user_profile: UserProfile, chatbot_desc: ChatBotDescription, task_info: TaskInfo) -> tuple[ChatAgentProfile, ChatTask]:
    """转换为ChatAgentProfile和ChatTask"""
    
    # 创建ChatAgentProfile
    agent_profile = ChatAgentProfile(
        name=chatbot_desc.name,
        role=chatbot_desc.role,
        description=chatbot_desc.description,
        expertise=chatbot_desc.expertise,
        persona=chatbot_desc.persona,
        language_style=chatbot_desc.language_style
    )
    
    # 创建ChatTask
    chat_task = ChatTask(
        agent_profile=agent_profile,
        brief=task_info.brief,
        guidelines=task_info.guidelines,
        detail=task_info.detail
    )
    
    return agent_profile, chat_task

def generate_scenario_data(scenario_name: str) -> Tuple[str, List[Tuple[str, str]], ChatTask]:
    """为单个场景生成完整的数据"""
    print(f"\n{'='*60}")
    print(f"生成 {scenario_name} 场景的完整内容")
    print(f"{'='*60}")
    
    try:
        # 1. 生成用户画像
        print(f"\n1. 生成用户画像...")
        user_profile = generate_user_profile(scenario_name)
        print("用户画像生成成功")
        print(nl_repr(user_profile))
        
        # 2. 生成聊天机器人描述
        print(f"\n2. 生成聊天机器人描述...")
        chatbot_desc = generate_chatbot_description(scenario_name)
        print("聊天机器人描述生成成功")
        print(nl_repr(chatbot_desc))
        
        # 3. 生成任务信息
        print(f"\n3. 生成任务信息...")
        task_info = generate_task_info(scenario_name, chatbot_desc)
        print("任务信息生成成功")
        print(nl_repr(task_info))
        
        # 4. 转换为ChatAgentProfile和ChatTask
        print(f"\n4. 转换为ChatAgentProfile和ChatTask...")
        agent_profile, chat_task = convert_to_chat_components(user_profile, chatbot_desc, task_info)
        print("转换成功")
        
        print(f"\nChatAgentProfile:")
        print(nl_repr(agent_profile))
        
        print(f"\nChatTask:")
        print(nl_repr(chat_task))
        
        # 5. 生成用户话题组合
        print(f"\n5. 生成用户话题组合...")
        user_topic_combinations = generate_user_topic_combinations(user_profile, scenario_name)
        print(f"生成了 {len(user_topic_combinations)} 个用户话题组合")
        
        return scenario_name, user_topic_combinations, chat_task
        
    except Exception as e:
        print(f"生成 {scenario_name} 失败: {e}")
        raise

class TopicCombination(BaseModel):
    """话题组合模型"""
    topics: List[str] = Field(..., description="话题列表，每个话题都是用户可能提出的具体需求或问题，要包含具体的使用场景、时间、地点、人群等细节信息，能引发多轮对话")

def generate_user_topic_combinations(user_profile: UserProfile, scenario_name: str) -> List[Tuple[str, str]]:
    """基于用户画像和场景用LLM生成多个话题组合"""
    
    prompt = f"""
    请为"{scenario_name}"场景生成5个具体的用户话题，这些话题应该：
    
    1. 符合场景特点：{scenario_name}
    2. 适合用户画像：{user_profile.age}岁，{user_profile.gender}，{user_profile.occupation}，{user_profile.interests}，{user_profile.personality}，{user_profile.location}，{user_profile.lifestyle}
    3. 每个话题都是用户可能提出的具体需求或问题
    4. 话题要自然、真实，符合中国用户的使用习惯
    5. 话题要有一定的多样性，涵盖不同的使用场景
    6. 话题要简洁直接，避免过于客套或正式的表达
    7. 模拟真实用户的日常对话风格，语言要口语化
    8. 话题要像真实用户一样直接表达需求，不要过度礼貌或客套
    9. 可以包含一些日常化的表达，比如"有什么好的"、"推荐一下"等
    10. 用户不会说"太感谢了"、"非常有用"、"再次感谢"等客套话
    11. 用户可能会直接说"好的"、"知道了"、"行"等简单回应
    12. 话题要具体明确，包含具体的使用场景、时间、地点、人群等信息
    13. 话题要能引发多轮对话，不只是简单的问答
    14. 话题要贴近用户的实际生活需求，避免过于理想化
    15. 话题要包含一些细节，让对话更丰富有趣
    
    请生成5个话题，每个话题用一句话描述用户的需求。
    """
    
    result = llm_output(
        prompt,
        output_type=TopicCombination,
        strategy="auto"
    )
    
    topics = result.output.topics
    
    # 将用户画像转换为字符串格式，并添加对话风格要求
    user_profile_str = f"{user_profile.age}岁，{user_profile.gender}，{user_profile.occupation}，{user_profile.interests}，{user_profile.personality}，{user_profile.location}，{user_profile.lifestyle}。对话行为：直接简洁，不会过度感谢或说客套话，不会说'太感谢了'、'再次感谢'、'祝你也有个美好的一天'、'有空再聊'、'祝你也有个好心情'、'谢谢你的介绍'、'之后有其他问题还来联系你'、'之后有问题再来找你'、'谢谢！如果有其他需要，我会再联系你'等客套话。多轮对话中会简单回应'好的'、'知道了'、'行'等，不会长篇大论地感谢。对话示例：当获得推荐后，会说'好的，我去试试'或'知道了'，而不是'太感谢你了，这些信息非常有用'等客套话。重要：你是在和一个AI助手对话，不是真人，所以不会说'有空再聊'、'祝你也有个好心情'、'之后有问题再来找你'等对真人说的话。对话结束时，简单说'好的'、'知道了'即可，不会说'谢谢'或任何客套的结束语。严格禁止：绝对不能说'谢谢'、'感谢'、'联系你'、'再找你'等任何客套话。"
    
    # 生成用户话题组合
    combinations = []
    for topic in topics:
        combinations.append((user_profile_str, topic))
    
    return combinations

async def generate_scenario_data_async(scenario_name: str) -> Tuple[str, List[Tuple[str, str]], ChatTask]:
    """异步版本：为单个场景生成完整的数据"""
    print(f"\n{'='*60}")
    print(f"生成 {scenario_name} 场景的完整内容")
    print(f"{'='*60}")
    
    try:
        # 并行生成用户画像、聊天机器人描述和任务信息
        print(f"\n并行生成 {scenario_name} 场景的核心内容...")
        
        # 创建异步任务
        import asyncio
        user_profile_task = asyncio.create_task(
            asyncio.to_thread(generate_user_profile, scenario_name)
        )
        chatbot_desc_task = asyncio.create_task(
            asyncio.to_thread(generate_chatbot_description, scenario_name)
        )
        
        # 等待前两个任务完成
        user_profile, chatbot_desc = await asyncio.gather(user_profile_task, chatbot_desc_task)
        
        print("用户画像和聊天机器人描述生成成功")
        print(nl_repr(user_profile))
        print(nl_repr(chatbot_desc))
        
        # 生成任务信息（依赖聊天机器人描述）
        print(f"\n生成任务信息...")
        task_info = await asyncio.to_thread(generate_task_info, scenario_name, chatbot_desc)
        print("任务信息生成成功")
        print(nl_repr(task_info))
        
        # 转换为ChatAgentProfile和ChatTask
        print(f"\n转换为ChatAgentProfile和ChatTask...")
        agent_profile, chat_task = await asyncio.to_thread(
            convert_to_chat_components, user_profile, chatbot_desc, task_info
        )
        print("转换成功")
        
        print(f"\nChatAgentProfile:")
        print(nl_repr(agent_profile))
        
        print(f"\nChatTask:")
        print(nl_repr(chat_task))
        
        # 生成用户话题组合
        print(f"\n生成用户话题组合...")
        user_topic_combinations = await asyncio.to_thread(
            generate_user_topic_combinations, user_profile, scenario_name
        )
        print(f"生成了 {len(user_topic_combinations)} 个用户话题组合")
        
        return scenario_name, user_topic_combinations, chat_task
        
    except Exception as e:
        print(f"生成 {scenario_name} 失败: {e}")
        raise

async def generate_and_run_conversations():
    """生成内容并运行对话"""
    scenarios = ["音乐推荐", "美食推荐", "汽车服务"]
    
    # 并行生成所有场景的数据
    print(f"\n{'='*60}")
    print(f"开始并行生成所有场景数据")
    print(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    # 创建所有场景的异步任务
    scenario_tasks = [
        generate_scenario_data_async(scenario_name) 
        for scenario_name in scenarios
    ]
    
    # 并行执行所有场景的数据生成
    scenario_results = await asyncio.gather(*scenario_tasks)
    
    # 整理结果
    all_scenarios = []
    all_users = {}
    all_tasks = {}
    
    for scenario_name, user_combinations, chat_task in scenario_results:
        scenario_obj = Scenario(scenario_name)
        all_scenarios.append(scenario_obj)
        all_users[scenario_obj] = user_combinations
        all_tasks[scenario_obj] = chat_task
    
    # 为本次对话生成带时间戳的保存目录
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_save_dir = Path("generated_conversations") / f"llm_generated_{timestamp}"
    
    print(f"\n{'='*60}")
    print(f"开始批量对话生成")
    print(f"时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"保存目录: {timestamped_save_dir}")
    print(f"最大轮数: 5")
    print(f"最大并发数: 3")
    print(f"{'='*60}\n")
    
    # 生成参数列表
    parameters_list = gen_chat_parameters(
        scenarios=all_scenarios,
        USERS=all_users,
        TASKS=all_tasks,
        save_dir=str(timestamped_save_dir),
        max_rounds=5,
        verbose=False,
        language_style="语言简洁。",
    )
    
    # 使用异步执行
    from nanoai.chat.simulation import agen_chat_with_nl
    results, stats = await amap(
        with_param_parse_async(agen_chat_with_nl),
        parameters_list,
        max_concurrent=3
    )
    
    print(f"\n{'='*60}")
    print(f"生成完成！")
    print(f"结果: {len(results)} 个对话生成完成")
    print(f"保存位置: {timestamped_save_dir}")
    print(f"{'='*60}")
    
    return results, stats

def main():
    """主函数"""
    # 运行异步对话生成
    asyncio.run(generate_and_run_conversations())

if __name__ == "__main__":
    main()
