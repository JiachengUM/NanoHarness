"""
命令行对话应用演示

演示如何使用NanoAI框架创建命令行对话应用。
用户可以输入任务描述，系统会自动生成AI助手和模拟用户，然后开始对话。

使用方法：python examples/chat_cli.py
"""

import asyncio
import datetime
from pathlib import Path
from typing import Any, Generator

from nanoai.utils.async_utils import map, amap, with_param_parse, with_param_parse_async
from nanoai.chat.define import (
    ChatScenario, 
    RolePlayScenario,  
    CHAT_SCENARIO_TASKS, 
    ROLE_PLAY_TASKS,
    CHAT_DB_DIR,
)
from nanoai.chat.worker import ChatWorker
from nanoai.chat.conversation import Conversation, ConversationInfo, conversations_to_html

from nanoai.chat.simulation import (
    ChatTask, 
    ChatAgentProfile, 
    gen_chat_with_nl, 
    agen_chat_with_nl,
)

CHAT_TASKS_AND_USERS: dict[str, list[tuple[str, str]]] = {
    ChatScenario.TravelPlanning: [
        ("热爱生活但有点懒的宝妈", "带宝宝出游的注意事项"),
        ("60岁退休老人，想要出国旅游", "欧洲自由行攻略和注意事项")
        ],
    ChatScenario.PopCultureRecommendation: [
        ("IT宅男", "最近比较流行的音乐"),
        ("25岁女性白领，喜欢追剧", "最近好看的电视剧和电影推荐")
        ],
    ChatScenario.CareerConsulation: [
        ("传统前后端开发工程师，中年，有职业危机感。", "如何转型智能体开发工程师"),
        ("25岁刚毕业的职场新人，工作压力大", "如何应对职场焦虑，内卷，pua等")
        ],
    ChatScenario.EducationConsultation: [
        ("小学三年级女生，性格害羞，说话紧张。", "如何提高表达能力"),
        ("20岁大学生，英语基础薄弱", "提高英语口语")
        ],
    ChatScenario.MedicalConsultation: [
        ("40多岁的中年程序员", "脱发"),
        ("30岁女性上班族，经常熬夜加班", "颈椎病和腰椎间盘突出")
        ],
}


ROLE_PLAY_TASKS_AND_USERS: dict[str, list[tuple[str, str]]] = {
    RolePlayScenario.Wukong: [
        ("5岁小女孩，顽皮，好奇", "刚接触西游记，很感兴趣"),
        ("猪八戒", "关于吃人参果的对话"),
        ],
    RolePlayScenario.Elsa: [
        ("8岁小女孩，喜欢公主故事", "想了解冰雪魔法的秘密"),
        ("安娜公主", "关于姐妹情深的对话"),
        ],
    RolePlayScenario.ZhuGeLiang: [
        ("历史爱好者，对三国很感兴趣", "请教诸葛亮的军事策略"),
        ("刘备", "关于三顾茅庐的对话"),
        ],
    RolePlayScenario.Huafei: [
        ("25岁宅女", "甄嬛传的粉丝，对于后宫八卦很感兴趣"),
        ("刚入宫时的甄嬛", "后宫妃子之间的关系，和皇上的八卦等等"),
        ],
    RolePlayScenario.Elon: [
        ("科技爱好者，对太空探索感兴趣", "讨论火星殖民计划"),
        ("特斯拉车主", "关于电动汽车未来的对话"),
        ],
}


def gen_chat_parameters(
        scenarios,
        USERS: dict[str, list[tuple[str, str]]],
        TASKS: dict[str, Any],
        save_dir: str,
        max_rounds: int = 5,
        verbose: bool = False,
        language_style: str | None = None,
    ) -> list[dict[str, Any]]:

    param_list = []
    
    for scenario in scenarios:
        users = USERS[scenario]

        # if gen_task:
        #     assert isinstance(task_desc, str), "当gen_task为True时，task_desc必须为str"
        #     # 当需要生成任务时，使用 AI 生成
        #     try:
        #         if verbose:
        #             print("🔄 正在生成任务定义...")
        #         task = generate_chat_task(task_desc)
        #         if verbose:
        #             print(f"\n✅ 自动生成任务详情:\n{nl_repr(task)}")
        #     except Exception as e:
        #         print(f"生成任务定义失败: {e}, 使用默认助手")
        #         task = ChatTask(brief=task_desc, agent_profile=ChatAgentProfile(name="助手", role="助手"))
        
        task = TASKS[scenario]
        
        if language_style is not None:
            task.agent_profile.language_style += "\n" + language_style

        for i, (user_info, topic) in enumerate(users):
            param_list.append({
                "task": task,
                "user_info": user_info,
                "topic": topic,
                "max_rounds": max_rounds,
                "verbose": verbose,
                "save_dir": save_dir,
                "scenario": scenario.name,
            })
    
    return param_list


