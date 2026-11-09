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
from enum import StrEnum
from pydantic import BaseModel, Field
from pathlib import Path
from datetime import datetime
import json
from nanoai.utils.async_utils import amap



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
    STANDARDIZATION = "标准化"


class RewriteStyle(BaseModel):
    name: str = Field(..., title="风格名称")
    description: str = Field(..., title="风格说明")
    examples: list[str] = Field(default_factory=list, title="示例")


"""
短轮指代生成质量低
"""
REWRITE_STYLES: dict[RewriteStyleEnum, RewriteStyle] = {
    RewriteStyleEnum.PRONOUN: RewriteStyle(
        name=RewriteStyleEnum.PRONOUN.value,
        description=(
            "使用明确指代词（它/这个/那个/这儿/那里等）指代前文‘唯一可匹配’的实体/参数/地点/歌曲/功能项；"
            "将指代词替换为所指对象后，句子应完整通顺；"
            "优先指代上一轮助手回答中的名词短语（如‘蓝牙连接’‘路线’‘那首歌’‘屏幕亮度’等）。"
        ),
        examples=[
            "把它调到22度",           
            "把那首歌再放一遍",
            "按那个路线走",
            "把那里设为终点",
            "这个再降一点"
        ],
    ),
    RewriteStyleEnum.STANDARDIZATION: RewriteStyle(
        name=RewriteStyleEnum.STANDARDIZATION.value,
        description="将说的话变得更口语化，如增加一些‘嗯、呃、啊’等语气词，使用‘帮我/能不能/可以吗/麻烦你/谢谢’等礼貌用语，以及一些完全没有必要的重复和冗余表达",
        examples=[
            "话说，我想去一下天安门那边，你能帮我导航一下吗？",
            "那个谁来着，李四，对对对，帮我给他打个电话吧",
            "啊啊啊，我想起来了，今天北京那边限不限行啊？",
            "麻烦您把空调温度调低一点点，现在有点热了"
        ],
    )
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


def build_simple_dialogue(start_domain: str, n: int) -> tuple[list[dict], str, str]:
    """
    构建简单对话：从指定领域开始，前 n-1 轮保持同域，最后一轮固定到传统垂域。
    返回：rounds 列表、领域路径字符串、最后一次领域迁移字符串。
    """
    assert n >= 2, "n 至少为 2 才能在最后一轮进行跨域"
    
    # 第一轮：从指定领域开始
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

    # 前 n-1 轮保持同域（优先使用同域关联）
    for round_idx in range(1, n - 1):
        assoc_map = list_all_associations_for_domain(current_domain)
        next_cat = None
        # 同域关联优先
        if assoc_map and current_domain in assoc_map:
            assoc = get_random_association(current_domain, current_domain)
            if assoc:
                candidate = _find_category_by_name(current_domain, assoc.target_category)
                if candidate is not None:
                    next_cat = candidate
        else:
            pass
            
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

    # 最后一轮：固定到传统垂域（优先使用跨域关联）
    traditional_domain = "传统垂域"
    
    # 检查是否有跨域关联
    assoc_map = list_all_associations_for_domain(current_domain)
    
    traditional_cat = None
    if assoc_map and traditional_domain in assoc_map:
        assoc = get_random_association(current_domain, traditional_domain)
        if assoc:
            candidate = _find_category_by_name(traditional_domain, assoc.target_category)
            if candidate is not None:
                traditional_cat = candidate
    else:
        pass
    
    if traditional_cat is None:
        # 无跨域关联可用时，随机选择传统垂域子类
        traditional_cat = random.choice(list(ALL_DOMAINS[traditional_domain].categories.values()))
    
    rounds.append({
        "from_domain": current_domain,
        "to_domain": traditional_domain,
        "from_name": current_cat_name,
        "to_name": traditional_cat.name,
        "to_description": traditional_cat.description,
        "to_examples": traditional_cat.examples,
        "to_notices": traditional_cat.notices or [],
    })

    domain_path_list.append(traditional_domain)
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


# 解析模型输出为：最后一轮用户问法 + 历史上下文（字符串列表）
def parse_dialogue_output(text: str) -> tuple[str, list[str]]:
    lines = [ln.strip() for ln in text.splitlines()]
    # 截断到“输出总结”之前
    try:
        summary_idx = next(i for i, ln in enumerate(lines) if ln.startswith("输出总结"))
        content_lines = lines[:summary_idx]
    except StopIteration:
        content_lines = lines

    # 抽取所有对话行
    convo_lines: list[str] = [ln for ln in content_lines if ln.startswith("用户：") or ln.startswith("助手：")]
    # 找到最后一个“用户：”作为最后一轮问法
    last_user_idx = -1
    for i, ln in enumerate(convo_lines):
        if ln.startswith("用户："):
            last_user_idx = i
    last_user_line = convo_lines[last_user_idx] if last_user_idx != -1 else "用户："
    last_user = last_user_line[len("用户："):].strip()
    # 历史上下文为最后一个用户问法之前的所有对话行
    history = convo_lines[:last_user_idx]
    return last_user, history


# 生成 5 个领域 × (2..5 轮 × 每轮 2 条) = 40 条对话，并保存到 JSON
async def generate_corpus_5x8(
    *,
    n_min: int = 2,
    n_max: int = 5,
    per_n: int = 2,
    output_filename: str = "generated_corpus_5x8.json",
    model: str = "doubao-seed-1-6-flash-250715",
    temperature: float = 1.0,
    top_p: float = 0.7,
    max_tokens: int = 800,
) -> str:
    chosen_style = REWRITE_STYLES[RewriteStyleEnum.PRONOUN]
    results: list[dict] = []

    # 构造任务列表：5个领域 × (n=2..5) × 每n 2条
    domains = list(ALL_DOMAINS.keys())
    tasks: list[tuple[str, int, int]] = []  # (domain, n, sample_idx)
    for domain in domains:
        for n in range(n_min, n_max + 1):
            for sample_idx in range(1, per_n + 1):
                tasks.append((domain, n, sample_idx))

    async def run_one(task: tuple[str, int, int]) -> dict:
        domain, n, sample_idx = task
        rounds, domain_path, last_transition = build_simple_dialogue(domain, n)
        text_multi = await gen_multi_round_dialogue(
            rounds,
            domain_path=domain_path,
            last_transition=last_transition,
            chosen_style=chosen_style,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        last_user, history = parse_dialogue_output(text_multi)
        return {
            "domain": domain,
            "rounds": n,
            "sample": sample_idx,
            "domain_path": domain_path,
            "last_transition": last_transition,
            "rewrite_style": chosen_style.name,
            "last_user": last_user,
            "history": history,
        }

    # 使用 nanoai 的 amap 并发执行，限制并发以稳妥（例如 5）
    results_list, _stats = await amap(run_one, tasks, max_concurrent=5, progress=True)
    results.extend(results_list)

    out_path = Path(__file__).resolve().parent / output_filename
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"已保存到: {out_path}")
    return str(out_path)


# 加载已保存的语料
def load_saved_corpus(path: str | None = None) -> list[dict]:
    out_path = Path(path) if path else (Path(__file__).resolve().parent / "generated_corpus_5x8.json")
    if not out_path.exists():
        return []
    with out_path.open("r", encoding="utf-8") as f:
        return json.load(f)


# 两种风格各生成指定数量（默认各20），n随机取[2,5]，最后一轮固定到传统垂域
async def generate_corpus_two_styles(
    *,
    count_each: int = 20,
    styles: list[RewriteStyleEnum] | None = None,
    output_prefix: str = "generated_corpus_two_styles",
    model: str = "doubao-seed-1-6-flash-250715",
    temperature: float = 1.0,
    top_p: float = 0.7,
    max_tokens: int = 800,
) -> str:
    if styles is None:
        styles = [RewriteStyleEnum.PRONOUN, RewriteStyleEnum.STANDARDIZATION]

    domains = list(ALL_DOMAINS.keys())
    tasks: list[tuple[RewriteStyleEnum, int]] = []  # (style, sample_idx)
    for st in styles:
        for idx in range(1, count_each + 1):
            tasks.append((st, idx))

    async def run_one(task: tuple[RewriteStyleEnum, int]) -> dict:
        style_enum, sample_idx = task
        chosen_style = REWRITE_STYLES[style_enum]
        domain = random.choice(domains)
        n = random.randint(2, 5)
        rounds, domain_path, last_transition = build_simple_dialogue(domain, n)
        text_multi = await gen_multi_round_dialogue(
            rounds,
            domain_path=domain_path,
            last_transition=last_transition,
            chosen_style=chosen_style,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
        last_user, history = parse_dialogue_output(text_multi)
        # 仅保留：sample、domain(由last_transition重命名)、rewrite_style、question(由last_user重命名)、history
        return {
            "sample": sample_idx,
            "domain": last_transition,
            "rewrite_style": chosen_style.name,
            "question": last_user,
            "history": history,
        }

    results_list, _stats = await amap(run_one, tasks, max_concurrent=8, progress=True)
    # 输出文件名添加时间戳，避免覆盖
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = Path(__file__).resolve().parent / f"{output_prefix}_{ts}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results_list, f, ensure_ascii=False, indent=2)
    print(f"已保存到: {out_path}")
    return str(out_path)


if __name__ == "__main__":
    async def _main():
        # 生成指代、标准化各20条，文件名带时间戳
        await generate_corpus_two_styles(count_each=20)

    asyncio.run(_main())
