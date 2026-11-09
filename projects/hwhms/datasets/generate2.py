
from jinja2 import Template
import asyncio
from nanoai.model.llm import allm
from projects.hwhms.common.client import get_openai_client
from openai import AsyncOpenAI


# 改写描述和示例
rewrite_notice = {
    "指代": """
    描述:用户在当前对话中使用了代词或指示词来代替之前已经提到的实体或信息
    示例:
    history: [{"q": "车上有几个天窗", "a": ""}, {"q":"打开它吧", "a": ""}]
    改写后：打开天窗
    """,

    "模糊": """
    描述:用户表达含糊或不完整，需要系统结合上下文或进一步询问才能确定意图
    示例:
    history: [{"q": "导航到静", "a": ""}, {"q":"静安寺附近好吃的小店", "a": ""}]
    改写后：导航到静安寺附近好吃的小店
    """,

    "省略": """
    描述:用户在后续的语句中省略了部分内容，但结合上下文仍然能理解完整意图
    示例:
    history: [{"q": "导航到静安寺", "a": ""}, {"q":"到了想买点好吃的", "a": ""}]
    改写后: 查询静安寺附近的美食
    """,

    "澄清": """
    描述:用户对之前系统的回答或行为提出修正、补充或澄清，通常带有纠错或细化意图
    示例:
    history: [{"q": "导航到静安寺", "a": ""}, {"q":"是静安区", "a": ""}]
    改写后: 导航到静安区
    """

}


Context_Dialogue_Template = """
你是一个问题改写专家。请将用户的问题改写成完整、独立、简洁的问题，方便大模型理解和处理。

【对话历史】
{{history}}

【用户问题】
{{question}}

【改写要求】
{{rewrite_req}}

【执行】
1. 请先结合对话历史"{{history}}"理解上下文语境语义
2. 按照改写要求 将用户问题"{{question}}"改写

"""

def render_rewrite_prompt(history: list, rewrite_req: str, question: str) -> str:
    """
    根据用户原始问题改写,生成改写后的提问
    """
    template = Template(Context_Dialogue_Template)
    return template.render(
        history=history,
        rewrite_req=rewrite_req,
        question=question,
    )


async def gen_rewrite_dialogue(
    history,
    rewrite_req,
    question,
    /,
    *,
    sys_prompt: str = "你是一个问题改写语料生成专家，严格按要求输出对话，不要多余解释。",
    client: AsyncOpenAI = get_openai_client(),
    **llm_params,
) -> str:
    """
    生成关于用户问题的改写提问
    返回原始文本，调用方可自行解析。
    """
    prompt = render_rewrite_prompt(history, rewrite_req, question)
    res = await allm(prompt, sys_prompt, client=client, **llm_params)
    return res.output


if __name__ == "__main__":
    # 指代
    history1 = [{"user": "搜索并播放歌曲《岁月神偷》。", "ai_assistant": "正在搜索《岁月神偷》，找到后即刻播放。"},
               {"user": "它的歌手是谁", "ai_assistant": "岁月神偷的演唱歌手是xxx"}]

    # 省略
    history2 = [{"q": "查询上海今天的限行规定", "a": "上海今天限行规定：限行尾号X、Y（根据实际查询结果填写）。"},
                {"q": "明天呢？", "a": "上海明天限行规定：限行尾号A、B（根据实际查询结果填写）。"}]
    # 澄清
    history3 = [{"q": "打开空调内循环", "a": "已为你打开空调内循环"},
                {"q": "说错了,是外循环", "a": "已为你打开空调外循环"}]

    # 模糊
    history4 = [{"q": "导航到静", "a": "已为你导航去静安区"},
                {"q": "静安寺附近好吃的小店", "a": "已为你导航去 静安寺附近好吃的小店"}]

    history = history1
    question = history[-1]["user"]
    rewrite_req = rewrite_notice.get('指代')
    # rewrite_req = rewrite_notice.get('省略')
    # rewrite_req = rewrite_notice.get('澄清')
    # rewrite_req = rewrite_notice.get('模糊')


    async def _main():
        text = await gen_rewrite_dialogue(
            history,
            rewrite_req,
            question,
            model="doubao-seed-1-6-flash-250715",
            temperature=1.0,
            top_p=0.7,
            max_tokens=400,
        )
        print(text)

    asyncio.run(_main())