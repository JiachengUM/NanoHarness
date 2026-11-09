from __future__ import annotations

import asyncio
from typing import List, Tuple

from nanoai.task.common import JudgeResult
from nanoai.model.llm import allm
from nanoai.utils.async_utils import amap
from nanoai.utils.nl_repr import nl_repr
from nanoai.task.common import acompare_judge

from mvms.memory.user import UserProfile as MVMSUserProfile
from mvms.memory.memory_chat_worker import MemoryChatWorker

# 使用自动服务中的用户画像生成器
from mvms.automatic_service.llm_generated_content import generate_user_profile as gen_profile_llm


class MemoryVsGroundTruthEvaluator:
    """记忆系统与Ground Truth对比评估器"""
    
    def __init__(self, user_profile: MVMSUserProfile, scenario: str):
        self.user_profile = user_profile
        self.scenario = scenario
    
    async def __call__(self, _ignored: object | None = None) -> JudgeResult:
        """执行评估：生成对话，提取记忆，与Ground Truth比较"""
        
        # 1. 用LLM生成对话轮次
        turns = await self._generate_conversation_with_llm()
        
        # 2. 用MemoryChatWorker处理对话并提取记忆
        memory_summary, user_facts = self._extract_memory_from_conversations(turns)
        
        # 3. 与Ground Truth比较
        ground_truth_text = nl_repr(self.user_profile)
        action = "判断记忆系统提取的用户信息是否与Ground Truth用户画像一致，并给出理由"
        result = await acompare_judge(user_facts, ground_truth_text, action)
        
        # 4. 打印详细信息
        print(f"\n=== 场景: {self.scenario} ===")
        print(f"\nGround Truth 用户画像:")
        print(ground_truth_text)
        print(f"\nMemory Blocks:")
        print(memory_summary)
        print(f"\n提取的 user_facts:")
        print(user_facts)
        print(f"\n一致性判断: {result.judgment}")
        print(f"判断理由: {result.reason}")
        
        return result
    
    async def _generate_conversation_with_llm(self) -> List[Tuple[str, str]]:
        """使用LLM生成与用户画像相关的自然对话"""
        user_info = nl_repr(self.user_profile)
        
        prompt = f"""请根据以下用户画像和场景，生成一段自然的对话，让用户自然地透露自己的信息。

场景: {self.scenario}
用户画像: {user_info}

要求:
1. 生成4-6轮对话
2. 用户应该自然地透露自己的基本信息（姓名、年龄、职业、居住地等）
3. 对话要符合场景，用户会咨询相关问题
4. 助手的回复要简洁友好
5. 每轮对话格式: "用户: xxx\n助手: xxx"

请直接输出对话内容，不要其他解释。"""

        try:
            response = await allm(prompt)
            conversation_text = response.output.strip()
        except Exception as e:
            print(f"LLM生成对话失败: {e}")
            # 回退到简单的硬编码对话
            return self._fallback_conversation()
        
        # 解析对话
        turns = []
        lines = conversation_text.split('\n')
        current_user_msg = ""
        current_assistant_msg = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith("用户:"):
                if current_user_msg and current_assistant_msg:
                    turns.append((current_user_msg, current_assistant_msg))
                current_user_msg = line[3:].strip()
                current_assistant_msg = ""
            elif line.startswith("助手:"):
                current_assistant_msg = line[3:].strip()
        
        # 添加最后一轮对话
        if current_user_msg and current_assistant_msg:
            turns.append((current_user_msg, current_assistant_msg))
        
        return turns
    
        
    def _extract_memory_from_conversations(self, turns: List[Tuple[str, str]]) -> Tuple[str, str]:
        """用MemoryChatWorker处理对话并提取记忆"""
        # 创建MemoryChatWorker
        worker = MemoryChatWorker(
            "用户信息收集助手", 
            batch_size=max(3, len(turns)), 
            enable_llm_analysis=True
        )
        
        # 处理对话
        for user_msg, assistant_msg in turns:
            worker.memory_manager.add_conversation(user_msg, assistant_msg)
        
        # 获取记忆摘要和user_facts
        memory_summary = worker.get_memory_summary()
        user_facts_block = worker.core_memory.get_block('user_facts')
        user_facts = user_facts_block.value if user_facts_block else ""
        
        return memory_summary, user_facts


def to_mvms_user_profile(llm_user) -> MVMSUserProfile:
    """将 llm_generated_content.UserProfile 转换为 mvms.memory.user.UserProfile"""
    return MVMSUserProfile(
        name=str(getattr(llm_user, "name", "未知")),
        age=str(getattr(llm_user, "age", "未知")),
        gender=str(getattr(llm_user, "gender", "未知")),
        occupation=str(getattr(llm_user, "occupation", "未知")),
        education=str(getattr(llm_user, "education", "未知")),
        location=str(getattr(llm_user, "location", "未知")),
        interests=str(getattr(llm_user, "interests", "未知")),
        personality=str(getattr(llm_user, "personality", "未知")),
        communication_style=str(getattr(llm_user, "communication_style", "未知")),
        lifestyle=str(getattr(llm_user, "lifestyle", "未知")),
    )


async def main_async():
    # 生成用户画像
    scenarios = ["音乐推荐", "美食推荐", "旅游规划"]
    users: List[MVMSUserProfile] = [to_mvms_user_profile(gen_profile_llm(s, i)) for i, s in enumerate(scenarios)]
    
    print("=== 生成的用户画像 ===")
    for i, (scenario, user) in enumerate(zip(scenarios, users), 1):
        print(f"\n[{i}] 场景: {scenario}")
        print(nl_repr(user))
    
    # 创建评估器
    evaluators = [MemoryVsGroundTruthEvaluator(user, scenario) for user, scenario in zip(users, scenarios)]
    
    # 执行评估
    print("\n=== 开始评估 ===")
    
    async def run_eval(evaluator: MemoryVsGroundTruthEvaluator) -> JudgeResult:
        return await evaluator()
    
    results, stats = await amap(run_eval, evaluators, progress=True)
    stats.print()
    
    # 统计结果
    print(f"\n=== 评估结果统计 ===")
    valid_results = [r for r in results if hasattr(r, 'judgment')]
    correct_count = sum(1 for r in valid_results if r.judgment == True)
    total_count = len(valid_results)
    
    if total_count > 0:
        print(f"一致性判断正确: {correct_count}/{total_count} ({correct_count/total_count*100:.1f}%)")
        
        for i, (result, scenario) in enumerate(zip(valid_results, scenarios[:len(valid_results)])):
            print(f"\n场景 {i+1} ({scenario}): {result.judgment} - {result.reason}")
    else:
        print("没有有效的评估结果")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()