from projects.hwhms.datasets.category import (
    Category,
    ALL_DOMAINS,
    get_random_association,
    list_all_associations_for_domain,
)

from jinja2 import Template
import asyncio
from nanoai.model.llm import allm
from projects.hwhms.common.client import get_openai_client
from openai import AsyncOpenAI
import random
import re
from enum import StrEnum
from pydantic import BaseModel, Field



# 多轮模板（带循环）：最后一轮用户提问需可用于“指代/省略/模糊/澄清”改写
Multi_Context_Dialogue_Template = """
你是一个专业的语料生成专家。请生成共{{ rounds|length }}轮对话，严格按以下格式逐轮输出。

{% for r in rounds %}
第{{ loop.index }}轮：
用户：{% if loop.first %}关于"{{ r.to_domain }} - {{ r.to_name }}"的提问{% else %}从"{{ r.from_domain }} - {{ r.from_name }}"自然过渡到"{{ r.to_domain }} - {{ r.to_name }}"的提问{% endif %}{% if loop.last %}（本轮必须包含对上下文的依赖表达，便于后续改写）{% endif %}
{% if not loop.last %}助手：回答{% endif %}

子类说明
{{ r.to_name }}：{{ r.to_description }}

示例
{% for example in r.to_examples %}
- {{ example }}
{% endfor %}

注意事项
{% for notice in r.to_notices %}
- {{ notice }}
{% endfor %}

{% if loop.last %}
改写风格要求（仅最后一轮适用，必须使用该风格）
目标风格：{{ chosen_style_name }}
风格说明：{{ chosen_style_description }}
风格示例：
{% for example in chosen_style_examples %}
- {{ example }}
{% endfor %}
约束：
- 必须明显体现“{{ chosen_style_name }}”风格
- 不得使用除该风格以外的表达方式
{% if chosen_style_name != "指代" %}- 禁止出现“它/这个/那个/这儿/那里”等明显指代词{% endif %}
要求：最后一轮“用户：”的提问必须体现上述风格，并依赖上下文，不得输出完全独立的问题。
{% endif %}

{% endfor %}

生成要求
- 前各轮（除最后一轮）必须只输出两行：以“用户：”开头的一行，紧跟以“助手：”开头的一行
- 最后一轮仅输出“用户：”一行，不输出“助手：”
- 提问需符合该轮目标子类的定义与示例风格
- 过渡自然、语义连贯，避免生硬跳转；不得输出多余解释或列表编号
- 最后一轮用户提问必须包含对上下文的依赖表达（指代/省略/模糊/澄清任意一种），不要输出完全独立的问题

输出总结（放在所有轮次之后，严格追加以下三行）
领域路径：{{ domain_path }}
最后一次领域迁移：{{ last_transition }}
最后一轮改写类型：{{ chosen_style_name }}
"""


def render_multi_round_prompt(rounds: list[dict], domain_path: str, last_transition: str, *, chosen_style_name: str, chosen_style_description: str, chosen_style_examples: list[str]) -> str:
    """
    渲染 n 轮对话生成的提示词（使用模板内循环）。
    rounds: 形如[{from_domain, to_domain, from_name, to_name, to_description, to_examples, to_notices}, ...]
    """
    template = Template(Multi_Context_Dialogue_Template)
    return template.render(
        rounds=rounds,
        domain_path=domain_path,
        last_transition=last_transition,
        chosen_style_name=chosen_style_name,
        chosen_style_description=chosen_style_description,
        chosen_style_examples=chosen_style_examples,
    )


# ==================== 改写风格定义（仿照 category.py 的风格） ====================

class RewriteStyleEnum(StrEnum):
    PRONOUN = "指代"
    ELLIPSIS = "省略"
    VAGUE = "模糊"
    CLARIFICATION = "澄清"


class RewriteStyle(BaseModel):
    name: str = Field(..., title="风格名称")
    description: str = Field(..., title="风格说明")
    examples: list[str] = Field(default_factory=list, title="示例")


