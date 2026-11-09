from nanoai.model.config import ModelName, create_client, AsyncOpenAI

from projects.mind.intent.alg.core import _intent_cls

from projects.mind.intent.task_data import (
    IntentClsInput, 
    IntentClsOutput, 
    IntentClsRunTrajectory,
    IntentClsPrompt,
    LLMParam,
    IntentClsParam,
)


async def api_intent_cls(
    input: IntentClsInput, 
    param: IntentClsParam
    ) -> tuple[IntentClsOutput, IntentClsRunTrajectory]:
    '''
    意图分类API。
    '''

    # 必须有这个转换，否则create_client会报错
    model_name = ModelName(param.llm_param.model)

    client, model = create_client(model_name, client_class=AsyncOpenAI)
    
    res = await _intent_cls(
        param.prompt,
        input.query, 
        input.messages,
        model=model,
        client=client,
        )


    output = IntentClsOutput(
        intent_type=res[0].category,
        reason=res[0].reason,
    )

    trajectory = IntentClsRunTrajectory(
        sys_prompt=res[1][1],
        user_prompt=res[1][0],
    )

    return output, trajectory
