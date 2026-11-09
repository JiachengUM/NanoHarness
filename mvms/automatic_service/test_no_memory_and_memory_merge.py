#!/usr/bin/env python3
"""
记忆系统 vs 原生用户画像对比测试

使用 ChatComparer 对比两种对话模式的效果差异：
1. ChatWorker + Ground Truth User Profile (原生用户画像，完整信息一次性提供)
2. MemoryChatWorker (动态记忆系统，通过对话逐步学习用户信息)

使用方法：
    python datasets/automatic/test_no_memory_and_memory.py
"""

import sys
import asyncio
import datetime
import argparse
from pathlib import Path
from typing import Any, Generator

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from nanoai.chat.define import ChatTask, ChatAgentProfile
from nanoai.chat.simulation import gen_chat_with_nl, agen_chat_with_nl
from nanoai.chat.conversation import Conversation, ConversationInfo, conversations_to_html
from nanoai.utils.async_utils import amap, with_param_parse_async
from mvms.memory import MemoryChatWorker
from pydantic import BaseModel, Field
from nanoai.model.llm import allm_output

class ScoreResult(BaseModel):
    """单个评分维度的判定结果。与 ScoreCategory 一一对应，用于业务路由、日志与可解释分析。"""

    category: str = Field(
        ...,
        description=(
            "评分维度（取 ScoreCategory 枚举名）："
            "'PERSONALIZATION' | 'INFORMATION_USE' | 'ADVICE_QUALITY'。"
            "用于业务分流与统计，请使用英文枚举名。"
        )
    )

    score: str = Field(
        ...,
        description=(
            "该分类分数（0.0~5.0，字符串格式。"
            "如 '4.3'"
        )
    )

    reason: str = Field(
        ...,
        description=(
            "打分依据与思考过程（2~4条要点）"
        )
    )

    def get_score_as_float(self) -> float:
        """获取分数作为浮点数，由调用方处理错误"""
        return float(self.score)

    def get_score_as_int_scale(self, scale: int = 10) -> float:
        """将分数缩放到指定范围（默认0-10分制）"""
        return float(self.score) * (scale / 5.0)
import json

# 直接导入 ChatComparer 相关功能
sys.path.append(str(Path(__file__).parent.parent.parent / "examples"))
from chat_cli import gen_chat_db_dir

# 测试场景定义
SCENARIO_NAME = "旅游规划咨询"
TOPIC = "根据个人特点制定个性化旅游计划，请根据你的个性特点主动提问，让每个问题都体现你的个人特色和思考方式。"
timeout = 200
# 基础任务定义
BASE_TASK = ChatTask(
    brief="作为专业旅游规划师，为用户提供个性化的旅行建议和详细行程规划，包括目的地推荐、路线设计、预算安排、住宿建议等",
    agent_profile=ChatAgentProfile(
        name="小游",
        role="专业旅游规划师",
        language_style="热情友好，专业细致，善于根据用户特点提供个性化建议",
        persona="在与用户互动时，不会只停留在表面问题，而是会主动挖掘用户的个性特点、潜在需求和真实动机。它会结合用户的身份、偏好、习惯和表达方式，进行全面分析，再给出高度个性化、切实可行的建议。"
    )
)

# 测试用户信息
TEST_USER = """40岁的杭州工程师，常用网名 “JazzSweet40”。已婚，有一个10岁的女儿，性格幽默风趣，喜欢在日常对话中夹带玩笑，让气氛轻松。
酷爱 爵士音乐，不仅收藏黑胶唱片，还常在周末去咖啡馆听现场演出，经常会提问与音乐风格、唱片版本、器材选择有关的问题。作为一个“甜食控”，他对蛋糕、巧克力和冰淇淋有独特见解，也会主动打听杭州本地的甜品店推荐，或者好奇甜食背后的健康小知识。
摄影是他的另一大爱好，尤其擅长 城市夜景和街头人文，会在对话中提出一些摄影技巧、设备选择、甚至如何给作品配有趣文案的问题。他喜欢用朋友圈展示作品，常常希望得到既实用又有创意的建议。
生活习惯方面，他作息规律，每天 7点半起床，用一杯黑咖啡开启一天，晚上11点左右休息。因为有轻微高血压，他坚持慢跑和快走，会经常提出与健康饮食、运动节奏相关的咨询，但更偏好“温和提醒”，而不是生硬的警告。
在交流中，他的问题往往带有以下特点：好奇心驱动、技术视角、兴趣导向性、幽默调侃、实用主义、家庭氛围式
问的问题很短、不是啰嗦的人，但是直切要害。
"""

