# eval_tools/poi_compare/judger.py
from aicore.models.credentials import create_client, AsyncArk, ModelName
from aicore.models.responses import ainvoke_output_by_json

from eval_tools.poi_compare.models import CaseResult

# 使用和ralph相同的模型，但prompt策略完全不同（checklist vs 整体叙述）
JUDGER_MODEL = ModelName.SEED_1_8_251228


def _build_judger_prompt(goal: str, output: str, expected: dict) -> str:
    must_contain = expected.get("must_contain", [])
    description = expected.get("description", "无具体说明")
    if not must_contain:
        raise ValueError(f"expected dict must have non-empty 'must_contain', got: {expected}")
    checklist = "\n".join(f"- {item}" for item in must_contain)

    return f"""你是严格的评测裁判，请逐条核查AI助手的回答是否满足每个要求。

用户目标：{goal}
评测标准说明：{description}

请逐条判断以下要求是否在回答中得到满足：
{checklist}

AI助手的回答：
{output}

评分规则（必须遵守）：
- 5分：所有要求均满足
- 4分：绝大多数满足，有轻微瑕疵（缺少一项次要信息）
- 3分：约一半要求满足
- 2分：少数要求满足（1-2项）
- 1分：基本未满足任何要求

pass_fail规则：score >= 4 则为true，否则为false

在reason字段中，列出每条checklist项的判断结果（满足/不满足/部分满足），并在最后给出扣分原因。"""


async def judge(goal: str, output: str, expected: dict) -> CaseResult:
    """
    独立裁判函数。使用checklist逐条核查，返回CaseResult。
    与ralph内部LMEvaluator完全独立：不同prompt策略，不同实例。
    """
    prompt = _build_judger_prompt(goal, output, expected)

    client, _ = create_client(ModelName(JUDGER_MODEL), AsyncArk)
    result, _ = await ainvoke_output_by_json(
        prompt,
        output_type=CaseResult,
        client=client,
        model=JUDGER_MODEL,
    )
    return result
