# Duplex DynamicTask（update）与 StreamTask 对比测评报告

## 1. 结论先行

新一轮实验已经改变旧对比结论：DynamicTask 不再使用对模型不可见的 create 文本，而是把
后台结果累计写回原 question，再用 PCM 主动激活。25/25 update 收到 ACK，Case 05、07、12
分别证明了跨轮可见、迟到结果续答和长会话事实连续性。

两种入口的核心差异不是“谁能并发 FC”——两者都能并发——而是工具跨越用户轮次后，谁持有
任务状态、结果如何重新进入上下文、以及如何启动回复：

- **StreamTask**：遵循 Duplex 原生 FC 轮次；同批工具全部结束后一次上行 `role=tool` output。
  清洁的一问一答路径短，但新用户轮次插入后，旧 output 经常不再触发续答。
- **DynamicTask**：立即返回占位，由 TaskManager 跨轮持有任务；成功后 update 原 question，
  再用 PCM 创建一个兼容性的推理触发。它能主动续答、精确取消和修改，但多了一层模型语义与
  音频调度风险。

本轮最稳妥的产品判断是：**StreamTask 是原生同步基线；DynamicTask update 版已经是有效的
异步兼容入口，并在跨轮连续性上明显更强，但仍不能把模型事实遵循、取消授权和 PCM 竞态视为
确定能力。**

## 2. 数据源与可比性

- DynamicTask：[`RULE_EVALUATION_REPORT.md`](RULE_EVALUATION_REPORT.md)
- StreamTask：[`SYNC_VOICE_TEST_REPORT.md`](SYNC_VOICE_TEST_REPORT.md)
- 两轮实际输入：[`VOICE_TEST_CASES.md`](VOICE_TEST_CASES.md)

本实验不是严格模型 A/B：

1. StreamTask 录制于 8 月 12 日，新 DynamicTask 录制于 8 月 13 日，联网搜索结果会变化。
2. 新 Dynamic 同时更换了 update 链路、系统提示词和激活语音，改善不能只归因于单一变量。
3. 工具延时、麦克风开关和环境噪音不同，不能用绝对耗时或 orphan ASR 直接比较 runner。
4. Case 05、06、09、10、11、12 的实际话术或等待时机不完全一致；其中 Sync Case 05、06
   只录到首轮。
5. 新 Dynamic Case 12 是顺序完成天气、电影、演唱会后才进入下一轮，没有复现旧测试的
   pending 取消或演唱会/车控跨 question 重叠。

因此只比较三类证据：协议日志能机械证明的机制；相近场景的行为趋势；每个版本内部“回复是否
受到该次工具材料支持”。

## 3. 两种数据流

| 阶段 | StreamTask | DynamicTask update 版 |
|---|---|---|
| 同组 FC | 本地并发执行 | 本地并发创建 TaskManager 任务 |
| 原 FC 轮次 | 等同组全部终态 | 立即返回同组占位 |
| 真实结果上行 | 同组攒齐，一次 `role=tool` create | 每个 success 累计 update 任务发起 question |
| 主动回复 | 依赖 Duplex 延续原 FC 轮次 | 等待当前播放结束，再发送本地 PCM 激活 |
| pending 状态所有者 | 原 FC / Duplex 会话 | 本地 TaskManager |
| 用户插入新轮次 | 可以继续收音，但旧续答容易失效 | 可以继续收音，旧任务仍由本地保持 |
| 取消与修改 | 无 session 级真实取消 | 精确 task_id cancel；修改可 cancel + recreate |
| 主要风险 | 旧 output 已上行但不再自动回复 | update 事实抽取、qid 归属、取消授权、PCM/真人碰撞 |

典型时间线：

```text
StreamTask，无插话：
Q_A -> FC_A -> 本地完成 -> tool output_A -> Duplex 自动回答 A

StreamTask，有插话：
Q_A -> FC_A pending -> Q_B -> 回答 B
                     -> tool output_A 上行 -> 经常不再回答 A

DynamicTask：
Q_A -> FC_A -> placeholder -> 原轮闭合
             -> TaskManager success -> update(Q_A) -> PCM -> 新推理回答 A
```

Dynamic 最后一段仍是兼容层模拟出的新语音轮，不是厂商原生的“追加外部 observation 后
`response.create()`”。厂商缺少该原语的第一性判断没有改变；改变的是本轮已经证明
`update + PCM` 这条兼容路径确实可见且可用。

## 4. 机械量化