# 对话轮数
MAX_ROUNDS = 3

def gen_memory_chat_with_nl(
        task: ChatTask,
        user_info: str,
        topic: str,
        *,
        max_rounds: int = 5,
        verbose: bool = True,
        save_dir: str | None = None,
        scenario: str = "",
        batch_size: int = 2,
        enable_llm_analysis: bool = True
        ) -> tuple[MemoryChatWorker, any, Conversation]:
    """使用 MemoryChatWorker 生成对话数据，仿造 gen_chat_with_nl"""
    
    from nanoai.chat.simulation import _create_assistant_and_user, gen_chat
    
    # 创建用户
    _, user = _create_assistant_and_user(task, user_info, topic, verbose=verbose)
    
    # 创建 MemoryChatWorker 替代普通 ChatWorker
    memory_assistant = MemoryChatWorker(
        task,
        batch_size=batch_size,
        enable_llm_analysis=enable_llm_analysis
    )
    
    if verbose:
        print(f"\n记忆助手创建完成: {memory_assistant.name}")
    
    # 使用 gen_chat 进行对话，传入 MemoryChatWorker
    conversation, _ = gen_chat(
        memory_assistant, 
        user, 
        max_rounds=max_rounds, 
        verbose=verbose
    )
    
    # 保存逻辑（简化版）
    if save_dir is not None and scenario:
        from nanoai.chat.simulation import save_worker_state
        success, cache_dir = save_worker_state(memory_assistant, user, conversation, save_dir, scenario, user_info, topic)
        if success and verbose:
            print(f"保存记忆助手状态和对话记录成功: {cache_dir}")
        elif not success:
            print(f"保存到缓存失败: {cache_dir}")
    
    return memory_assistant, user, conversation

async def agen_memory_chat_with_nl(
        task: ChatTask,
        user_info: str,
        topic: str,
        *,
        max_rounds: int = 5,
        verbose: bool = True,
        save_dir: str | None = None,
        scenario: str = "",
        batch_size: int = 2,
        enable_llm_analysis: bool = True
        ) -> tuple[MemoryChatWorker, any, Conversation]:
    """异步版本的 MemoryChatWorker 对话生成，仿造 agen_chat_with_nl"""
    
    from nanoai.chat.simulation import _create_assistant_and_user, agen_chat
    
    # 创建用户（复用 simulation.py 的逻辑）
    _, user = _create_assistant_and_user(task, user_info, topic, verbose=verbose)
    
    # 创建 MemoryChatWorker 替代普通 ChatWorker
    memory_assistant = MemoryChatWorker(
        task,
        batch_size=batch_size,
        enable_llm_analysis=enable_llm_analysis
    )
    
    if verbose:
        print(f"\n记忆助手创建完成: {memory_assistant.name}")
    
    # 使用 agen_chat 进行异步对话，传入 MemoryChatWorker
    conversation, _ = await agen_chat(
        memory_assistant, 
        user, 
        max_rounds=max_rounds, 
        verbose=verbose
    )
    
    # 保存逻辑（仿造 agen_chat_with_nl）
    if save_dir is not None and scenario:
        from nanoai.chat.simulation import save_worker_state
        success, cache_dir = save_worker_state(memory_assistant, user, conversation, save_dir, scenario, user_info, topic)
        
        if success:
            if verbose:
                print(f"保存记忆助手状态和对话记录成功: {cache_dir}")
        else:
            # 错误信息总是显示，无论verbose设置
            print(f"保存到缓存失败, 错误信息: {cache_dir}")
    
    return memory_assistant, user, conversation

