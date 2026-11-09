from openai import OpenAI
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params.response_format_json_schema import (
    ResponseFormatJSONSchema,
)
from pydantic import BaseModel, Field

if __name__ == "__main__":
    base_url = ""
    api_key = "REDACTED"
    model = ""

    client = OpenAI(base_url=base_url, api_key=api_key)

    class Character(BaseModel):
        name: str = Field(..., description="角色姓名")
        age: int = Field(..., description="角色年龄")
        hobbies: list[str] = Field(..., description="角色爱好，可能不止一种")

    sys_prompt = "请随机生成角色"
    user_input = "他是一个程序员"
    message_history = [
        ChatCompletionSystemMessageParam({"role": "system", "content": sys_prompt}),
        ChatCompletionUserMessageParam({"role": "user", "content": user_input}),
    ]

    response_format = ResponseFormatJSONSchema(
        type="json_schema",
        json_schema={"name": "response", "schema": Character.model_json_schema(), "strict": True},
    )

    response_origin = client.chat.completions.create(
        model=model,
        messages=message_history,
        response_format=response_format,
    )
    response = response_origin.choices[0].message
    assert response.content is not None
    output = Character.model_validate_json(response.content)

    print(type(output))
    print(output)
