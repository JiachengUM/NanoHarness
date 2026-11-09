from __future__ import annotations

import json
from typing import Any

from projects.mind.mem.auto_test_script.case_schema import DialogueRoundConfig, TestCase
from projects.mind.mem.auto_test_script.langchain_models import doubao_model
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree


def _deduplicate_keep_order(items: list[str]) -> list[str]:
    """
    标签去重并保留首个出现顺序，便于结果稳定可读。

    Args:
        items: 原始标签列表，允许重复。

    Returns:
        去重后的标签列表，保持首次出现顺序。
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _format_seed_user_queries(test_case: TestCase, max_rounds: int = 12) -> str:
    """
    当前 auto-test 数据约定：每次多轮对话只预置一条用户起始 query。
    这里按“第N次对话起始query”展示，不做摘要推断。

    Args:
        test_case: 待打标的测试用例对象。
        max_rounds: 最多展示的轮次数，超出部分省略。

    Returns:
        可直接拼接到 prompt 中的多行字符串。
    """
    lines: list[str] = []
    for idx, one_round in enumerate(test_case.user_query_lists[:max_rounds], start=1):
        if isinstance(one_round, DialogueRoundConfig):
            msgs = one_round.user_query_list
        else:
            msgs = one_round
        seed_query = next((msg.content for msg in msgs if msg.role == "user"), "无")
        lines.append(f"- 第{idx}次对话起始query: {seed_query}")
    if len(test_case.user_query_lists) > max_rounds:
        lines.append(f"- ... 其余 {len(test_case.user_query_lists) - max_rounds} 次对话起始query已省略")
    return "\n".join(lines) if lines else "- 无预置起始query"


def _format_leaf_tags_with_descriptions(tag_tree: TagTree) -> str:
    """
    将叶子标签及其说明格式化为多行文本，便于模型直接参考。

    Args:
        tag_tree: 标签树对象。

    Returns:
        形如 `- 标签名: 详情` 的多行字符串。
    """
    lines: list[str] = []
    for node in tag_tree.root.iter_leaf_nodes():
        description = (node.description or "").strip() or "（无详情）"
        lines.append(f"- {node.name}: {description}")
    return "\n".join(lines) if lines else "- 无叶子标签"


def _build_tagging_prompt(test_case: TestCase, tag_tree: TagTree) -> str:
    """
    构建给模型的打标提示词。

    关键点：
    - 打标“策略”不硬编码在此函数，而是来自 `tag_tree.tagging_guideline`。
    - 提示词里同时给出树形结构和叶子候选，降低模型越界输出概率。

    Args:
        test_case: 待打标的测试用例。
        tag_tree: 标签树对象，提供叶子候选与打标策略。

    Returns:
        发送给大模型的完整提示词文本。
    """
    leaf_tags = tag_tree.get_leaf_tag_names()
    leaf_tags_with_desc = _format_leaf_tags_with_descriptions(tag_tree)
    return f"""你是测试用例标签专家。请根据 case 内容，从给定标签树的叶子节点中挑选最合适的标签。

硬性约束（必须满足）：
1) 只能选择“叶子节点标签”。
2) 不要输出任何未在候选列表中的标签。
3) 返回 JSON，格式严格为：{{"tags": ["标签1", "标签2"]}}
4) 若无合适标签，返回：{{"tags": []}}
5) 标签数量建议 2-6 个；只有在证据非常强时再多选。

该标签树的打标思路（请严格遵循）：
{tag_tree.tagging_guideline}

标签树：
{tag_tree.to_pretty_string(show_leaf_mark=True)}

可选叶子标签：
{leaf_tags}

可选叶子标签及详情（重点参考）：
{leaf_tags_with_desc}

case 基本信息：
- case_id: {test_case.case_id}
- case_description: {test_case.case_description}
- expected_script: {test_case.expected_script}
- nl_assertion: {test_case.nl_assertion}
- context_config: {json.dumps(test_case.context_config, ensure_ascii=False)}

