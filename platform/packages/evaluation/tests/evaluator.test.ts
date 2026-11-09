import { describe, it, expect } from 'vitest'
import AgentV1Adaptor from '../src/adaptor/agent-v1'
import { Evaluator } from '../src/core/evaluator'
import { connect, disconnect, datasetRepository, DatasetItem } from '@eval-platform/database'

describe('Evaluator', () => {
  describe('getDataset', () => {
    it('should connect to MongoDB and list datasets', async () => {
      const mongoUri = 'mongodb://127.0.0.1:27017/eval_platform'

      await connect(mongoUri)

      const datasets = await datasetRepository.listDatasets()

      expect(datasets).toBeDefined()
      expect(Array.isArray(datasets)).toBe(true)

      await disconnect()
    })
  })

  describe('evaluate', () => {
    it('should evaluate a dataset item and return result', { timeout: 120000 }, async () => {
      const adaptor = new AgentV1Adaptor()
      const evaluator = new Evaluator(adaptor)

      const datasetItem = {
        case_id: '101',
        context_config: {},
        max_round: 3,
        user_query_lists: [
          [
            {
              role: 'user',
              content:
                '先带我去浦东那个圆圆的湖，再去有尼克狐尼克的公园，然后去有高达雕像的那个地方，最后带我去能看见三件套的那个桥。',
            },
          ],
        ],
        expected_script:
          '用户: 先带我去浦东那个圆圆的湖，再去有尼克狐尼克的公园，然后去有高达雕像的那个地方，最后带我去能看见三件套的那个桥。\n助手: 【语义理解】 将用户的模糊描述与城市地标映射：\n- "浦东那个圆圆的湖"→ 滴水湖；\n- "有尼克狐尼克的公园"→ 识别与迪士尼IP/主题活动相关的公园或活动区域（如迪士尼度假区或带尼克狐尼克IP活动区的公园）；\n- "有高达雕像的那个地方"→ LaLaport金桥高达广场；\n- "能看见三件套的那个桥"→ 外白渡桥。\n【POI查询】 分别检索以上四个地点的精确POI，并确认当前是否开放可达。\n【LLM内部逻辑】 按用户给出的顺序固定多途径点：起点→滴水湖→尼克狐尼克IP公园→LaLaport金桥高达→外白渡桥，不对顺序做自作主张调整。\n【导航控制】 规划一条包含上述四个目的地的多途径点路线，并启动导航；在每一段导航开始前进行语音提示当前要去的地标。',
        nl_assertion: [
          '重点考察：1) 将"圆圆的湖/尼克狐尼克/高达雕像/能看见三件套的桥"正确对齐到城市地标；2) 按用户自然语言顺序规划固定的多途径点导航，而不是简单单点导航。',
        ],
        case_description: 'P2\n导航领域测试用例: 语义理解- POI查询-多途径点导航控制',
        tags: [],
      } as unknown as DatasetItem

      const result = await evaluator.evaluate(datasetItem)

      expect(result).toBeDefined()
      expect(result.datasetItem).toBeDefined()
    })
  })
})