REWRITE_STYLES: dict[RewriteStyleEnum, RewriteStyle] = {
    RewriteStyleEnum.PRONOUN: RewriteStyle(
        name=RewriteStyleEnum.PRONOUN.value,
        description="使用‘它/这个/那个/这儿/那里’等指代前文实体或信息",
        examples=["它能调到几度？", "这个再降一点？", "那个设置要怎么改？"],
    ),
    RewriteStyleEnum.ELLIPSIS: RewriteStyle(
        name=RewriteStyleEnum.ELLIPSIS.value,
        description="省略主语/宾语/动词，但结合上下文可理解",
        examples=["再调低两度。", "再来一个。", "和刚才一样就行。"],
    ),
    RewriteStyleEnum.VAGUE: RewriteStyle(
        name=RewriteStyleEnum.VAGUE.value,
        description="使用‘好像/大概/应该/差不多/可能’等模糊词",
        examples=["好像有点热，再降点？", "差不多就行", "大概再靠右一点"],
    ),
    RewriteStyleEnum.CLARIFICATION: RewriteStyle(
        name=RewriteStyleEnum.CLARIFICATION.value,
        description="对前述内容纠正/补充/细化",
        examples=["不是内循环，是外循环。", "我说的是第二个那个。", "不是那家餐厅，是旁边那家。"],
    ),
}


def _find_category_by_name(domain_name: str, category_name: str) -> Category | None:
    domain = ALL_DOMAINS[domain_name]
    for cat in domain.categories.values():
        if cat.name == category_name:
            return cat
    return None


def build_cross_domain_rounds(n: int) -> tuple[list[dict], str, str]:
    """
    构建跨域的 n 轮对话路径：每轮位于不同 domain，使用 category.py 的跨域关联。
    返回：rounds 列表、领域路径字符串、最后一次领域迁移字符串。
    """
    domain_names = list(ALL_DOMAINS.keys())
    start_domain = random.choice(domain_names)
    start_cat = random.choice(list(ALL_DOMAINS[start_domain].categories.values()))

    rounds: list[dict] = []
    rounds.append({
        "from_domain": "",
        "to_domain": start_domain,
        "from_name": "",
        "to_name": start_cat.name,
        "to_description": start_cat.description,
        "to_examples": start_cat.examples,
        "to_notices": start_cat.notices or [],
    })

    current_domain = start_domain
    current_cat_name = start_cat.name
    domain_path_list: list[str] = [start_domain]

    for _ in range(1, n):
        # 获取当前域的可达目标域集合
        assoc_map = list_all_associations_for_domain(current_domain)
        target_domains = list(assoc_map.keys()) if assoc_map else []
        next_domain = None
        next_cat = None

        if target_domains:
            next_domain = random.choice(target_domains)
            assoc = get_random_association(current_domain, next_domain)
            if assoc:
                # 优先使用关联中的目标子类名
                candidate = _find_category_by_name(next_domain, assoc.target_category)
                if candidate is not None:
                    next_cat = candidate
        # 若未找到可用关联或目标子类，退化为随机选择一个不同域与子类
        if next_domain is None or next_cat is None:
            alt_domains = [d for d in domain_names if d != current_domain]
            next_domain = random.choice(alt_domains) if alt_domains else current_domain
            next_cat = random.choice(list(ALL_DOMAINS[next_domain].categories.values()))

        rounds.append({
            "from_domain": current_domain,
            "to_domain": next_domain,
            "from_name": current_cat_name,
            "to_name": next_cat.name,
            "to_description": next_cat.description,
            "to_examples": next_cat.examples,
            "to_notices": next_cat.notices or [],
        })

        current_domain = next_domain
        current_cat_name = next_cat.name
        domain_path_list.append(current_domain)

    domain_path = " -> ".join(domain_path_list)
    last_transition = f"{domain_path_list[-2]} -> {domain_path_list[-1]}" if len(domain_path_list) >= 2 else f"{domain_path_list[0]} -> {domain_path_list[0]}"
    return rounds, domain_path, last_transition


