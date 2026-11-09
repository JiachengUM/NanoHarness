# Simple/Complex Router Rule Cards

这个文件是规则的人工审阅入口。它不从算法字段开始解释，而从一个更小的问题开始：

> 当前 query 有没有足够证据，证明它可以被某个简单执行器一次性、安全地处理？

维护时只看两类证据：

- 正证据：query 能落到一张简单能力卡。
- 反证据：query 超过简单执行器边界，需要复杂链路。

`assets/<project>/capabilities/*.yaml`、`assets/<project>/rules/lexicon.yaml`、`assets/<project>/rules/global_risks.yaml`、`assets/<project>/rules/parser_rules.yaml` 和 `assets/<project>/llm_classfication/*.py` 是 runtime 资产；本文件是默认 profile 的人类可读视图。当前阶段先用于审阅和对齐，后续如果稳定，可以再把这种卡片结构变成生成 runtime YAML 的源头。

## 维护原则

- 先判断能力，不先判断关键词。
- 数字、档位、颜色、位置范围是值类型，不是关键词枚举。
- 词表只描述用户怎么说，不描述能力边界。
- 风险规则只描述为什么不能简单，不反向堆复杂关键词。
- parser 流程辅助词只解释残留和风险，不直接证明 simple 能力。
- exact case 负责覆盖数据集长尾，规则只沉淀稳定、可解释、可泛化的简单形状。

## 关键词归属

| 类型 | 放在哪里 | 不能放错的原因 |
| --- | --- | --- |
| 执行器可直接处理的动作/目标/值 | `assets/<project>/capabilities/*.yaml` | 这是 simple 的正向证明，必须能落到明确工具 |
| 能力命中后的路由策略 | `assets/<project>/capabilities/*.yaml` | `route_policy` / `intent_marker_policy` 决定完整命中后是直接 simple，还是继续交给 LLM fallback |
| 跨能力共享的别名 | `assets/<project>/rules/lexicon.yaml` | 词表只是展开说法，不能承载能力边界 |
| 未消费文本中的复杂反证据 | `assets/<project>/rules/global_risks.yaml` | 风险词只负责 veto，不应该被 card 宽泛消费 |
| parser 横向辅助信号 | `assets/<project>/rules/parser_rules.yaml` | 例如填充词、疑问词、通用值 token、场景辅助词；它们解释解析过程，不代表能力 |

## 通用值类型

这些值类型不是独立能力。只有被某张 `capabilities/*.yaml` 的 `values`、或 `rules/parser_rules.yaml` 的 parser 辅助规则引用时，才会影响当前运行结果。

| 值类型 | 人类含义 | 当前例子 |
| --- | --- | --- |
| 温度值 | 空调温度设置范围 | `18度`、`二十二度`、`22` |
| 档位值 | 低中高或 1-3 档控制 | `一档`、`2档`、`三挡` |
| 程度值 | 调大/调小/一点/一半/百分比 | `大一点`、`调小`、`50%` |
| 位置范围 | 车内区域或屏幕范围 | `主驾`、`副驾`、`左后`、`前排`、`全车` |
| 颜色值 | 氛围灯颜色 | `蓝色`、`红色`、`紫色` |
| 频率值 | 收音机 FM 频率 | `FM90.9`、`90.9` |
| 媒体序位 | 上下首/上下条/继续暂停 | `下一首`、`上一个`、`继续` |
| 天气时间范围 | 天气 query 和长范围天气风险判断 | `今天`、`明天`、`未来一周` |

## 全局复杂边界

只要 query 命中这些边界，除非 exact case 明确覆盖，否则应升级复杂链路。

| 边界 | 为什么复杂 | 典型例子 |
| --- | --- | --- |
| 多能力组合 | 需要多个工具或多个执行步骤 | `打开空调和座椅加热` |
| 同能力多目标不同值 | 单次简单指令无法唯一落参 | `主驾24度，副驾25度` |
| 条件/自动化 | 需要监听状态或未来触发 | `如果下雨就关窗`、`每天自动打开` |
| 记忆/偏好 | 需要写入或读取用户长期偏好 | `记住我喜欢22度` |
| 上下文指代 | 离开当前 query 不能确定目标 | `也这样`、`老规矩` |
| 场景目标 | 用户给的是目的，不是直接动作 | `小朋友睡着了`、`车里有异味` |
| 开放规划/比较 | 需要搜索、比较、推理或排序 | `找个顺路又好停车的餐厅` |
| 长时间范围和规划 | 简单天气 card 不承接多日规划或出行决策 | `未来一周天气怎么样` |

