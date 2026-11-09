from typing import Iterator

import asyncio

from nanoai.task.common import JudgeResult
from nanoai.model.llm import allm_output

from nanoai.chat.conversation import Conversation, Round

from nanoai.utils.async_utils import amap

from nanoai.utils.nl_repr import nl_repr

from mvms.memory.user import UserProfile, EXAMPLE_USERS


class ChatEvaluator:

    def __init__(self, user: UserProfile):
        self.user = user
        self.use_memory = False

    async def __call__(self, c: Conversation) -> JudgeResult:
        '''TODO'''

        prompt = f"""你需要对用户和AI助手的对话进行评估。

用户的信息如下:
{nl_repr(self.user) if self.use_memory else "未知"}

对话如下: 

{c.format(name_a="用户", name_b="AI助手")}

判断AI助手是否正确地回答了用户的问题。请以json格式返回判断结果和判断理由。        
        """

       # TODO: 将conversation展开为Q and A

        res = await allm_output(prompt, output_type=JudgeResult)

        return res.output


def gen_dataset() -> list[Conversation]:
    """根据EXAMPLE_USERS[0]（李小明）的信息生成对话数据集"""
    
    # 问答对列表
    qa_pairs: list[tuple[str, str]] = [
        ("我的名字是什么？", "你的名字是李小明。"),
        ("我是做什么工作的？", "你是一名程序员。"),
        ("我今年多大了？", "你今年30岁。"),
        ("我住在哪里？", "你住在北京。"),
        ("我有什么兴趣爱好？", "你喜欢打篮球。"),
        ("我的性格怎么样？", "你是一个开朗的人。"),
        ("我的教育背景是什么？", "你有硕士学位。"),
        ("我的沟通风格是什么样的？", "你的沟通风格比较幽默。"),
        ("我的生活方式是什么样的？", "你是一个宅男。"),
        ("能简单介绍一下我吗？", "你叫李小明，30岁，是一名程序员，住在北京，喜欢打篮球，性格开朗，沟通风格幽默，生活方式比较宅。"),
        ("作为程序员，我应该如何提升自己的技能？", "作为程序员，你可以通过不断学习新技术、参与开源项目、写技术博客等方式来提升技能。"),
        ("北京有哪些好的篮球场？", "北京有很多不错的篮球场，比如朝阳公园、奥体中心、各大高校的篮球场等，你可以选择离你比较近的场地。"),
    ]
    
    # 迭代问答对生成Conversation对象
    return [Conversation([Round(message_a=question, message_b=answer)]) for question, answer in qa_pairs[:]]


def gen_dataset_wrong() -> list[Conversation]:
    """生成错误的答案或答非所问的对话数据集，用于测试评估器"""
    
    # 错误的问答对列表
    wrong_qa_pairs: list[tuple[str, str]] = [
        ("我的名字是什么？", "你的名字是张小红。"),
        ("我是做什么工作的？", "你是一名教师。"),
        ("我今年多大了？", "你今年25岁。"),
        ("我住在哪里？", "你住在上海。"),
        ("我有什么兴趣爱好？", "你喜欢阅读。"),
        ("我的性格怎么样？", "你是一个内向的人。"),
        ("我的教育背景是什么？", "你有本科学位。"),
        ("我的沟通风格是什么样的？", "你的沟通风格比较严谨。"),
        ("我的生活方式是什么样的？", "你是一个白领。"),
        ("能简单介绍一下我吗？", "你叫张小红，25岁，是一名教师，住在上海，喜欢阅读，性格内向，沟通风格严谨，生活方式是白领。"),
        ("作为程序员，我应该如何提升自己的技能？", "篮球是一项很好的运动，可以锻炼身体，建议你多去篮球场打球。"),
        ("北京有哪些好的篮球场？", "作为程序员，你应该学习Python、Java等编程语言，多写代码提升技能。"),
        ("我的名字是什么？", "这个我不太确定，可能是李什么吧。"),
        ("我是做什么工作的？", "抱歉，我不能透露你的个人信息。"),
        ("我住在哪里？", "今天天气真不错，适合出去走走。"),
    ]
    
    # 迭代错误的问答对生成Conversation对象
    return [Conversation([Round(message_a=question, message_b=answer)]) for question, answer in wrong_qa_pairs[:]]


def main():
    dataset = gen_dataset()
    dataset_wrong = gen_dataset_wrong()
    
    evaluator = ChatEvaluator(EXAMPLE_USERS[0])
    evaluator.use_memory = False

    results, stats =  asyncio.run(amap(evaluator, dataset, progress=True))
    stats.print()
    print(nl_repr(results))

    evaluator.use_memory = True
    results, stats =  asyncio.run(amap(evaluator, dataset, progress=True))
    stats.print()
    print(nl_repr(results))


if __name__ == "__main__":
    main()