def build_same_domain_then_cross(n: int) -> tuple[list[dict], str, str]:
    """
    构建 n 轮路径：前 n-1 轮保持同一个 domain（优先依据同域关联），最后一轮跨域（依据跨域关联）。
    返回：rounds 列表、领域路径字符串、最后一次领域迁移字符串。
    """
    assert n >= 2, "n 至少为 2 才能在最后一轮进行跨域"

    domain_names = list(ALL_DOMAINS.keys())
    start_domain = random.choice(domain_names)
    start_cat = random.choice(list(ALL_DOMAINS[start_domain].categories.values()))

    rounds: list[dict] = []
    rounds.append({
        "from_domain": "",
        "to_domain": start_domain,
        "from_name": "",
        "to_name": start_cat.name,
        "to_description": start_cat.description,
        "to_examples": start_cat.examples,
        "to_notices": start_cat.notices or [],
    })

    current_domain = start_domain
    current_cat_name = start_cat.name
    domain_path_list: list[str] = [start_domain]

    # 前 n-1 轮保持同域（若无可用同域关联，则退化为在同域内随机挑选下一子类）
    for _ in range(1, n - 1):
        assoc_map = list_all_associations_for_domain(current_domain)
        next_cat = None
        # 同域关联优先
        if assoc_map and current_domain in assoc_map:
            assoc = get_random_association(current_domain, current_domain)
            if assoc:
                candidate = _find_category_by_name(current_domain, assoc.target_category)
                if candidate is not None:
                    next_cat = candidate
        if next_cat is None:
            # 无同域关联可用时，在同域内随机
            next_cat = random.choice(list(ALL_DOMAINS[current_domain].categories.values()))

        rounds.append({
            "from_domain": current_domain,
            "to_domain": current_domain,
            "from_name": current_cat_name,
            "to_name": next_cat.name,
            "to_description": next_cat.description,
            "to_examples": next_cat.examples,
            "to_notices": next_cat.notices or [],
        })

        current_cat_name = next_cat.name
        domain_path_list.append(current_domain)

    # 最后一轮跨域
    assoc_map = list_all_associations_for_domain(current_domain)
    target_domains = [d for d in assoc_map.keys() if d != current_domain] if assoc_map else []
    next_domain = None
    next_cat = None
    if target_domains:
        next_domain = random.choice(target_domains)
        assoc = get_random_association(current_domain, next_domain)
        if assoc:
            candidate = _find_category_by_name(next_domain, assoc.target_category)
            if candidate is not None:
                next_cat = candidate
    if next_domain is None or next_cat is None:
        alt_domains = [d for d in domain_names if d != current_domain]
        next_domain = random.choice(alt_domains) if alt_domains else current_domain
        next_cat = random.choice(list(ALL_DOMAINS[next_domain].categories.values()))

    rounds.append({
        "from_domain": current_domain,
        "to_domain": next_domain,
        "from_name": current_cat_name,
        "to_name": next_cat.name,
        "to_description": next_cat.description,
        "to_examples": next_cat.examples,
        "to_notices": next_cat.notices or [],
    })

    domain_path_list.append(next_domain)
    domain_path = " -> ".join(domain_path_list)
    last_transition = f"{domain_path_list[-2]} -> {domain_path_list[-1]}"
    return rounds, domain_path, last_transition


async def gen_multi_round_dialogue(
    rounds: list[dict],
    /,
    *,
    domain_path: str,
    last_transition: str,
    chosen_style: RewriteStyle,
    sys_prompt: str = "你是一个语料生成专家，严格按要求输出对话，不要多余解释。",
    client: AsyncOpenAI = get_openai_client(),
    **llm_params,
) -> str:
    """
    生成一段 n 轮的上下文对话：Q1/A1 -> Q2/A2 -> ...（最后一轮仅有用户问法）。
    每一轮都使用该轮目标子类的示例与注意事项，并按跨域关联过渡。
    """
    prompt = render_multi_round_prompt(
        rounds,
        domain_path,
        last_transition,
        chosen_style_name=chosen_style.name,
        chosen_style_description=chosen_style.description,
        chosen_style_examples=chosen_style.examples,
    )
    res = await allm(prompt, sys_prompt, client=client, **llm_params)
    return res.output


if __name__ == "__main__":
    # 指定轮数 n；基于跨域关联生成不同 domain 的子类路径
    n = 3
    per_style = 5

    async def _main():
        styles_in_order = [
            RewriteStyleEnum.PRONOUN,
            RewriteStyleEnum.ELLIPSIS,
            RewriteStyleEnum.VAGUE,
            RewriteStyleEnum.CLARIFICATION,
        ]
        idx = 1
        for style_enum in styles_in_order:
            chosen_style = REWRITE_STYLES[style_enum]
            print(f"=== 改写风格：{chosen_style.name}（每种生成 {per_style} 条） ===")
            for _ in range(per_style):
                rounds, domain_path, last_transition = build_same_domain_then_cross(n)
                text_multi = await gen_multi_round_dialogue(
                    rounds,
                    domain_path=domain_path,
                    last_transition=last_transition,
                    chosen_style=chosen_style,
                    model="doubao-seed-1-6-flash-250715",
                    temperature=1.0,
                    top_p=0.7,
                    max_tokens=800,
                )
                print(f"=== 样本 {idx} ===")
                print(text_multi)
                print()
                idx += 1

    asyncio.run(_main())