## Runtime 能力卡

下面只描述当前 `assets/default/capabilities/*.yaml` 真的存在、且 engine 会读取的默认 profile 能力边界。

- `route_policy=parser_simple`：完整命中且无风险残留时，parser 可以直接证明 simple。
- `route_policy=llm_fallback`：只作为开放能力入口或候选，完整命中后仍交给 LLM fallback。
- 没有 runtime card 的领域不要写成规则能力；这类样本只能来自 exact、LLM fallback 或上游链路。

### 端侧车控

| 能力卡 | 当前可证明 simple 的边界 | 复杂/兜底边界 |
| --- | --- | --- |
| `vehicle.temperature.set` / `vehicle.temperature.comfort` | 空调/温度/冷气/暖风开关、调高调低、设置温度值；用户明确表达冷/热时的体感温度调节 | 多区域不同温度、温度加风量/座椅等第二能力、自动化和偏好记忆 |
| `vehicle.fan.set` / `vehicle.circulation.set` / `climate.defog_air.set` / `vehicle.air_quality.set` | 风量风速、内外循环、除雾/除霜/出风、香氛/净化/加湿/灭菌等白名单目标和值 | 根据空气质量自动调整、条件触发、同时夹带温度/车窗/座椅等第二能力 |
| `vehicle.window.set` / `vehicle.blind.set` | 车窗、指定位置车窗、遮阳帘的打开/关闭/升降/留缝/锁止 | 多位置不同动作、模糊指代、依赖外部条件或安全策略 |
| `vehicle.light.set` / `vehicle.ambient_light.set` | 车灯/近光/远光/雾灯开关，氛围灯开关和颜色设置 | 多灯光目标不同动作、随音乐/大灯等联动、节奏策略 |
| `vehicle.seat.comfort.set` / `vehicle.seat.position.set` / `vehicle.seat.feature.set` | 座椅加热/通风/按摩/方向盘加热，腿托/脚托/坐垫/零重力，座椅便利进出/Auto/烘干等白名单模式 | 主副驾不同值、泛说 `座椅` 但没有具体功能、自动开启和偏好记忆 |
| `vehicle.feature.set` / `vehicle.drive_mode.set` / `vehicle.scene_mode.set` | 车道保持、驾驶辅助、自动泊车、无线充电、驾驶模式、用车习惯、场景模式、车外喊话等明确目标 | 只表达效果或场景目标，例如 `我想更省电`；目标/action 不足以唯一落到端侧功能 |
| `vehicle.status.query` / `vehicle.lock.set` / `vehicle.lock.status` | 胎压、电量、油量、续航、保养查询；儿童锁、面板锁、门锁控制和状态查询 | 需要外部综合诊断、上下文指代或多个状态联合判断 |
| `vehicle.hud.set` / `vehicle.blind_spot_display.set` / `vehicle.mirror.set` | HUD/抬头显示调节，转向补盲显示，后视镜折叠/加热/除雾/亮度等白名单功能 | 和屏幕、倒车镜、HUD 多显示面混合但目标不清；条件联动 |
| `vehicle.parking_assist.set` / `vehicle.parking_hold.set` / `vehicle.air_suspension.set` / `vehicle.fridge.set` | 自动泊入/泊出/车位/一键贴边，自动驻车，空气悬架，车载冰箱模式/儿童锁/电源等白名单目标 | 停车规划、泊车安全判断、冰箱策略规划或多步骤联动 |

### 端侧系统

| 能力卡 | 当前可证明 simple 的边界 | 复杂/兜底边界 |
| --- | --- | --- |
| `system.dialog.dismiss` / `system.generic.confirm` | 退出、取消、打断、闭嘴、拜拜、收藏 | 出现在复杂上下文中的确认/否定不应直接当 simple |
| `system.camera_360.set` / `system.display.set` / `system.hotspot.set` | 360/全景影像/行车记录仪/熄屏，屏幕显示和亮度，车机热点设置 | 多屏不同动作、需要外部应用链路或用户上下文 |
| `system.time_format.set` / `system.language.set` / `system.theme.set` / `system.voice_package.set` | 时间格式、系统语言、主题壁纸、桌面、语音包/音色/发音语言的白名单设置 | 开放下载、推荐、个性化选择或多步骤订阅流程 |
| `system.camera.take` / `system.dvr.capture` | 拍照、自拍、录像、DVR 录制/抓拍/录音和有限时长值 | 视频剪辑、内容理解、复杂记录策略 |
| `system.location.status` | 当前目的地、还有多久到等状态查询 | 依赖上文地点、路线规划或 POI 搜索 |

