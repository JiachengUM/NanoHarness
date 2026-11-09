import logging
import time
from typing import Any, Type

from jinja2 import Template
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from nanoai.model.llm import allm, allm_output
from nanoai.utils.nl_repr import nl_repr
from projects.hwhms.common.client import get_openai_client

logger = logging.getLogger(__name__)

class RewriteResult(BaseModel):
    result: str = Field(..., title="结果", description="改写的结果。")
    reason: str = Field(..., title="原因", description="改写的原因。")

    def __nl_repr__(self, **kwargs) -> str:
        return f"{self.result}。{self.reason}。"

class Rewrite(BaseModel):
    description: str = Field(..., description="关于用户任务的定义和描述")
    rules: list[str] | None = Field(default=None, title="改写规则", description="改写的详细规则")
    examples: list[str] | None = Field(default=None, title="改写示例", description="改写的正确示例")

async def rewritr[T](
    query: str,
    history: str,
    rewrite: Rewrite,
    /,
    *,
    client: AsyncOpenAI = get_openai_client(),
    output_type: Type[T] = str,
    output_hint: str = "请仅返回改写后的结果。",
    **llm_params,
    ) -> T:
    
    start_time = time.time()
    # 预先将意图类别转换为字符串表示
    rewrite_str = nl_repr(rewrite)

    # 使用 Jinja2 模板生成系统提示词
    # 模板支持动态渲染专家角色、意图类别列表和输出提示
    template_str = """
你的任务具体说明如下:
{{ rewrite_str }}

历史对话：
{{history}}

原用户指令：
{{query}}


{{ output_hint }}
"""
    template = Template(template_str)
    prompt = template.render(
        query=query,
        rewrite_str=rewrite_str,
        history=history,
        output_hint=output_hint
    )

    print(prompt)

    # 根据输出类型选择不同的调用方式
    if output_type is str:
        # 简单字符串输出，适用于生产环境
        response = await allm(
            prompt,
            client=client,
            **llm_params,
        )
    else: 
        # 结构化输出，得到更多信息用于分析，调试时使用，上线时关闭
        # 返回 Pydantic 模型对象，包含分类结果和详细原因
        response = await allm_output(
            prompt,
            output_type=output_type,
            client=client,
            **llm_params,
        )
    
    # 提取输出结果
    output = response.output
    logger.info(f"模型改写耗时: {time.time() - start_time:.2f}秒")
    return output  # type: ignore