| 指标 | DynamicTask update | StreamTask | 结论 |
|---|---:|---:|---|
| 纯用户 ASR | 46，另 1 个真人+PCM 混合轮 | 46 | 用户样本量接近，但 Dynamic 多合成输入 |
| 合成 PCM ASR | 21 纯 PCM + 1 混合轮 | 0 | 仅 Dynamic 有激活成本与碰撞面 |
| FC group / call | 44 / 51 | 31 / 36 | Dynamic 多 13 个 cancel FC |
| 业务 FC | 38 | 36 | 两边都有并发与 schema 失败样本 |
| 本地业务终态 | 25 success + 11 cancelled；另 2 schema 拒绝 | 35 success + 1 schema error | 两边都没有悬空调用 |
| 真实结果上行 | 25 update，25 ACK | 36 个 role=tool output | 传输链路均闭环 |
| 真实取消 | 11 | 0 | 只有 Dynamic 能中止后台任务 |
| 成功取消后迟到结果 | 0 / 11 | 不适用 | Dynamic 本地取消终态可靠 |
| 主动激活 | 22 PCM | 0 | StreamTask 依赖原生 continuation |

Dynamic 的 25 个 success 经 22 次 PCM 激活：Case 02、Case 06 一组、Case 12 各合并一组
同 question 多结果。这个差值是合并，不是漏发。

## 5. 核心维度对比

### 5.1 同轮并发：能力相同，回传策略不同

- StreamTask 在 Case 02、06、10、10_02 中都能并发执行同组 FC，并严格等待最慢调用后一次
  上行同组全部 output。
- DynamicTask 同样在 Case 02、06、10、10_02、12 中并发业务 FC；原 FC 只批量返回占位，
  真实结果按完成顺序 update，必要时合并 PCM 激活。

所以“并发工具”不是 Dynamic runner 的独占能力。Dynamic 的价值是任务脱离原 FC 轮次后仍有
session 级生命周期，而不是更会并发。

### 5.2 pending 期间继续对话：Dynamic 明显更完整

- Case 07：两边都能在香港天气 pending 时创建车控。Sync 的香港结果虽上行，却没有自然续答，
  后续追问还一度错搜上海；Dynamic 将两项绑定各自 question，车控与天气分别激活并回复。
- Case 08：Sync 把“需要带伞吗”变成第二次搜索，两个结果仍需用户再问“查到了吗”；Dynamic
  不重复调用，等待原任务后主动同时回答天气和带伞。

这两个 Case 直接验证了 TaskManager + update + PCM 对跨轮 liveness 的实际价值。旧报告中
“Dynamic 也会吞掉迟到结果”的结论，在新 Case 07 上已经被反证。

### 5.3 取消与修改：Dynamic 机制更强，模型语义仍不稳

StreamTask 没有 session 级 TaskManager：Case 09、10、11 中，模型可以口头说“取消”，但已
启动的工具仍继续执行并上行。

DynamicTask 的本地行为是真实的：

- Case 09 精确取消旧台风查询，无迟到结果，再创建新查询。
- Case 11_02 连续四次取消旧天气任务，只保留最终贵阳查询。
- 11 个成功取消全部没有 backfill。

但模型决策仍有三类失败：

- Case 10 第一条会澄清“取消哪个”，Case 10_02 同一句话却直接取消两个任务，授权语义不一致。
- Case 11 第一次录制使用不存在的 task_id，导致一个旧任务继续完成。
- Case 11 两条日志都错误回答自己取消过几次，TaskManager 真实历史没有可靠投影给模型。

因此 Dynamic 已解决“能不能取消 worker”，没有解决“模型是否正确理解取消谁、是否能如实
回忆任务历史”。

### 5.4 事实遵循：Dynamic 不再整体弱于 Sync，但两边都有反例

新 Dynamic 有明确依据的场景包括 Case 02、03、05、06 主体、07、09 天气、10 天气、
11 最终天气，以及 Case 12 的全部工具轮。Case 05 后续无新 FC 仍答出《空心》日期，进一步
证明不再是旧 create 版的“模型根本没看见结果”。

按相近 Case 看：

- Case 03：两边的台风和天气主体都能从各自工具结果找到。
- Case 04：Sync 至少引用了“大森”的真实事实，虽额外推荐超预算候选；Dynamic 完整编造“鮨政”。
- Case 05：新 Dynamic 的《锈》《空心》有依据；Sync 只录首轮，且“最新歌曲”选择与结果冲突。
- Case 08：Dynamic 控制更好，但 33℃精度不足；Sync 同样存在日期温度偏差。
- Case 09：两边最终 POI 都出现结果外实体或距离，Dynamic 只在取消机制上明显更好。
- Case 11：Dynamic 的最终目标天气基本正确，但一次旧香港结果被回答成上海；Sync 也有目标和
  数值错误。
- Case 12：新 Dynamic 四个工具轮均有依据；Sync 的清洁天气、电影也有依据，但原演唱会结果
  被新车控轮打断后没有自然续答。

结论不能再写成“原生 role=tool 一定比 update 事实性好”。更准确的是：原生路径在清洁单轮更
简单；update 路径已经具备事实可见性，跨轮更完整，但模型对长文本、POI 约束、旧 item 与当前
意图的归属仍不稳定。

### 5.5 回复时序与体验