class MemoryComparer:
    """记忆系统对比器，复用 ChatComparer 的设计模式"""
    
    def __init__(self, max_rounds: int = MAX_ROUNDS):
        self.task = BASE_TASK
        self.user_types = [
            "Ground Truth (完整用户画像)",
            "Memory System (动态记忆系统)"
        ]
        self.user_info = TEST_USER
        self.topic = TOPIC
        self.max_rounds = max_rounds
        self.save_dir = gen_chat_db_dir("memory_comparison")
        self.scenario = "memory_vs_groundtruth"

    def params(self) -> Generator[dict[str, Any], None, None]:
        """生成参数，复用 ChatComparer.params 的模式"""
        
        # Ground Truth 参数
        yield {
            "task": self.task,
            "user_info": self.user_info,
            "topic": self.topic,
            "max_rounds": self.max_rounds,
            "verbose": False,
            "save_dir": str(self.save_dir),
            "scenario": "ground_truth",
        }
        
        # Memory System 参数  
        yield {
            "task": self.task,
            "user_info": self.user_info,
            "topic": self.topic,
            "max_rounds": self.max_rounds,
            "verbose": False,
            "save_dir": str(self.save_dir),
            "scenario": "memory_system",
            "batch_size": 1,
            "enable_llm_analysis": True
        }

    def run(self) -> None:
        
        print(f"开始记忆系统 vs 原生用户画像对比测试")
        print(f"测试时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"结果保存目录: {self.save_dir}")
        print(f"测试场景: {SCENARIO_NAME}")
        print(f"对话轮数: {self.max_rounds}")
        print(f"测试用户: 工程师（杭州）")
        
        # 准备参数列表
        params_list = list(self.params())
        
        # 使用不同的生成函数
        async def run_comparison():
            tasks = []
            
            # Ground Truth 使用标准生成函数
            gt_task = with_param_parse_async(agen_chat_with_nl)(params_list[0])
            tasks.append(gt_task)
            
            # Memory System 使用自定义生成函数
            memory_task = with_param_parse_async(agen_memory_chat_with_nl)(params_list[1])
            tasks.append(memory_task)
            
            # 并发执行
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return results
        
        # 执行对比测试
        results = asyncio.run(run_comparison())
        
        print(f"\n对话生成完成")
        
        # 处理结果，复用 ChatComparer 的结果处理逻辑
        conversations: list[tuple[Conversation, ConversationInfo]] = []
        
        for i, (res, user_type) in enumerate(zip(results, self.user_types)):
            if isinstance(res, Exception):
                print(f"{user_type} 测试失败: {res}")
                continue
                
            assistant = res[0]
            conversation = res[2]
            
            # 获取助手名称
            if hasattr(assistant, 'task') and hasattr(assistant.task, 'agent_profile'):
                assistant_name = assistant.task.agent_profile.name
            else:
                assistant_name = "助手"
            
            # 显示记忆状态（仅对 Memory System）
            if i == 1 and hasattr(assistant, 'get_memory_summary'):
                memory_summary = assistant.get_memory_summary()
                print(f"\nMemory System 最终记忆状态:")
                print(f"{'─'*60}")
                print(memory_summary)
                print(f"{'─'*60}")
                
                # 检查记忆是否为空，如果为空则显示警告
                if not memory_summary.strip() or all(block.strip() == '' for block in memory_summary.split('\n') if '<' in block and '>' in block):
                    print("  警告：记忆模块没有更新！可能的原因：")
                    print("   1. LLM API 配置缺失（OPENAI_API_KEY 等）")
                    print("   2. LLM 分析失败")
                    print("   3. 网络连接问题")
                    print("   请检查环境变量配置或查看详细错误日志")
            
            conversations.append((conversation, 
                                ConversationInfo(
                                    summary=user_type,
                                    name_a="用户",
                                    name_b=f"{assistant_name}({user_type.split()[0]})"
                                )))
        
        # 生成 HTML 对比报告，复用 ChatComparer 的 HTML 生成逻辑
        if len(conversations) >= 2:
            try:
                conversations_to_html(
                    conversations=conversations,
                    filename=str(self.save_dir / "comparison_report.html"),
                    title="记忆系统 vs 原生用户画像对比报告"
                )
                print(f"\nHTML对比报告已生成: {self.save_dir / 'comparison_report.html'}")
            except Exception as e:
                print(f"生成HTML报告失败: {e}")
            
            # 简单的统计对比
            self.print_comparison_stats(conversations)
            # 生成定量评测报告
            asyncio.run(self.evaluate_and_report(conversations))
        
        print(f"\n对比测试完成！")

    def print_comparison_stats(self, conversations: list[tuple[Conversation, ConversationInfo]]):
        """打印对比统计信息"""
        print(f"\n对话统计对比:")
        print(f"{'系统类型':<25} {'对话轮数':<10} {'平均回复长度':<15}")
        print(f"{'-'*55}")
        
        for conversation, info in conversations:
            # Conversation 是 Round 的列表，每个 Round 包含 message_a 和 message_b
            if conversation:
                # 计算平均回复长度（只计算 message_b，即助手的回复）
                avg_length = sum(len(round.message_b) for round in conversation) / len(conversation)
                print(f"{info.summary:<25} {len(conversation):<10} {avg_length:<15.1f}")
            else:
                print(f"{info.summary:<25} {'0':<10} {'0':<15}")
        
        print(f"\n观察要点:")
        print(f"  • Ground Truth 系统拥有完整用户信息，能立即提供个性化建议")
        print(f"  • Memory System 通过对话逐步学习，记忆状态会不断更新")
        print(f"  • 注意两系统在个性化程度和建议质量上的差异")

class ConvQualityScores(BaseModel):
    """对话质量评分（0-5），每个分数都有对应的理由"""
    personalization: float = Field(..., description="个性化程度", ge=0.0, le=5.0)
    personalization_reason: str = Field(..., description="个性化评分依据")
    
    information_use: float = Field(..., description="信息利用度", ge=0.0, le=5.0)
    information_use_reason: str = Field(..., description="信息利用度评分依据")
    
    advice_quality: float = Field(..., description="建议质量", ge=0.0, le=5.0)
    advice_quality_reason: str = Field(..., description="建议质量评分依据")
    
    overall: float = Field(..., description="综合评分", ge=0.0, le=5.0)
    overall_reason: str = Field(..., description="综合评分依据")

class BaseConversationEvaluator:
    """对话质量评估器基类"""
    def __init__(self, user_profile: str, scenario: str, topic: str):
        self.user_profile = user_profile
        self.scenario = scenario
        self.topic = topic
        self.use_profile = True

    def _get_base_prompt(self, conversation: Conversation, info: ConversationInfo) -> str:
        """获取基础提示词"""
        conv_text = conversation.format(name_a="用户", name_b=info.name_b)
        user_text = self.user_profile if self.use_profile else "未知"
        return f"""
场景: {self.scenario}
话题: {self.topic}
用户画像: {user_text}

对话如下:
{conv_text}
"""

class PersonalizationEvaluator(BaseConversationEvaluator):
    """个性化程度评估器"""
    
    async def __call__(self, item: tuple[Conversation, ConversationInfo]) -> ScoreResult:
        conversation, info = item
        base_prompt = self._get_base_prompt(conversation, info)
        
        prompt = f"""
你将对对话的个性化程度进行定量评估，并返回严格符合下述JSON结构的评分（仅JSON，勿包含多余字符）。

评分标准（0.0-5.0，一位小数）：
- 5.0: 完全个性化，紧扣用户画像的所有关键特征（年龄、职业、兴趣、地点、健康等）
- 4.0-4.9: 高度个性化，大部分建议都体现了用户特征
- 3.0-3.9: 中等个性化，部分建议体现了用户特征
- 2.0-2.9: 低个性化，建议较为泛化，很少体现用户特征
- 1.0-1.9: 极低个性化，建议完全泛化或模板化
- 0.0-0.9: 无个性化，建议与用户画像完全无关

评分依据要求：
- 引用具体的"用户画像要点"（至少2项）
- 说明对话中"如何体现/未体现"这些要点（各举1-2个证据短句）
- 对个性化程度的总体判断

{base_prompt}

请仅返回如下JSON（字段固定、值为0.0-5.0的字符串，保留一位小数）：
{{
  "category": "PERSONALIZATION",
  "score": "x.x",
  "reason": "..."
}}
"""
        res = await allm_output(prompt, output_type=ScoreResult)
        return res.output



class InformationUseEvaluator(BaseConversationEvaluator):
    """信息利用度评估器"""
    
    async def __call__(self, item: tuple[Conversation, ConversationInfo]) -> ScoreResult:
        conversation, info = item
        base_prompt = self._get_base_prompt(conversation, info)
        
        prompt = f"""
你将对对话的信息利用度进行定量评估，并返回严格符合下述JSON结构的评分（仅JSON，勿包含多余字符）。

评分标准（0.0-5.0，一位小数）：
- 5.0: 主动、充分、正确地调用了所有关键画像信息，无遗漏
- 4.0-4.9: 大部分关键信息被正确利用，遗漏很少
- 3.0-3.9: 部分关键信息被利用，有一定遗漏
- 2.0-2.9: 信息利用不充分，遗漏较多关键信息
- 1.0-1.9: 信息利用很少，大量关键信息被遗漏
- 0.0-0.9: 几乎未利用用户画像信息

评分依据要求：
- 列出用户画像中的"关键信息点"
- 说明对话中"如何利用/遗漏"这些信息（各举1-2个证据短句）
- 对信息利用度的总体判断

{base_prompt}

请仅返回如下JSON（字段固定、值为0.0-5.0的字符串，保留一位小数）：
{{
  "category": "INFORMATION_USE",
  "score": "x.x",
  "reason": "..."
}}
"""
        res = await allm_output(prompt, output_type=ScoreResult)
        return res.output

class AdviceQualityEvaluator(BaseConversationEvaluator):
    """建议质量评估器"""
    
    async def __call__(self, item: tuple[Conversation, ConversationInfo]) -> ScoreResult:
        conversation, info = item
        base_prompt = self._get_base_prompt(conversation, info)
        
        prompt = f"""
你将对对话的建议质量进行定量评估，并返回严格符合下述JSON结构的评分（仅JSON，勿包含多余字符）。

评分标准（0.0-5.0，一位小数）：
- 5.0: 建议非常具体、可执行、专业，包含详细的目的地/行程/预算/注意事项等
- 4.0-4.9: 建议较为具体和专业，包含大部分必要信息
- 3.0-3.9: 建议有一定具体性，但可能缺少一些重要细节
- 2.0-2.9: 建议较为空泛，具体性和可执行性不足
- 1.0-1.9: 建议很空泛，缺乏具体内容和可操作性
- 0.0-0.9: 建议完全空泛，无实际价值

评分依据要求：
- 评估建议的"具体性"（是否有具体的地点、时间、方法等）
- 评估建议的"可执行性"（是否可以直接按照建议行动）
- 评估建议的"专业性"（是否体现了专业知识和经验）
- 对建议质量的总体判断

{base_prompt}

请仅返回如下JSON（字段固定、值为0.0-5.0的字符串，保留一位小数）：
{{
  "category": "ADVICE_QUALITY",
  "score": "x.x",
  "reason": "..."
}}
"""
        res = await allm_output(prompt, output_type=ScoreResult)
        return res.output

class ConversationQualityEvaluator:
    """基于LLM的对话质量评测器（组合版本）"""
    def __init__(self, user_profile: str, scenario: str, topic: str):
        self.user_profile = user_profile
        self.scenario = scenario
        self.topic = topic
        self.use_profile = True
        
        # 创建三个独立的评估器
        self.personalization_evaluator = PersonalizationEvaluator(user_profile, scenario, topic)
        self.information_use_evaluator = InformationUseEvaluator(user_profile, scenario, topic)
        self.advice_quality_evaluator = AdviceQualityEvaluator(user_profile, scenario, topic)

    def _safe_get_score(self, result: ScoreResult) -> float:
        """安全地获取分数，带错误处理和降级策略"""
        try:
            score = result.get_score_as_float()
            # 验证分数范围
            if not (0.0 <= score <= 5.0):
                print(f"警告：分数超出范围: {score}，应在0.0-5.0之间")
                return max(0.0, min(5.0, score))  # 限制在范围内
            return score
        except (ValueError, TypeError) as e:
            print(f"警告：分数转换失败: {e}")
            print(f"原始分数值: {result.score} (类型: {type(result.score)})")
            
            # 尝试手动解析
            try:
                if isinstance(result.score, str):
                    # 尝试提取数字
                    import re
                    numbers = re.findall(r'\d+\.?\d*', result.score)
                    if numbers:
                        score_value = float(numbers[0])
                        if 0.0 <= score_value <= 5.0:
                            print(f"手动解析成功: {score_value}")
                            return score_value
                        else:
                            print(f"手动解析的分数超出范围: {score_value}")
                            return max(0.0, min(5.0, score_value))
            except Exception as parse_error:
                print(f"手动解析也失败: {parse_error}")
            
            # 降级策略：使用默认分数
            print(f"使用默认分数 2.5 作为降级分数")
            return 2.5

    def _validate_scores(self, scores: ConvQualityScores) -> bool:
        """验证分数是否有效"""
        is_valid = True
        
        # 检查分数范围
        for field_name, field_value in [
            ("personalization", scores.personalization),
            ("information_use", scores.information_use),
            ("advice_quality", scores.advice_quality),
            ("overall", scores.overall)
        ]:
            if not (0.0 <= field_value <= 5.0):
                print(f"错误：{field_name} 分数超出范围: {field_value}，应在0.0-5.0之间")
                is_valid = False
        
        # 检查综合分数是否合理（应该在各个维度分数的加权平均附近）
        expected_overall = 0.4 * scores.personalization + 0.3 * scores.information_use + 0.3 * scores.advice_quality
        if abs(scores.overall - expected_overall) > 0.5:  # 允许0.5的误差
            print(f"警告：综合分数 {scores.overall:.1f} 与计算值 {expected_overall:.1f} 差异较大")
        
        return is_valid

    async def __call__(self, item: tuple[Conversation, ConversationInfo]) -> ConvQualityScores:
        """组合三个评估器的结果"""
        # 并发执行三个评估
        personalization_result, information_use_result, advice_quality_result = await asyncio.gather(
            self.personalization_evaluator(item),
            self.information_use_evaluator(item),
            self.advice_quality_evaluator(item)
        )
        
        # 安全地转换分数为浮点数，带错误处理和降级策略
        personalization_score = self._safe_get_score(personalization_result)
        information_use_score = self._safe_get_score(information_use_result)
        advice_quality_score = self._safe_get_score(advice_quality_result)
        
        # 计算综合评分（加权平均）
        overall_score = round(0.4 * personalization_score + 0.3 * information_use_score + 0.3 * advice_quality_score, 1)
        
        # 生成综合评分依据
        overall_reason = f"""
综合评分基于以下三个维度的加权平均：
- 个性化程度({personalization_score:.1f}/5.0) × 40% = {personalization_score * 0.4:.1f}
- 信息利用度({information_use_score:.1f}/5.0) × 30% = {information_use_score * 0.3:.1f}  
- 建议质量({advice_quality_score:.1f}/5.0) × 30% = {advice_quality_score * 0.3:.1f}
总分: {overall_score:.1f}/5.0
"""
        
        # 创建评分结果
        scores = ConvQualityScores(
            personalization=personalization_score,
            personalization_reason=personalization_result.reason,
            information_use=information_use_score,
            information_use_reason=information_use_result.reason,
            advice_quality=advice_quality_score,
            advice_quality_reason=advice_quality_result.reason,
            overall=overall_score,
            overall_reason=overall_reason.strip()
        )
        
        # 验证分数有效性
        if not self._validate_scores(scores):
            print("警告：检测到无效分数，但继续处理")
        
        return scores

    @staticmethod
    def summarize(scores_a: ConvQualityScores, scores_b: ConvQualityScores) -> dict[str, Any]:
        return {
            "personalization_delta": scores_b.personalization - scores_a.personalization,
            "information_use_delta": scores_b.information_use - scores_a.information_use,
            "advice_quality_delta": scores_b.advice_quality - scores_a.advice_quality,
            "overall_delta": scores_b.overall - scores_a.overall,
        }

    @staticmethod
    def print_scores(name: str, s: ConvQualityScores) -> None:
        print(f"\n{name} 评分：")
        print(f"  个性化:     {s.personalization:.1f}/5.0")
        print(f"    理由: {s.personalization_reason}")
        print(f"  信息利用度: {s.information_use:.1f}/5.0")
        print(f"    理由: {s.information_use_reason}")
        print(f"  建议质量:   {s.advice_quality:.1f}/5.0")
        print(f"    理由: {s.advice_quality_reason}")
        print(f"  综合:       {s.overall:.1f}/5.0")
        print(f"    理由: {s.overall_reason}")

    @staticmethod
    def print_delta(delta: dict[str, Any]) -> None:
        print(f"\n差异（Memory - GroundTruth）：")
        print(f"  个性化 Δ:     {delta['personalization_delta']:+.1f}")
        print(f"  信息利用度 Δ: {delta['information_use_delta']:+.1f}")
        print(f"  建议质量 Δ:   {delta['advice_quality_delta']:+.1f}")
        print(f"  综合 Δ:       {delta['overall_delta']:+.1f}")

async def _aevaluate(evaluator: ConversationQualityEvaluator, items: list[tuple[Conversation, ConversationInfo]]):
    return await amap(evaluator.__call__, items, progress=False)

def _save_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"\n定量评测报告JSON已保存: {path}")
    except Exception as e:
        print(f"保存JSON失败: {e}")

