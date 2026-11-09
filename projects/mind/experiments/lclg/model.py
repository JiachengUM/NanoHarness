from langchain.messages import HumanMessage, AIMessage, SystemMessage

from langchain_openai import ChatOpenAI

from rich import print

from nanoai.model.config import ModelName, ARK_API_KEY, ARK_BASE_URL

def test_invoke():

    model = ChatOpenAI(
        model=ModelName.DOUBAO_SEED_1_8_251228,
        base_url=ARK_BASE_URL,
        api_key=ARK_API_KEY,
    )

    conversation = [
        SystemMessage("You are a helpful assistant that translates English to Chinese."),
        HumanMessage("Translate: I love programming."),
        AIMessage("我喜欢编程。"),
        HumanMessage("Translate: I love building applications.")
    ]

    result = model.invoke(conversation)
    print(f"type: {type(result)}")
    print(result)


if __name__ == "__main__":
    test_invoke()