def gen_chat_db_dir(tag: str) -> Path:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"{CHAT_DB_DIR}") / f"chat_{timestamp}_{tag}"


def gen_chat_batch():
    if True:
        # 使用ChatScenario
        # scenarios = ChatScenario
        scenarios = [ChatScenario.TravelPlanning]
        USERS = CHAT_TASKS_AND_USERS
        TASKS = CHAT_SCENARIO_TASKS

        DATA_TAG = "chat_scenario"
    else:
        # 使用RolePlayScenario
        scenarios = RolePlayScenario
        USERS = ROLE_PLAY_TASKS_AND_USERS
        TASKS = ROLE_PLAY_TASKS

        DATA_TAG = "role_play"

    # 为本次对话生成带时间戳的保存目录
    timestamped_save_dir = gen_chat_db_dir(DATA_TAG)
    
    max_rounds = 2 # 测试
    # max_rounds = 5 # 生成长对话
    language_style = "语言简洁。"  # 在这里控制对话的风格
    
    use_async = True
    max_concurrent = 10
    verbose = False
    
    print(f"🚀 开始批量对话生成测试")
    print(f"📁 保存目录: {timestamped_save_dir}")
    if use_async:
        print(f"⚡ 最大并发数: {max_concurrent}")
    
    # 生成参数列表
    parameters_list = gen_chat_parameters(
        scenarios=scenarios,
        USERS=USERS,
        TASKS=TASKS,
        save_dir=str(timestamped_save_dir),
        max_rounds=max_rounds,
        verbose=verbose,
        language_style=language_style,
    )
    
    # 生成对话
    if use_async:
        results, stats = asyncio.run(amap(
            with_param_parse_async(agen_chat_with_nl),
            parameters_list,
            max_concurrent=max_concurrent,
        ))
    else:
        results, stats = map(
            with_param_parse(gen_chat_with_nl),
            parameters_list
        )
    
    print(f"\n📊 执行完成，最终统计结果:")
    stats.print()
    print(f"✅ 所有测试完成！结果已保存到: {timestamped_save_dir}")


class ChatComparer:
    def __init__(self):
        self.task = ChatTask(brief="为用户做旅游规划", agent_profile=ChatAgentProfile(name="助手1", role="助手"))
        self.user = ["30岁女性上班族, 经常熬夜加班, 比较文艺",
                     "40岁中年码农, 有两个孩子, 工作压力大"]
        self.topic = "利用周末短暂的时间北京周边游"
        self.max_rounds = 2
        self.save_dir = gen_chat_db_dir("chat_compare_example")
        self.scenario = "travel_plan"

    def params(self) -> Generator[dict[str, Any], None, None]:
        # TODO: 

        for u in self.user:
            yield {
                "task": self.task,
                "user_info": u,
                "topic": self.topic,
                "max_rounds": self.max_rounds,
                "verbose": False,
                "save_dir": self.save_dir,
                "scenario": self.scenario,
            }

    def run(self) -> None:
        results, stats = asyncio.run(amap(
            with_param_parse_async(agen_chat_with_nl),
            self.params(),
            max_concurrent=5,
        ))
        stats.print()

        conversations: list[tuple[Conversation, ConversationInfo]] = [] 
        for res, u in zip(results, self.user):
            # TODO: 这里的self.user可以改成通用的self.conv_summary: Iterator[str]
            assert res is not Exception, "任务执行失败"

            assistant = res[0]
            assert isinstance(assistant, ChatWorker), "助手必须是ChatWorker"
            assistant_name = assistant.task.agent_profile.name
            
            conversations.append((res[2], 
                                  ConversationInfo(summary=u,
                                                    name_a="",
                                                    name_b=assistant_name)))
            
        try:
            conversations_to_html(
                conversations=conversations,
                filename=str(self.save_dir / "conversations.html"),
                title="不同用户做同样的旅游规划"
                )
            print(f"生成comparison HTML文件: {self.save_dir / 'conversations.html'}")
        except Exception as e:
            print(f"生成HTML文件失败: {e}")


if __name__ == "__main__":
    # gen_chat_batch()
    
    ChatComparer().run()