case 预置对话起始query（每次多轮对话仅1条）：
{_format_seed_user_queries(test_case)}
"""


def _build_retry_prompt(previous_prompt: str, validation_error: str) -> str:
    """
    在原提示词基础上追加“上次失败原因”，要求模型仅返回修正后的 JSON。

    Args:
        previous_prompt: 上一次发送给模型的提示词。
        validation_error: 上一次解析/校验失败的错误信息。

    Returns:
        用于重试调用的新提示词。
    """
    return (
        previous_prompt
        + "\n\n上一次输出校验失败，错误如下：\n"
        + validation_error
        + "\n请严格修正，仅返回合法JSON，且标签必须都来自标签树叶子节点。"
    )


def _extract_response_text(response: Any) -> str:
    """
    兼容不同模型SDK的返回格式，统一提取可解析文本：
    - 直接字符串
    - 带 `content` 字段的对象
    - 列表分块（dict/text 混合）

    Args:
        response: 模型返回对象，类型不固定。

    Returns:
        提取后的纯文本内容，用于后续 JSON 解析。
    """
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    chunks.append(text_value)
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks)
    return str(content)


def _parse_tags_from_model_output(model_output: str) -> list[str]:
    """
    解析模型输出为标签列表。

    容错策略：
    - 优先把整段当 JSON 解析；
    - 失败时尝试提取首个 `{...}` 再解析（应对模型附带解释文本）。

    Args:
        model_output: 模型输出的原始文本。

    Returns:
        解析后的标签列表（已去重并保序）。

    Raises:
        ValueError: 当输出不是可接受的 JSON 结构或 tags 类型不正确时抛出。
    """
    text = model_output.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"模型输出不是合法JSON: {model_output}")
        parsed = json.loads(text[start : end + 1])

    # 兼容两种返回格式：{"tags":[...]} 或直接 [...]
    if isinstance(parsed, dict):
        tags = parsed.get("tags", [])
    elif isinstance(parsed, list):
        tags = parsed
    else:
        raise ValueError(f"模型输出JSON格式不支持: {parsed}")

    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ValueError(f"模型返回 tags 格式错误: {tags}")
    return _deduplicate_keep_order(tags)


async def auto_tag_case_with_llm(
    test_case: TestCase,
    tag_tree: TagTree,
    llm: Any = doubao_model,
    max_retries: int = 3,
) -> list[str]:
    """
    用大模型对单个 TestCase 打标签（基于标签树叶子节点）。

    Args:
        test_case: 待打标的测试用例。
        tag_tree: 标签树对象（用于提示与叶子合法性校验）。
        llm: 异步大模型实例，需要提供 `ainvoke` 方法。
        max_retries: 最大重试次数（默认3），总调用次数为 `max_retries + 1`。

    Returns:
        最终通过校验的标签列表，并同步写入 `test_case.tags`。

    Raises:
        ValueError: 参数非法，或超过最大重试次数仍无法得到合法标签时抛出。
    """
    if max_retries < 0:
        raise ValueError("max_retries 不能小于0")

    # 首次调用 + 重试调用总计最多为 max_retries + 1 次
    prompt = _build_tagging_prompt(test_case, tag_tree)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            raw_response = await llm.ainvoke(prompt)
            model_output = _extract_response_text(raw_response)
            candidate_tags = _parse_tags_from_model_output(model_output)
            # 核心校验：标签必须存在于标签树且是叶子节点。
            tag_tree.validate_case_tags(candidate_tags)
            test_case.tags = candidate_tags
            return candidate_tags
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                raise ValueError(
                    f"自动打标失败，已达到最大重试次数({max_retries})，最后一次错误: {exc}"
                ) from exc
            prompt = _build_retry_prompt(prompt, str(exc))

    # 兜底
    raise ValueError(f"自动打标失败: {last_error}")
