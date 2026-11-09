import ScenarioGenerator from '../src/core/scenario-generator'
import DatasetGenerator from '../src/core/dataset-generator'
import type { ScenarioInstance } from '../src/core/scenario-generator'

const scenarioTemplate = {
  name: '导航条件筛选',
  description: '用户根据距离、评分、设施等条件筛选目的地并导航',
}

const userTemplate = {
  profile: {
    name: '张三',
    age: 30,
    gender: '男',
    preferences: ['音乐', '运动'],
  },
  intents: ['喜欢走高速', '不喜欢走内环'],
}

const carInfoTemplate = {
  speed: '60',
  gear: 'P',
  windows: '关闭',
  temperature: '24',
}

export async function generate() {
  const scenarioGenerator = new ScenarioGenerator()
  console.log('开始生成场景实例：', scenarioTemplate)
  const scenarios = await scenarioGenerator.generate(scenarioTemplate, userTemplate, carInfoTemplate)
  console.log('场景实例生成完成：', scenarios)

  const scenario = scenarios[0]
  console.log('开始生成测试用例：', scenario)
  const datasetGenerator = new DatasetGenerator()
  const datasetItems = await datasetGenerator.generate(scenario)
  console.log('测试用例生成完成：', datasetItems)
}

export async function generateScenarioLoop() {
  const scenarioGenerator = new ScenarioGenerator()
  console.log('开始生成场景实例：', scenarioTemplate)
  const scenarios = await scenarioGenerator.generateLoop(scenarioTemplate, userTemplate, carInfoTemplate)
  console.log('场景实例生成完成：', scenarios)
  scenarioGenerator.saveToFile()
  return scenarios
}

export async function generateDataset(scenarios: ScenarioInstance[]) {
  const datasetGenerator = new DatasetGenerator()
  // 只生成第一个场景实例的测试用例
  for (const scenario of [scenarios[0]]) {
    console.log('开始根据场景实例生成测试用例：', scenario.instance_id)
    const datasetItems = await datasetGenerator.generateLoop(scenario)
    console.log('测试用例生成完成：', datasetItems)
  }
  datasetGenerator.saveToFile()
}

export async function generateData() {
  const scenarios = await generateScenarioLoop()
  await generateDataset(scenarios)
}

// generate()
// generateScenarioLoop()
generateData()
