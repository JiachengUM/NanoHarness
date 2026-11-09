import asyncio

from rich import print

from aicore.tools.experiments.goal_planner import goal_plan_tool
from aicore.models.credentials import ModelName
from aicore.agents.experiments.base import _create_agent
from aicore.events.react import ReActEventPrinter

#from aicore.agents.experiments.ralph import ralph_loop, ReActExecutor, LMEvaluator, ModelParams, RalphReActEventPrinter

# 复杂意图，细节不足，都需要澄清
QUERIES_SINGLE_GOAL = [
    # 旅游规划
    "我想带家人去旅游，找一些好玩的地方",
    "我计划去一个有特色的城市旅游，希望能有好的体验",

    # 学习教育规划
    "我想学习一门新技能，提升自己",
    "我的孩子学习成绩不好，想找办法提高",
    
    # 健康健身规划
    "我想开始健身，但是身体有些问题",
    "我想改善饮食习惯，变得更健康",
    
    # 职业工作规划
    "我想换个工作，找个更好的发展方向",
    "我想在工作中获得晋升，需要一些建议",
    
    # 个人发展/兴趣爱好规划
    "我想培养一个兴趣爱好，充实生活",
    "我想学习一项新技能，丰富自己的能力",
]

# 复杂意图，有充分的细节，不需要澄清
QUERIES_SINGLE_GOAL_COMPLETE = [
    # 旅游规划 - 详细版
    "我计划带65岁的父母在北京旅游3天，他们喜欢历史文化和自然风光，体力一般，希望每天行程不超过5小时，主要想参观故宫、颐和园和长城，预算每人每天500元左右，希望住在市中心方便出行的酒店。",
    # 学习教育规划 - 详细版
    "我是一名市场营销专业的大学生，之前没有编程经验，想从Python基础开始学习，每天可以投入2小时，目标是在3个月内掌握数据分析基础，6个月内学会使用Pandas和Matplotlib进行数据可视化，最终能开发一个简单的市场数据分析工具。",
    # 健康健身规划 - 详细版
    "我35岁，体重75kg，身高175cm，膝盖有轻微半月板损伤，医生建议避免剧烈运动，我想每周健身3次，每次1小时，目标是在6个月内降低体脂率5%，增强核心力量，希望获得适合膝盖损伤人群的低冲击运动计划和饮食建议。",
    # 职业工作规划 - 详细版
    "我是一名软件测试工程师，有3年工作经验，想转行到数据分析领域，目前会基本的Excel和SQL，计划在1年内完成Python和数据分析课程学习，考取Google数据分析师证书，希望获得具体的学习路径、推荐的课程资源和面试准备建议。",
    # 个人发展/兴趣爱好规划 - 详细版
    "我想培养摄影爱好，已购买入门级单反相机，每周可以练习2-3次，目标是在1年内掌握基本构图、光线控制和后期处理技巧，能够拍摄出专业水平的风景和人像照片，希望获得详细的学习计划、推荐的摄影书籍和练习项目。",
]

async def test_gola_plan_tool():
    plan_tool = goal_plan_tool()

    agent = _create_agent(model=ModelName.SEED_1_8_251228, tools=[plan_tool])

    #QUERIES = QUERIES_SINGLE_GOAL_COMPLETE
    QUERIES = QUERIES_SINGLE_GOAL

    for query in QUERIES:
        print("*" * 30)
        print(f"user: {query}")
        result = await agent.astream_run(query, event_listeners=[ReActEventPrinter()])
        print(f"\nassistant(完整): {result.response.raw_text}")


if __name__ == "__main__":
    asyncio.run(test_gola_plan_tool())