/** 语音测试页标准示例：按数据集名称 + case_id 从 DB 拉取，label 为展示名 */
export type VoiceCaseShowcaseEntry = {
  datasetName: string
  label: string
  caseId: string
}

export const VOICE_CASE_SHOWCASE: VoiceCaseShowcaseEntry[] = [
  {
    datasetName: '通用车载助手评测集',
    label: '单轮对话多任务',
    caseId: '叶子标签用例-多任务组合',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '单次多轮对话车控',
    caseId: '车窗·副驾开大→吹脸→关回',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '单次多轮对话联网搜索',
    caseId: '联网·追问·厦门船票',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '单次长多轮对话',
    caseId: '叶子标签用例-多轮对话_7轮及以上',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '容忍重试',
    caseId: '容忍重试的用例',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '容忍重试+带唤醒词',
    caseId: '容忍重试，且要求假人重试时带上固定的唤醒词的用例',
  },
  {
    datasetName: '奔驰项目多轮对话测试集',
    label: '超长单次多轮闲聊',
    caseId: '长对话稳定性-超20轮持续闲聊',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '普通记忆（2次多轮对话）',
    caseId: '叶子标签用例-常用地点记忆',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '时间规律记忆发现',
    caseId: '叶子标签用例-时间规律发现',
  },
  {
    datasetName: '通用车载助手评测集',
    label: '条件规律记忆发现',
    caseId: '条件·车外三十八度排队暴晒·最大制冷与前排通风口述联动',
  },
]