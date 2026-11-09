import asyncio

from rich import print

from nanoai.model.config import ModelName

from projects.mind.intent.task_data.api_alg import (
    IntentClsInput, 
    IntentClsOutput, 
    IntentClsRunTrajectory,
    IntentClsPrompt,
    LLMParam,
    IntentClsParam,
    api_intent_cls,
)

def test_api_intent_cls():
    input = IntentClsInput(
        query="你好",
    )

    categories = ["闲聊", "座舱内的车辆控制", "其它不属于上述类别的"]

    param = IntentClsParam(
        prompt=IntentClsPrompt(
            categories=categories,
        ),
        llm_param=LLMParam(
            model=ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        ),
    )

    res = asyncio.run(api_intent_cls(input, param))

    print(res)


if __name__ == "__main__":
    test_api_intent_cls()