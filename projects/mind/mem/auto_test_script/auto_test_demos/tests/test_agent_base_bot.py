from projects.mind.mem.auto_test_script.agent_v1_eval_context import (
    USER_PROFILE,
    VEHICLE_STATE_PROMPT,
    create_params_payload,
)
from projects.mind.mem.auto_test_script.auto_test_constants import (
    MEMORY_COLLECTION_NAME,
    DEFAULT_MEMORY_USER_ID,
    MEMORY_LIMIT,
    MEMORY_TYPES,
    TEST_ASSISTANT_ID,
)
from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_auto_test import (
    AgentWithMemoryToTest,
)

def test_dump_history():

    tools = get_default_tools("123")
    little_jarvis = AgentWithMemoryToTest(tools=tools)
    result = little_jarvis.chat("你好，我叫小途，我住在浦江镇，导航去迪士尼，同时打开空调", "123")
    history = little_jarvis.dump_history()
    print(history)

def test_create():
    input_params = create_params_payload(
        tool_name=["car_control"],
        model_name="doubao-seed-1-8-251228",
        system_prompt_template=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,

        # user_profile=USER_PROFILE,
        # car_state=VEHICLE_STATE_PROMPT,

        collection_name=MEMORY_COLLECTION_NAME,
        profile_types=MEMORY_TYPES,
        profile_limit=MEMORY_LIMIT,
        user_id=DEFAULT_MEMORY_USER_ID,
        assistant_id=TEST_ASSISTANT_ID,

    )
    input_dump = input_params.model_dump()
    print(input_dump)

    extra_params = {
            "test": True,
        },
    test_agent = AgentWithMemoryToTest.create(
        context_config=input_dump,
        extra_params=extra_params,
    )

    result = test_agent.chat("你好，我叫小途，我住在浦江镇，导航去迪士尼，同时打开空调", "123")
    result = test_agent.chat("我刚刚说了什么", "123")
    history = test_agent.dump_history()
    print(history)

    # 新的session id ，是一个新的agent
    result = test_agent.chat("我刚刚说了什么", "1234")
    history = test_agent.dump_history()
    print(history)

def main():
    test_dump_history()
    test_create()

if __name__ == "__main__":
    main()