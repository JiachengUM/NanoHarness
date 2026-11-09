import taskApi from '@/apis/task-data'
import { VOICE_CASE_SHOWCASE, type VoiceCaseShowcaseEntry } from './case-showcase-config'

export type VoiceCaseOption = {
  key: string
  label: string
  description?: string
  case: ComplexReasoningCase
  datasetId?: string
  datasetName?: string
}

export type LoadVoiceCaseOptionsResult = {
  options: VoiceCaseOption[]
  missing: VoiceCaseShowcaseEntry[]
}

function stripRuntimeMeta(doc: ComplexReasoningCase): ComplexReasoningCase {
  const { creator, created_time, updated_time, ...rest } = doc as ComplexReasoningCase & {
    creator?: string
    created_time?: string
    updated_time?: string
  }
  return rest
}

export async function loadDatasetCases(datasetId: string): Promise<ComplexReasoningCase[]> {
  const cases = await taskApi.complexReasoningCase.list({ dataset_id: datasetId })
  return (cases || []).map(stripRuntimeMeta)
}

export async function loadVoiceCaseOptions(): Promise<LoadVoiceCaseOptionsResult> {
  const datasets = await taskApi.complexReasoningDataset.list()
  const datasetIdByName = new Map<string, string>()
  for (const dataset of datasets || []) {
    if (dataset.name && dataset.id) {
      datasetIdByName.set(dataset.name, dataset.id)
    }
  }

  const caseListCache = new Map<string, ComplexReasoningCase[]>()
  const options: VoiceCaseOption[] = []
  const missing: VoiceCaseShowcaseEntry[] = []

  for (const entry of VOICE_CASE_SHOWCASE) {
    const datasetId = datasetIdByName.get(entry.datasetName)
    if (!datasetId) {
      missing.push(entry)
      continue
    }

    let cases = caseListCache.get(datasetId)
    if (!cases) {
      cases = await taskApi.complexReasoningCase.list({ dataset_id: datasetId })
      caseListCache.set(datasetId, cases || [])
    }

    const doc = cases.find((item) => item.case_id === entry.caseId)
    if (!doc) {
      missing.push(entry)
      continue
    }

    options.push({
      key: `${datasetId}:${entry.caseId}`,
      label: entry.label,
      description: doc.case_description || entry.caseId,
      case: stripRuntimeMeta(doc),
      datasetId,
      datasetName: entry.datasetName,
    })
  }

  return { options, missing }
}
