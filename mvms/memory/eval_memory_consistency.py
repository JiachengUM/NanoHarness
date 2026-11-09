from __future__ import annotations

import asyncio
from typing import List, Tuple

from nanoai.task.common import JudgeResult
from nanoai.model.llm import allm_output
from nanoai.utils.async_utils import amap
from nanoai.utils.nl_repr import nl_repr

from mvms.memory.user import UserProfile as MVMSUserProfile
from mvms.memory.memory_chat_worker import MemoryChatWorker

# 使用自动服务中的用户画像生成器
from mvms.automatic_service.llm_generated_content import generate_user_profile as gen_profile_llm


class MemoryConsistencyEvaluator:
    def __init__(self, user: MVMSUserProfile):
        self.user = user
        self.use_memory = False

    async def __call__(self, _ignored: object | None = None) -> JudgeResult:
        turns = build_user_facts_conversations(self.user)
        memory_summary = extract_memory_from_conversations(turns)

        user_info_text = nl_repr(self.user) if self.use_memory else "未知"
        prompt = f"""你需要判断记忆系统抽取的用户信息是否与用户画像一致。

用户信息如下:
{user_info_text}

记忆摘要如下:
{memory_summary}

请以json格式返回判断结果和判断理由。        
        """

        res = await allm_output(prompt, output_type=JudgeResult)
        return res.output


def to_mvms_user_profile(llm_user) -> MVMSUserProfile:
    """将 llm_generated_content.UserProfile 转换为 mvms.memory.user.UserProfile。
    后者字段均为 str。
    """
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


def build_user_facts_conversations(user: MVMSUserProfile) -> List[Tuple[str, str]]:
    """根据用户画像构造若干轮对话(用户发言, 助手简短回复)。
    这些对话旨在让 MemoryManager 能从用户表述中提取事实。
    助手回复内容对提取不重要，仅充当占位。
    """
    turns: List[Tuple[str, str]] = []
    # 尽量让关键信息从“用户”口中说出
    if user.name != "未知":
        turns.append((f"我叫{user.name}。", "好的，已记录。"))
    if user.age != "未知":
        turns.append((f"我今年{user.age}岁。", "了解。"))
    if user.gender != "未知":
        turns.append((f"我是{user.gender}。", "收到。"))
    if user.occupation != "未知":
        turns.append((f"我的职业是{user.occupation}。", "记下了。"))
    if user.education != "未知":
        turns.append((f"我的教育背景是{user.education}。", "好的。"))
    if user.location != "未知":
        turns.append((f"我住在{user.location}。", "了解你的所在城市了。"))
    if user.interests != "未知":
        turns.append((f"我平时喜欢{user.interests}。", "明白了。"))
    if user.personality != "未知":
        turns.append((f"我性格{user.personality}。", "好的。"))
    if user.communication_style != "未知":
        turns.append((f"我的沟通风格比较{user.communication_style}。", "知道了。"))
    if user.lifestyle != "未知":
        turns.append((f"我的生活方式是{user.lifestyle}。", "了解。"))

    return turns[:10]


def extract_memory_from_conversations(turns: List[Tuple[str, str]]) -> str:
    """将对话对喂给 MemoryChatWorker，使其完成一次记忆分析并返回记忆摘要。"""
    # 将 batch_size 设为此次轮数，确保会触发一次 LLM 分析
    worker = MemoryChatWorker("记忆抽取任务", batch_size=max(3, len(turns)), enable_llm_analysis=True)

    for user_msg, assistant_msg in turns:
        # 直接写入对话历史，避免触发真实对话 LLM
        worker.memory_manager.add_conversation(user_msg, assistant_msg)

    # 汇总为提示文本
    return worker.get_memory_summary()


async def main_async():
    # 生成 ~5 个用户画像（不同场景以增加多样性）
    scenarios = ["音乐推荐", "美食推荐", "汽车服务", "旅游规划", "健康咨询"]
    users: List[MVMSUserProfile] = [to_mvms_user_profile(gen_profile_llm(s)) for s in scenarios]

    for i, (sc, u) in enumerate(zip(scenarios, users), 1):
        print(f"\n[{i}] 场景: {sc}")
        print(nl_repr(u))

    evaluators = [MemoryConsistencyEvaluator(u) for u in users]

    async def run_eval(e: MemoryConsistencyEvaluator) -> JudgeResult:
        return await e()

    # 1) 不使用用户画像（use_memory=False）
    for e in evaluators:
        e.use_memory = False
    results_no_mem, stats_no_mem = await amap(run_eval, evaluators, progress=True)
    stats_no_mem.print()
    print(nl_repr(results_no_mem))

    # 2) 使用用户画像（use_memory=True）
    for e in evaluators:
        e.use_memory = True
    results_with_mem, stats_with_mem = await amap(run_eval, evaluators, progress=True)
    stats_with_mem.print()
    print(nl_repr(results_with_mem))


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()


