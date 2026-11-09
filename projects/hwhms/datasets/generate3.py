from projects.hwhms.datasets.category import (
    Category,
    ALL_DOMAINS,
    get_random_association,
    list_all_associations_for_domain,
    list_all_associations_as_target_domain,
)

from jinja2 import Template
import asyncio
from nanoai.model.llm import allm
from projects.hwhms.common.client import get_openai_client
from openai import AsyncOpenAI
import random
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


STANDARDIZATION_NOTICE = """
【改写目标】泛化语料标准化改写
将表述方式不同但含义相同的语音指令进行扩展和规范，使其符合统一的格式和标准。

【需要标准化的表达类型】
1. 口语化表达：去除"那个"、"这个"、"嗯"、"呃"等犹豫词和语气词
2. 客套用语：去除"帮我"、"能不能"、"可以吗"、"麻烦你"、"谢谢"等礼貌用语
3. 冗余表达：去除重复和无意义的修饰
4. 生僻拗口：转换为常见的标准表达
5. ASR识别噪声：纠正可能的识别错误

【改写原则】
1. 保留核心动作和关键信息
2. 使用简洁明确的标准指令格式
3. 去除所有冗余和客套内容
4. 确保车载语音助手能直接理解和执行

【改写示例】
示例1：
  原问题："那个，我想去一下天安门那边，你能帮我导航一下吗？"
  改写后："导航去天安门"

示例2：
  原问题："麻烦你把空调温度调低一点点，现在有点热了"
  改写后："降低温度"

示例3：
  原问题："嗯，能不能帮我播放一首周杰伦的歌曲呢？"
  改写后："播放周杰伦的歌"

示例4：
  原问题："我想看看今天北京那边限不限行啊？"
  改写后："查看今天北京的限行"

示例5：
  原问题："那个谁来着，李四，对对对，帮我给他打个电话吧"
  改写后："打电话给李四"
"""


Multi_Context_Dialogue_JSON_Template = """
你是一个专业的语料生成专家。请生成共{{ rounds|length }}轮对话，并以JSON格式输出。

对话要求：
{% for r in rounds %}
第{{ loop.index }}轮：
- 领域：{{ r.to_domain }}
- 子类：{{ r.to_name }}
{% if loop.first %}
- 要求：关于"{{ r.to_domain }} - {{ r.to_name }}"的正常提问
{% else %}
- 要求：从"{{ r.from_domain }} - {{ r.from_name }}"自然过渡到"{{ r.to_domain }} - {{ r.to_name }}"的提问
{% endif %}
{% if loop.last %}
- **特别要求**：用户问题使用自然口语化表达（可包含犹豫词、客套语、冗余表达等），然后提供标准化改写版本
{% else %}
- 需要生成：用户问题 + 助手回答
{% endif %}

子类说明：
{{ r.to_name }}：{{ r.to_description }}

示例：
{% for example in r.to_examples %}
- {{ example }}
{% endfor %}

{% if r.to_notices %}
注意事项：
{% for notice in r.to_notices %}
- {{ notice }}
{% endfor %}
{% endif %}

{% endfor %}

{% if rounds|length >= 2 %}
【最后一轮改写要求】
{{ standardization_notice }}
{% endif %}

生成要求：
- 提问需符合该轮目标子类的定义与示例风格
- 过渡自然、语义连贯，避免生硬跳转
- 前{{ rounds|length - 1 }}轮：生成正常的用户问题和助手回答
- **第{{ rounds|length }}轮（最后一轮）：**
  1. user字段：生成自然口语化的问题（可包含犹豫词、客套语、冗余表达）
  2. rewritten_user字段：将口语化问题改写成简洁标准的指令格式
  3. assistant字段：设为null（不生成回答）

严格按照以下JSON格式输出（不要有任何其他内容）：
```json
{
  "rounds": [
    {
      "round": 1,
      "user": "第1轮的用户问题",
      "assistant": "第1轮的助手回答"
    }{% for i in range(1, rounds|length - 1) %},
    {
      "round": {{ i + 1 }},
      "user": "第{{ i + 1 }}轮的用户问题",
      "assistant": "第{{ i + 1 }}轮的助手回答"
    }{% endfor %},
    {
      "round": {{ rounds|length }},
      "user": "第{{ rounds|length }}轮的口语化用户问题（包含犹豫词/客套语/冗余表达）",
      "assistant": null,
      "rewritten_user": "改写为简洁标准的指令格式"
    }
  ],
  "domain_path": "{{ domain_path }}",
  "category_path": "{{ category_path }}"
}
```
"""


