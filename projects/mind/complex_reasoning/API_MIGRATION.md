# complex_reasoning_agent api.py → mind complex_api_server.py 迁移说明

## 原版 api.py 实现的功能

| 接口 | 方法 | 功能 |
|------|------|------|
| `/v1/chat/completions` | POST | OpenAI 兼容的对话补全：body 为 ChatCompletionRequest（model, messages, chat_id, prompt_config 等），根据 `model` 是否以 `pre1` 开头选择 **request_stream_pre1**（Planner）或 **request_stream**（当前 agent），流式返回 SSE，通过 **generate_stream_chunks_from_data** 转成 OpenAI chunk 格式。 |
| `/v1/agent/do/stream` | POST | 火山 agent 流式：body 为 **VolAgentRequest**（chat_id, question_id, intent_type, query, history, car_info），转成 **RequestContext**，固定用 **request_stream_pre1**，通过 **generate_stream_chunks_from_data_for_vol_baseline** 转成火山基线 SSE 格式。 |
| `/get_question_id` | GET | 从 **question_id_pool** 取一个 id（供插件/上游用）。 |
| `/query_function` | GET | 直接调 **call_fc(query, uuid)**，返回 fc_result（用于调试/联调插件）。 |
| `/health` | GET | 健康检查，返回 `{"status":"ok"}`。 |
| `/upload_vlm_result` | POST | 台架 VLM 状态上报：body 为 **VehicleData**，调 **upload_vlm_state**。 |
| **startup** | - | HttpClient.get_instance()、**get_question_id_pool().init_pool()**、**init_nacos()**、**NacosConfigs.init()**。 |
| **shutdown** | - | HttpClient.close()。 |

## 迁到 mind 后需要改动的点

1. **推理引擎**  
   原版：`request_stream` / `request_stream_pre1`（Planner + SubAgentBuilder）。  
   mind：用 **create_agent(get_default_tools(chat_id))** 的 ReAct agent，流式用 **agent.astream(query)**，非流式用 **agent.ainvoke(query)**。

2. **请求/响应模型**  
   - 若要保持与 OpenAI / 火山完全一致：需在 mind 中定义等价 **ChatCompletionRequest**、**VolAgentRequest**（或复用 Pydantic 从原仓库拷），并实现「messages → 最后一条 user 作为 query」的转换。  
   - 流式输出：原版用 **DebugTextChunk / FullChunk / TailChunk** 和 **generate_stream_chunks_from_data**；mind 无这些类型，可简化为：从 **agent.astream** 得到「文本片段」和「工具调用结果」，按 OpenAI 风格组 SSE（delta.content 或自定义 reasoning_content）。

3. **/v1/chat/completions**  
   - 从 body 取 `model`、`messages`、`chat_id`（可选）、`show_json` 等。  
   - 最后一条 user content 作为 query；若有 `chat_id` 用其构造 tools，否则用新 uuid。  
   - 调用 `agent.astream(query)`，遍历 step：若是 str 则作为 delta.content 写 SSE；若是工具调用/结果可选择性写 reasoning_content 或忽略。  
   - 无需 Nacos：可去掉 `prompt_config` 或固定用 mind 的 default prompt。

4. **/v1/agent/do/stream**  
   - 若需与火山基线格式完全一致：需迁 **vol_baseline_stream_convertor** 及 **VolAgentRequest → RC**；否则可简化为：body 取 `query`、`chat_id`、`question_id`、`history`，用 **agent.astream(query)** 流式返回，SSE 格式自定或仿原版。

5. **/get_question_id**  
   - mind 已有 **utils/plugins/question_id_pool**，startup 时 **get_question_id_pool().init_pool()**，此接口直接 **return {"question_id": await get_question_id_pool().get_id()}** 即可。

6. **/query_function**  
   - mind 已有 **utils/plugins/plugins.call_fc**，需要 **chat_id**；可从 query 参数取 query，chat_id 用 uuid 或固定测试值，**return {"fc_result": await call_fc(query, chat_id)}**。

7. **/health**  
   - 直接 `return {"status": "ok"}`。

8. **/upload_vlm_result**  
   - 原版调 **upload_vlm_state**（complex_reasoning_agent 的 context.vlm）。mind 若无 VLM 状态存储，可先 **return {"status": 0, "errormsg": "上传成功"}** 做占位，或迁入 upload_vlm_state 与 VehicleData 模型。

9. **Nacos**  
   - 原版 startup 有 **init_nacos()**、**NacosConfigs.init()**，用于动态配置/拉 prompt。mind 可省略或改为从环境变量/本地 config 读，不在 startup 调 Nacos。

10. **CORS**  
    - 与原版一致在 FastAPI 加 **CORSMiddleware** 即可。

以上改完后，功能上与 api.py 一致：同一批 HTTP 接口，背后由 mind 的 ReAct agent + 现有 tools 执行。
