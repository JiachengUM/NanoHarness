from typing import override, Any

import asyncio

from rich import print

from aicore.models.credentials import ModelName, create_client, AsyncArk

from projects.mind.demo.task import TaskType
from projects.mind.intent.alg.base import IntentClassifierBase
from projects.mind.intent.alg.simple import IntentClassifierLLM, ResponseParams

from projects.mind.demo.user_env.simulated_data import TEST_SHORT
from projects.mind.demo.task import ALL_CATEGORIES

class KeywordBasedIntentClassifier(IntentClassifierBase):
    """基于关键词的意图分类器"""
    
    @override
    def run(self, prompt: str, /,) -> tuple[str, Any]:
        # 遍历所有任务类别，根据关键词进行匹配
        for category in self.categories:
            if any(keyword in prompt for keyword in category.keywords): # type: ignore
                return category.name, None
        
        return TaskType.OTHER.value, None

    @override
    async def arun(self, prompt: str, /,) -> tuple[str, Any]:
        return self.run(prompt)

def test_intent_classifer():
    # 创建意图分类器实例
    #classifier = KeywordBasedIntentClassifier(ALL_CATEGORIES)

    params = ResponseParams(thinking={"type": "disabled"})
    #params = ResponseParams(thinking={"type": "enabled"})
    client, model = create_client(
        ModelName.SEED_1_6_FLASH_250828, 
        AsyncArk
        )
        
    classifier = IntentClassifierLLM(
        ALL_CATEGORIES,
        model = model,
        client = client,
        params = params,
    )

    print("cls_prompt:")
    print(classifier.cls_prompt)

    for query in TEST_SHORT:
        result, middle_info = asyncio.run(classifier.arun(query))
        print("\n===================================================")
        print(f"query: {query}")
        print(f"result: {result}")
        print(middle_info["response"])


# 测试意图分类器
if __name__ == "__main__":
    test_intent_classifer()