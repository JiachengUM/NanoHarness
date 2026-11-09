import asyncio

from nanoai.model.config import ModelName
from nanoai.chat.define import ROLE_PLAY_AGENT_PROFILES, RolePlayScenario
from nanoai.chat.simulation import agen_chat

from projects.uiagent.utils.chat_agent import ChatAgentState, ChatAgentProfile, ChatAgent, SimulatedChatUser


agent_xiaotu = ChatAgentProfile(
    name="小途",
    role="旅行规划师",
    description="小途是一位旅行规划师，擅长根据用户的需求提供个性化的旅行建议。",
    expertise="熟悉国内外各大旅游景点，了解各类旅行方式和预算安排，擅长制定安全、舒适的旅行计划。",
    persona="热情周到，善于倾听，能根据用户的需求提供个性化的旅行建议。",
    language_style="亲切友好，表达清晰准确，能够生动形象地描绘旅行的魅力。"
)


def test_state():
    print("测试ChatAgentState")
    agent = ChatAgent(agent_xiaotu, ModelName.DOUBAO_SEED_1_6_FLASH_250828, task="随便聊聊")

    # 可以随便调用一次 .execute 以改变状态，更真实模拟
    response = asyncio.run(agent.aexecute("你好，你是谁？"))
    print(response)

    state_dict = agent.save_state()

    state_restored = ChatAgentState.model_validate(state_dict)

    # 检查是否相等。可以比对重要字段，比如 ._result（如有）、.save_state() 内容
    assert agent.state == state_restored, "加载后的state与保存前不一致"


async def test_chat_agent():
    print("测试ChatAgent")
    
    agent = ChatAgent(
        agent_xiaotu, 
        ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        intent_cls_strategy = "light",
        )

    user_message = "你好。你对于我了解多少?"

    # 此时模型并不知道用户是谁
    print(f"user: {user_message}")
    try:
        res = await agent.aexecute(user_message)
        print(f"assistant: {res}")
        print(f"status: {agent.status_full}")
    except Exception as e:
        print(f"Error: {e}")

    user_message = "我叫小明。你现在了解我了么？"
    print(f"user: {user_message}")
    try:
        print(f"assistant(async stream):", end="", flush=True)
        async with agent.aexecute_stream(user_message, delta=True) as result_stream:
            async for chunk in result_stream:
                print(chunk, end="")
                
        print(f"\nstatus: {agent.status_full}")
    except Exception as e:
        print(f"Error: {e}")

    # 测试更新用户
    user = "男，20岁，学生，喜欢爬山。"
    agent.update_user(user)

    user_message = "再说说你对我的了解。并推荐旅游地点。"
    print(f"user: {user_message}")
    try:
        print(f"assistant(async stream):", end="", flush=True)
        async with agent.aexecute_stream(user_message, delta=True) as result_stream:
            async for chunk in result_stream:
                print(chunk, end="")
                
        print(f"\nstatus: {agent.status_full}")
    except Exception as e:
        print(f"Error: {e}")

    # 测试特殊的退出msg
    user_message = "再见"
    print(f"user: {user_message}")
    try:
        res = await agent.aexecute(user_message)
        print(f"assistant: {res}")
        print(f"status: {agent.status_full}")

    except Exception as e:
        print(f"Error: {e}")


scenario_and_messages = [
    (RolePlayScenario.Huafei, [
        "你好，华妃姐姐. 我是甄嬛, 想请教在后宫的生存之道",
        "你对其她姐妹的看法如何",
        "你觉得皇上喜欢你么",
    ]),
    (RolePlayScenario.Wukong, [
        "你好，孙悟空。我叫团团，今年5岁，很喜欢西游记。",
        "81难中最难的是那几难？",
    ]),
]


def test_mocked_user(scenario: RolePlayScenario, messages: list[str]):
    assistant = ChatAgent(
        ROLE_PLAY_AGENT_PROFILES[scenario], 
        ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        task=scenario.value)

    try:
        asyncio.run(agen_chat(assistant, messages, max_rounds=len(messages)))
    except Exception as e:
        print(f"Error: {e}")


scenario_and_user = [
    (RolePlayScenario.Huafei, "甄嬛", "甄嬛", None),
    (RolePlayScenario.Huafei, "小美", "25岁宅女, 甄嬛传的粉丝，对于后宫八卦很感兴趣", "讨论华妃和皇上的感情"),
    (RolePlayScenario.Wukong, "猪八戒", "猪八戒", "人参果好吃么"),
    (RolePlayScenario.Wukong, "团团", "5岁小女孩, 很喜欢西游记", None),
]

def test_simulated_user(scenario: RolePlayScenario, user_name: str, user_desc: str, topic: str | None):

    # model = ModelName.DOUBAO_SEED_1_6_251015

    model = ModelName.DOUBAO_SEED_1_6_FLASH_250828

    # intent_cls_strategy = "none"
    # intent_cls_strategy = "light"
    intent_cls_strategy = "heavy"

    assistant = ChatAgent(
        ROLE_PLAY_AGENT_PROFILES[scenario], 
        model,
        task = scenario.value,
        intent_cls_strategy = intent_cls_strategy,
        )

    user = SimulatedChatUser(
        user_name,
        user_desc,
        topic = topic,
        model = model,
        intent_cls_strategy = intent_cls_strategy,
        )

    #print(user._sys_prompt)
    #return

    try:
        asyncio.run(agen_chat(assistant, user, max_rounds=3))
    except Exception as e:
        print(f"Error: {e}")
    

def main():
    # test_state()
    asyncio.run(test_chat_agent())

    #test_mocked_user(*scenario_and_messages[0])
    #test_mocked_user(*scenario_and_messages[1])
    #test_simulated_user(*scenario_and_user[0])
    #test_simulated_user(*scenario_and_user[1])
    #test_simulated_user(*scenario_and_user[2])
    #test_simulated_user(*scenario_and_user[3])


if __name__ == "__main__":
    main()