class QueryRewrite:
    def __init__(self):

        self.llm_params: dict[str, Any] = {
            "model": "doubao-seed-1-6-flash-250715",
            "stream": False,
            "temperature": 1,
            "top_p": 0.7,
            "max_tokens": 2000,
            "extra_body": {
                "thinking": {
                    "type": "disabled",
                }
            },
        }

        self.rewrite_prompt = Rewrite(
                description="""对用户的车控指令进行规范化改写。""",
                rules=[
                    "改写后的用户指令是语义完整的句子, 脱离历史对话也完全可以理解",
                    """保持原表述的核心意图, 关键动作等信息""",
                    """如果有"它"、"这个"、"那个"之类的指代词，将其替换为对话历史中指代的的具体实体，替换时必须保留完整的实体描述，包括所有限定词和修饰语（如"屏幕亮度"不能简化为"亮度"）""",
                    """补全被省略的主语、宾语、动词等关键信息, 使得改写后的句子完整""",
                    """去除口语化、冗余、客套等表达""",
                    """去掉"好像"、"可能"、"大概"、"应该"等意图模糊的词""",
                    """去掉"你"、"帮我"、"能不能"、"可以吗"、"吧"等客套语""",
                    """去掉"不对"、"其实"、"更正"等澄清标记词""",
                    """正确理解状态描述的隐含意图：
                    1. 不带部件的模糊说法（如"有点热/冷"），默认针对空调：热→调低空调温度，冷→调高空调温度。
                    2. 带座椅部件的模糊说法（如"座椅有点热/冷"）：座椅有点热→关闭座椅加热，座椅有点冷→打开座椅加热。
                    3. 噪音描述（如"太吵"）：太吵→降低音量。""",
                    """保留精确信息：严禁省略具体的数值、百分比、量词（如"一半"、"10%"、"20度"等）以及目标状态（"最高"、"最低"、"最大"、"最小"、"高档位"）。例如："关闭一半"不能改为"关闭"，"调小10%"不能改为"调小"，"调到最高"不能改为"调高"。""",
                    """正确理解调节方向："低一点"意味着调低（如"温度低一点"->调低温度），"高一点"意味着调高。""",
                    """导航意图区分：如果用户说"顺路去"、"顺道去"，改写为"添加[地点]为途经点"；如果是"去"、"导航去"，改写为"导航去[地点]"。""",
                    """导航地点补全规则：如果历史对话中提到导航目的地，需要从历史对话中提取完整的地址信息（包括省、市、区和具体地点名称），并将其改写为"导航去[省][市][区][地点名称]"的格式""",
                ],
                examples=[
                    """原用户指令：那个，我想去一下天安门那边，你能帮我导航一下吗？\n改写后的用户指令：导航去天安门""",
                    """原用户指令：麻烦你把空调温度调低一点点，现在有点热了\n改写后的用户指令：调低空调温度""",
                    """原用户指令：嗯，能不能帮我播放一首周杰伦的歌曲呢？\n改写后的用户指令：播放周杰伦的歌""",
                    """原用户指令：我想看看今天北京那边限不限行啊？\n改写后的用户指令：查看今天北京的限行""",
                    """替换指代词的示例。\n对话历史：Q1: 附近有什么好玩的博物馆吗？\nA1: 附近有一家历史博物馆，展品丰富，非常有教育意义。\n原用户指令：导航去这家博物馆。\n改写后的用户指令：导航去历史博物馆。""",
                    """替换指代词的示例。\n对话历史：Q1: 播放一些摇滚乐。\nA1: 正在为您播放摇滚乐。\n原用户指令：调高它的音量。\n改写后的用户指令：音乐音量调高。""",
                    """替换指代词的示例。\n对话历史：Q1: 屏幕亮度调高点\nA1: 亮度已设置为80%。\nQ2: 亮度再调高点\nA2: 亮度已设置为90%。\n原用户指令：还是给它亮度调到80%吧\n改写后的用户指令：屏幕亮度调到80%""",
                    """状态描述示例。\n原用户指令：主驾有点热\n改写后的用户指令：调低主驾空调温度""",
                    """状态描述示例。\n原用户指令：主驾有点冷\n改写后的用户指令：调高主驾空调温度""",
                    """状态描述示例。\n原用户指令：主驾座椅有点热\n改写后的用户指令：关闭主驾座椅加热""",
                    """状态描述示例。\n原用户指令：主驾座椅冰冰的\n改写后的用户指令：打开主驾座椅加热""",
                    """状态描述示例。\n原用户指令：后排右边座椅太冷了\n改写后的用户指令：打开后排右边座椅加热""",
                    """极值保留示例。\n原用户指令：主驾空调温度调到最高\n改写后的用户指令：主驾空调温度调到最高""",
                    """极值保留示例。\n原用户指令：前排空调风量调到最大\n改写后的用户指令：前排空调风量调到最大""",
                    """档位保留示例。\n原用户指令：主驾座椅加热调到高档位\n改写后的用户指令：主驾座椅加热调到高档位""",
                    """调节方向示例。\n原用户指令：后排空调温度低一点\n改写后的用户指令：调低后排空调温度""",
                    """精确信息保留示例。\n原用户指令：天窗关闭一半\n改写后的用户指令：天窗关闭一半""",
                    """精确信息保留示例。\n原用户指令：语音交互音量调小10%\n改写后的用户指令：语音交互音量调小10%""",
                    """导航途经点示例。\n原用户指令：顺路去超市\n改写后的用户指令：添加超市为途经点""",
                    """导航地点补全的示例。\n对话历史：Q1: 重庆有啥适合带小孩去的餐厅\nA1: 为您推荐以下餐厅：1. 重庆老灶火锅（重庆市渝中区），2. 重庆小面馆（重庆市渝中区），3. 重庆火锅城（重庆市渝中区）\n原用户指令：导航去第二个\n改写后的用户指令：导航去重庆市渝中区重庆小面馆""",
                    """导航地点补全的示例。\n对话历史：Q1: 北京朝阳区有什么咖啡馆\nA1: 推荐：1. 星巴克臻选店（北京市朝阳区三里屯），2. 瑞幸咖啡（北京市朝阳区国贸）\n原用户指令：去第一个\n改写后的用户指令：导航去北京市朝阳区三里屯星巴克臻选店""",
                ],
            )


    async def run(
        self,
        query: str,
        history: list[str] | str | None = None,
        output_structure: bool = False,
    ) -> RewriteResult | str:
        """固定的对外接口"""

        # 如果没有历史对话，则无需改写，直接返回原始 query
        if not history:
            if output_structure:
                return RewriteResult(result=query, reason="历史为空，无需改写")
            return query

        # 兼容 list[str] / str 两种历史格式，统一转换成字符串
        if isinstance(history, list):
            history_text = "\n".join(str(item) for item in history)
        else:
            history_text = str(history)

        if output_structure:
            return await rewritr(
                query,
                history_text,
                self.rewrite_prompt,
                output_type=RewriteResult,
                **self.llm_params,
            )
        else:
            return await rewritr(query, history_text, self.rewrite_prompt, **self.llm_params)