### 媒体

| 能力卡 | 当前可证明 simple 的边界 | 复杂/兜底边界 |
| --- | --- | --- |
| `system.volume.set` | 音量、导航音量、视频音量、副屏音量、静音等明确目标的大小/百分比设置 | 只有 `调高` / `再小一点` 且没有上下文时，不盲猜目标 |
| `media.music_app.set` | 打开/关闭音乐应用 | 指定歌曲、歌手、歌单、榜单、风格、场景音乐不在这个 card 直接执行 |
| `media.video.set` / `media.playback.seek` / `media.radio.tune` / `media.playback.start` / `media.playback.continue` | 视频应用和播放、快进快退、收音机/FM、开始播放、继续/暂停/停止/上下首/切歌 | 播放内容需要搜索、比较、最新榜单、个性化推荐 |
| `media.music.search` | 不是 parser-simple；它是 `route_policy=llm_fallback` 的开放音乐入口 | `播放周杰伦的歌`、`来点轻音乐`、`播放最新榜单`、`放我偶像欢快点的歌` 等进入 LLM fallback |

### 导航

| 能力卡 | 当前可证明 simple 的边界 | 复杂/兜底边界 |
| --- | --- | --- |
| `navigation.session.control` | 无开放实体的导航会话控制：开始、发起、启动、继续、结束、关闭、打开导航，以及空目标 `导航去` / `导航到` | 带 POI、地址、城市、地标、商户、路线偏好或上下文地点时，不由 parser 直接证明 simple |
| `navigation.route.preference` | 不是 parser-simple；它是 `route_policy=llm_fallback` 的路线偏好入口 | `不走高速`、`导航去正大广场，不走潜山路`、`找附近最近的花店导航过去` 等进入 LLM fallback |

维护原则：

- 不在 `navigation.yaml` 中堆 POI、城市、商户、地标词表。
- 不把开放导航目标做成 `parser_veto` 直接判复杂；这些 case 应进入 flash-LLM fallback。
- 只有没有目标唯一性问题的导航控制命令，才允许作为 parser simple。

### 电话和天气

| 能力卡 | 当前可证明 simple 的边界 | 复杂/兜底边界 |
| --- | --- | --- |
| `call.phone.start` / `call.phone.control` | 拨打/呼叫/联系/报警，接听/拒接/挂断电话 | 联系人歧义、需要二次确认、电话内容推理或多轮沟通 |
| `open_domain.weather.query` | 天气、下雨、气温、冷不冷、热不热、空气质量、雾霾、湿度、太阳、带伞等单问答 | 长时间范围、天气影响出行规划、天气后接车控动作 |

### 当前没有 runtime card

| 旧文档领域 | 当前口径 |
| --- | --- |
| 地点和周边查询 | 没有 `capabilities/*.yaml` card；不要把附近餐厅、咖啡、充电桩等写成 parser-simple 规则能力 |
| 开放域单问答 | 没有通用 QA card；数据集长尾由 exact 或 LLM fallback 处理 |
| 简单闲聊/情绪陪伴 | 没有闲聊 card；讲故事、唱歌、情绪安慰不属于当前 parser 能力边界 |

## 错例维护流程

处理错例时按这个顺序，不直接先加关键词：

1. 找正证据：它是否属于某张能力卡？
2. 找值类型：如果只是数字、档位、颜色、位置范围缺失，补值类型或词表。
3. 找反证据：如果是多能力、条件、规划、指代，补复杂边界。
4. 如果只是数据集开放域长尾，不沉淀规则，交给 exact case、LLM fallback 或上游链路。
5. 最后才考虑新增 capability。

每次规则修改后至少跑：

```bash
python -m projects.sgm_prod.classification.tools.evaluate_router_rules \
  --asset-dir projects/sgm_prod/classification/assets/default
```

如果涉及 production exact case，再跑：

```bash
python -m projects.sgm_prod.classification.tools.evaluate_router_assets \
  --asset-dir projects/sgm_prod/classification/assets/default
```