def _pack_conv(conv: Conversation, info: ConversationInfo) -> str:
    return conv.format(name_a="用户", name_b=info.name_b)

async def evaluate_and_report(self: MemoryComparer, conversations: list[tuple[Conversation, ConversationInfo]]):
    """在 MemoryComparer 中追加：定量评测两段对话并输出报告"""
    assert len(conversations) >= 2, "需要至少两段对话进行对比"

    evaluator = ConversationQualityEvaluator(user_profile=self.user_info, scenario=SCENARIO_NAME, topic=self.topic)

    # 顺序：0 -> Ground Truth, 1 -> Memory System
    gt_item = conversations[0]
    mem_item = conversations[1]

    # 带画像评测
    evaluator.use_profile = True
    (gt_scores_list, gt_stats), (mem_scores_list, mem_stats) = await asyncio.gather(
        _aevaluate(evaluator, [gt_item]),
        _aevaluate(evaluator, [mem_item])
    )

    gt_scores: ConvQualityScores = gt_scores_list[0]
    mem_scores: ConvQualityScores = mem_scores_list[0]
    delta = ConversationQualityEvaluator.summarize(gt_scores, mem_scores)

    # 打印结果
    ConversationQualityEvaluator.print_scores("Ground Truth", gt_scores)
    ConversationQualityEvaluator.print_scores("Memory System", mem_scores)
    ConversationQualityEvaluator.print_delta(delta)

    # 保存JSON
    report = {
        "scenario": SCENARIO_NAME,
        "topic": self.topic,
        "user_profile": self.user_info,
        "ground_truth": gt_scores.model_dump(),
        "memory_system": mem_scores.model_dump(),
        "delta": delta,
        "conversation_texts": {
            "ground_truth": _pack_conv(*gt_item),
            "memory_system": _pack_conv(*mem_item),
        }
    }
    _save_json(self.save_dir / "quality_report.json", report)

# 将方法绑定到类（避免大幅改动原类结构）
setattr(MemoryComparer, "evaluate_and_report", evaluate_and_report)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="记忆系统 vs 原生用户画像对比测试")
    parser.add_argument("--max-rounds", type=int, default=MAX_ROUNDS, help=f"最大对话轮数 (默认: {MAX_ROUNDS})")
    
    args = parser.parse_args()
    
    try:
        comparer = MemoryComparer(max_rounds=args.max_rounds)
        comparer.run()
        
    except KeyboardInterrupt:
        print(f"\n测试被用户中断")
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()