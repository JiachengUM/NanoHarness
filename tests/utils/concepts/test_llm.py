from __future__ import annotations

import anyio

from rich import print

from aicore.models.model_api import create_model_api, UserMessage

from aicore.models.credentials import ModelName

from aicore.utils._concepts.meta import Concept, SimpleConcept


async def test_gen_concept():
    """测试 LLM 生成包含 ObjectType 嵌套和 ArrayType 数组的 Concept。"""

    api = create_model_api(backend="chat", model=ModelName.SEED_1_8_251228)

    state = api.initial_state(system_prompt="")

    query = (
        "请生成一个描述电影的概念。要求：\n"
        "1）包含片名 title、上映年份 release_year\n"
        "2）导演个人信息"
        "3）演职员列表。"
    )

    try:
        response = await api.structured_output(
                UserMessage(text=query),
                output_type=Concept,
                state=state,
            )

        concept = response.parsed

        print(concept)

    except Exception as e:
        print(e)

async def test_gen_simple_concept():

    api = create_model_api(backend="responses", model=ModelName.SEED_1_8_251228)

    state = api.initial_state(system_prompt="")

    query = "请生成一个描述小说中人物的概念"

    try:
        response = await api.structured_output(
                UserMessage(text=query),
                output_type=SimpleConcept,
                state=state,
            )

        concept = response.parsed

        print(concept)

    except Exception as e:
        print(e)


if __name__ == "__main__":
    anyio.run(test_gen_concept)