def render_multi_round_json_prompt(
        rounds: list[dict],
        domain_path: str,
        category_path: str
) -> str:
    """渲染 n 轮对话生成的提示词（JSON格式输出，包含标准化改写）"""
    template = Template(Multi_Context_Dialogue_JSON_Template)
    return template.render(
        rounds=rounds,
        domain_path=domain_path,
        category_path=category_path,
        standardization_notice=STANDARDIZATION_NOTICE
    )


def _find_category_by_name(domain_name: str, category_name: str) -> Category | None:
    """根据domain名称和category名称查找Category对象"""
    domain = ALL_DOMAINS.get(domain_name)
    if not domain:
        return None
    for cat in domain.categories.values():
        if cat.name == category_name:
            return cat
    return None


def build_specified_domain_rounds(
        n: int,
        source_domain: str,
        target_domain: str = "传统垂域"
) -> tuple[list[dict], str, str]:
    """
    构建指定域的 n 轮对话路径：
    - 前 n-1 轮保持在 source_domain 内（使用同域关联）
    - 第 n 轮跳转到 target_domain（从目标域视角选择映射）

    Args:
        n: 轮数（至少2轮）
        source_domain: 起始域（前n-1轮所在域）
        target_domain: 目标域（第n轮跳转到的域，默认为传统垂域）

    Returns:
        rounds 列表、领域路径字符串、子类路径字符串
    """
    if n < 2:
        raise ValueError("轮数至少为2轮")

    if source_domain not in ALL_DOMAINS:
        raise ValueError(f"起始域 '{source_domain}' 不存在")

    if target_domain not in ALL_DOMAINS:
        raise ValueError(f"目标域 '{target_domain}' 不存在")

    # 第1轮：在起始域随机选择一个子类
    start_cat = random.choice(list(ALL_DOMAINS[source_domain].categories.values()))

    rounds: list[dict] = []
    rounds.append({
        "from_domain": "",
        "to_domain": source_domain,
        "from_name": "",
        "to_name": start_cat.name,
        "to_description": start_cat.description,
        "to_examples": start_cat.examples,
        "to_notices": start_cat.notices or [],
    })

    current_cat_name = start_cat.name
    domain_path_list: list[str] = [source_domain]
    category_path_list: list[str] = [start_cat.name]

    # 生成第 2 到 n-1 轮：保持在起始域内（使用同域关联）
    for i in range(1, n - 1):
        next_cat = None

        # 优先使用同域关联（source_domain -> source_domain）
        assoc_map_for_source = list_all_associations_for_domain(source_domain)
        print('\n1:\n', assoc_map_for_source)
        if source_domain in assoc_map_for_source:
            assoc = get_random_association(source_domain, source_domain)
            print('\n2:\n', assoc)
            if assoc:
                candidate = _find_category_by_name(source_domain, assoc.target_category)
                if candidate is not None:
                    next_cat = candidate

        # 如果没有同域关联，随机选择该domain的另一个子类
        if next_cat is None:
            all_cats = list(ALL_DOMAINS[source_domain].categories.values())
            other_cats = [c for c in all_cats if c.name != current_cat_name]
            if other_cats:
                next_cat = random.choice(other_cats)
            else:
                next_cat = random.choice(all_cats)

        rounds.append({
            "from_domain": source_domain,
            "to_domain": source_domain,
            "from_name": current_cat_name,
            "to_name": next_cat.name,
            "to_description": next_cat.description,
            "to_examples": next_cat.examples,
            "to_notices": next_cat.notices or [],
        })

        current_cat_name = next_cat.name
        domain_path_list.append(source_domain)
        category_path_list.append(next_cat.name)

    # 最后一轮：跳转到目标域（从目标域视角选择关联）
    final_cat = None

    # 使用 list_all_associations_as_target_domain 从目标域视角查找
    assoc_map_for_target = list_all_associations_as_target_domain(target_domain)

    if source_domain in assoc_map_for_target:
        # 存在从source_domain到target_domain的关联
        associations = assoc_map_for_target[source_domain]
        if associations:
            # 随机选择一个关联
            selected_assoc = random.choice(associations)

            # 获取目标子类（target_category）
            candidate = _find_category_by_name(target_domain, selected_assoc.target_category)
            if candidate is not None:
                final_cat = candidate

    # 如果没有找到关联，随机选择目标域的一个子类
    if final_cat is None:
        final_cat = random.choice(list(ALL_DOMAINS[target_domain].categories.values()))

    rounds.append({
        "from_domain": source_domain,
        "to_domain": target_domain,
        "from_name": current_cat_name,
        "to_name": final_cat.name,
        "to_description": final_cat.description,
        "to_examples": final_cat.examples,
        "to_notices": final_cat.notices or [],
    })

    domain_path_list.append(target_domain)
    category_path_list.append(final_cat.name)

    # 构建路径字符串
    domain_path = f"{domain_path_list[0]} -> {domain_path_list[-1]}"
    category_path = f"{category_path_list[0]} -> {category_path_list[-1]}"

    return rounds, domain_path, category_path


