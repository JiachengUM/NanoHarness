from __future__ import annotations

from rich import print

from aicore.models.model_api import UserMessage, create_model_api

from tests.models.model_api._model_api_examples_common import (
    ModelExampleCase,
    iter_model_cases,
    print_case_header,
    print_exception,
    print_model_response,
    print_state_dump,
    print_step,
    run_async,
    short_params,
    text_input,
)

async def example_state_lifecycle_flow(
    case: ModelExampleCase,
) -> None:
    """演示 ModelState 在一次完整对话生命周期中的用法。

    步骤包括：
    1. 发起首轮对话，并从 response 中拿到 state。
    2. 把 response.state 传给下一轮继续上下文。
    3. 在需要开启全新对话时重新创建 initial_state。
    4. 基于同一个历史 state 启动两条不同的后续对话。
    5. 使用 history 导出 provider-neutral 的 ModelMessage 历史。
    6. 修改 message list，插入调用方自己的 UserMessage 内容。
    7. 使用 state_from_history 根据修改后的通用消息历史重建 state，并继续后续对话。
    8. 使用 dump_state 将当前状态持久化为 ModelStateDump。
    9. 在当前 adapter 上使用 restore_state 恢复状态，并继续后续对话。
    10. 打印 model.history 与 responses.state 两种 dump format 的公共 envelope 和差异。
    """
    print_case_header("ModelAPI state lifecycle example", case)
    api = create_model_api(backend=case.backend, model=case.model_name)
    params = short_params(max_output_tokens=160)

    print_step("1. 首轮对话：拿到 response.state")
    token = f"state-demo-token-{case.backend}"
    state = api.initial_state(system_prompt="你是一个会严格记住用户短期上下文的助手。")
    query = f"请记住这个 token：{token}。只回复 OK。"
    print(f"user: {query}")
    first = await api.invoke(
        text_input(query),
        state=state,
        params=params,
    )
    print_model_response("首轮回复", first)

    print_step("2. 把 response.state 传给下一轮继续上下文")
    query = "刚才的 token 是什么？请只输出 token。"
    print(f"user: {query}")
    continued = await api.invoke(
        text_input(query),
        state=first.state,
        params=params,
    )
    print_model_response("续聊回复", continued)

    print_step("3. 需要开启全新对话时，重新创建 initial_state")
    fresh_state = api.initial_state(system_prompt="你是一个简洁助手。")
    query = "刚才的 token 是什么？如果上下文里没有，请说明没有看到。"
    print(f"user: {query}")
    fresh = await api.invoke(
        text_input(query),
        state=fresh_state,
        params=params,
    )
    print_model_response("全新 state 回复", fresh)

    print_step("4. 基于同一个历史 state 启动两条不同的后续对话")
    base_state = api.initial_state(system_prompt="你是一个商业分析助手。")
    query = "我们要讨论咖啡店选址。请记住主题，只回复 OK。"
    print(f"user: {query}")
    base = await api.invoke(
        text_input(query),
        state=base_state,
        params=params,
    )
    print_model_response("分支前的共同历史", base)

    left_query = "分支 A：从创业者视角，给一句选址建议。"
    right_query = "分支 B：从产品经理视角，给一句选址建议。"
    print(f"user branch A: {left_query}")
    left = await api.invoke(
        text_input(left_query),
        state=base.state,
        params=params,
    )
    print_model_response("分支 A 回复", left)

    print(f"user branch B: {right_query}")
    right = await api.invoke(
        text_input(right_query),
        state=base.state,
        params=params,
    )
    print_model_response("分支 B 回复", right)

    print_step("5. history：导出 provider-neutral 的 ModelMessage 历史")
    history = await api.history(left.state)
    print(f"history length: {len(history)}")
    print(f"last history item: {history[-1] if history else None}")

    print_step("6. 修改 message list：插入调用方自己的 UserMessage 内容")
    injected_message = UserMessage(text="调用方补充：预算上限是每月 2 万元。")
    edited_history = [
        *history,
        injected_message,
    ]
    print(f"inserted message: {injected_message}")
    print(f"edited history length: {len(edited_history)}")

    print_step("7. state_from_history：根据修改后的历史重建 state 并继续对话")
    edited_state = api.state_from_history(edited_history)
    query = "基于刚才补充的预算上限，给一句更具体的选址建议。"
    print(f"user: {query}")
    edited_response = await api.invoke(
        text_input(query),
        state=edited_state,
        params=params,
    )
    print_model_response("state_from_history 后继续对话", edited_response)

    print_step("8. dump_state：把当前状态转换成可存储的 ModelStateDump")
    dump = await api.dump_state(edited_response.state)
    print_state_dump("修改后 state dump", dump)

    print_step("9. restore_state：在当前 adapter 上恢复状态并继续对话")
    restored_state = api.restore_state(dump)
    query = "继续基于修改后的预算上下文，给一个下一步可执行动作。"
    print(f"user: {query}")
    restored_response = await api.invoke(
        text_input(query),
        state=restored_state,
        params=params,
    )
    print_model_response("restore 后继续对话", restored_response)

    print_step("10. dump envelope：观察不同 backend 的 format 差异")
    latest_dump = await api.dump_state(restored_response.state)
    print_state_dump("latest state dump", latest_dump)


def main() -> None:
    """运行 state 主流程示例，覆盖续聊、新对话、分支和 dump/restore。"""
    for case in iter_model_cases():
        try:
            run_async(example_state_lifecycle_flow(case))
        except Exception as exc:
            print_exception(f"state example failed: {case.label}", exc)


if __name__ == "__main__":
    main()