StreamTask 没有占位，用户在长工具执行期间通常只等待；没有新用户轮次时，真实 output 后直接
由 Duplex 回复，链路更短。

DynamicTask 会快速播报“正在查询”，任务完成后还能主动恢复结果回复；代价是多一次 PCM ASR
和推理轮。日志证明 22 次 PCM 都在当时下行音频结束后发送，没有抢断正在播放的回复。

但上下行是独立流，无法只靠“当前没有播放”判断用户是否正要开口。Case 06 的 PCM 与真人追问
合并成一个 ASR，是 Dynamic 当前最重要的时序反例。两轮工具延时与麦克风策略不一致，不能给出
有意义的绝对时延优劣。

### 5.6 Case 12 与方言

新 Dynamic Case 12 的主要结论应单独保留：

- 天气、电影、演唱会顺序三轮都能 update 后主动、基于事实地回复。
- 空调 + 当前温度同轮并发，累计两个结果后一次回复完整覆盖。
- 长会话上下文和四川话措辞整体连续；第一次唱歌仍用普通歌词，用户纠正后恢复四川话改写。

Sync Case 12 也有事实正确的独立工具轮，但曾在长等待后退回普通话，且旧演唱会 continuation
被新轮次覆盖。由于麦克风、输入时序不同，不能宣称 Dynamic 的方言模型能力更强。

更重要的是，新 Dynamic Case 12 没有复现“电影 pending 时取消”或“演唱会 pending 时插入
车控”。它证明的是顺序长会话连续性和同 question 多结果，不应被扩写成所有跨任务抢占都已修复。

## 6. Case 对照矩阵

| Case | StreamTask | DynamicTask update | 对比结论 |
|---|---|---|---|
| 01 无工具/打断 | 通过 | 通过 | 基础语音接近 |
| 02 车控+导航 | 同批攒齐后正确回复 | 累计 update 后正确回复 | 两边都严格通过 |
| 03 台风预警 | 主体有依据 | 主体有依据 | 接近；Dynamic 已摆脱旧 create 失败 |
| 04 POI | 真店但违反单店约束 | 完整实体幻觉 | Sync 本轮更好 |
| 05 最新歌曲 | 首轮事实选择失败，缺追问 | 一次搜索支撑三轮追问 | Dynamic 更完整；非严格同输入 |
| 06 天气+歌曲 | 已录首轮事实通过 | 多轮事实基本通过，有 PCM 碰撞 | Dynamic 覆盖更广，不能完整 A/B |
| 07 pending 插车控 | 天气 output 上行后不续答 | 车控、天气分别续答 | Dynamic 明显更好 |
| 08 pending 追问 | 重复搜索且需手动追问 | 不重复并主动续答 | Dynamic 控制更好；两边温度均有偏差 |
| 09 取消+POI | 旧任务继续，POI 事实失败 | 旧任务真实取消，POI 事实失败 | Dynamic 生命周期更强 |
| 10 模糊取消 | 口头取消，任务继续 | 可真实取消，但澄清行为不一致 | Dynamic 技术更强，语义仍失败 |
| 11 连续修改 | 旧任务全部继续 | 可 supersede；一次错 task_id/错归属 | Dynamic 更接近目标，但不稳定 |
| 12 长会话/方言 | 清洁事实好，旧结果续答丢失 | 四个工具轮连续且有事实 | Dynamic 连续性更好；旧竞态未同条件复现 |

## 7. 设计判断

### 已验证的边界

1. StreamTask 适合作为 Duplex 原生 FC 行为基线，单轮数据流最短。
2. DynamicTask 的 TaskManager、真实取消、跨轮 pending 和主动恢复回复是额外工程能力，不是
   对 StreamTask 并发能力的重复封装。
3. `conversation.item.update` 能让外部结果进入上下文；PCM 能启动新推理。二者组合已经构成
   可工作的兼容层。
4. Duplex 仍没有原生“追加 observation + 创建响应”的协议原语，所以兼容层必须承担上下文
   shadow、音频激活和回复调度成本。
5. 兼容层无法完全消除用户开口与 PCM 同时上行；也不能强制模型始终按旧 item 结果而非当前
   对话意图作答。

### 当前取舍

- 保留两个明确入口：StreamTask 用于原生同步行为与厂商基线；DynamicTask 用于需要 pending、
  取消、修改和跨轮主动播报的实验/兼容场景。
- 不再把 DynamicTask 描述为“结果正文不可见”或“无法实现”；本轮日志已经否定这两个说法。
- 也不把 Case 12 的成功外推成产品全通过。需要继续约束的是模型语义和音频竞态，而不是再怀疑
  update 是否送达。

最终对比结论是：**StreamTask 的优势是原生和简单；DynamicTask update 版的优势是跨轮生命
周期与主动续答。新 Dynamic 已经从无效 create 实验变成可用兼容链路，但仍需把事实遵循、取消
授权和 PCM/真人竞争作为显式能力边界。**