async def gen_multi_round_dialogue_json(
        rounds: list[dict],
        /,
        *,
        domain_path: str,
        category_path: str,
        sys_prompt: str = "你是一个语料生成专家，严格按JSON格式输出，不要有任何其他内容。",
        client: AsyncOpenAI = get_openai_client(),
        **llm_params,
) -> dict:
    """生成一段 n 轮的上下文对话，返回JSON格式（最后一轮包含标准化改写）"""
    prompt = render_multi_round_json_prompt(rounds, domain_path, category_path)
    res = await allm(prompt, sys_prompt, client=client, **llm_params)

    output = res.output.strip()

    # 尝试提取JSON
    if output.startswith("```json"):
        output = output[7:]
        if output.endswith("```"):
            output = output[:-3]
        output = output.strip()
    elif output.startswith("```"):
        output = output[3:]
        if output.endswith("```"):
            output = output[:-3]
        output = output.strip()

    try:
        result = json.loads(output)
        return result
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        print(f"原始输出:\n{output}")
        raise


async def generate_corpus_batch(
        rounds: int,
        count: int,
        source_domain: str,
        target_domain: str = "传统垂域",
        output_file: Optional[str] = None,
        client: AsyncOpenAI = get_openai_client(),
        **llm_params
) -> list[dict]:
    """
    批量生成语料（简化输出）

    Args:
        rounds: 轮数（2-5）
        count: 生成条数
        source_domain: 起始域
        target_domain: 目标域（默认传统垂域）
        output_file: 输出文件路径（可选，JSON格式）
        **llm_params: LLM参数

    Returns:
        生成的语料列表（简化格式）
    """
    print(f"{'=' * 80}")
    print(f"生成配置: {rounds}轮 | {count}条 | {source_domain} → {target_domain}")
    print(f"{'=' * 80}\n")

    results = []
    success_count = 0
    failed_count = 0

    for i in range(count):
        try:
            print(f"[{i + 1}/{count}] 生成中...", end=" ")

            # 构建路径
            round_configs, domain_path, category_path = build_specified_domain_rounds(
                rounds, source_domain, target_domain
            )

            # 生成对话
            result = await gen_multi_round_dialogue_json(
                round_configs,
                domain_path=domain_path,
                category_path=category_path,
                client=client,
                **llm_params
            )

            results.append(result)
            success_count += 1
            print(f"✓")

        except Exception as e:
            failed_count += 1
            print(f"✗ 失败: {e}")
            continue

    print(f"\n生成完成: 成功 {success_count}/{count}，失败 {failed_count}/{count}\n")

    # 保存到文件（只保存data数组）
    if output_file and results:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"✓ 结果已保存到: {output_path}")
        print(f"  包含 {len(results)} 条语料\n")

    return results


if __name__ == "__main__":

    # ==================== 快速测试 ====================
    async def quick_test():
        """快速测试"""
        print("\n快速测试：生成3轮对话，用车助手→传统垂域\n")

        results = await generate_corpus_batch(
            rounds=3,
            count=2,
            source_domain="用车助手",
            target_domain="传统垂域",
            output_file="outputs/test_corpus.json",
            model="doubao-seed-1-6-flash-250715",
            temperature=1.0,
            top_p=0.7,
            max_tokens=1500,
        )

        if results:
            print("生成示例:")
            print(json.dumps(results[0], ensure_ascii=False, indent=2))



    asyncio.run(quick_test())