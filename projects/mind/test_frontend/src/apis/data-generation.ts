import {
  PLATFORM_BASE_URL,
  platformDelete,
  platformGet,
  platformPost,
  platformPostSSE,
  platformPut,
} from '@/request/platform-https'

export default {
  generationTask: {
    list: (params?: Partial<GenerationTask>) =>
      platformGet<GenerationTask[]>(`${PLATFORM_BASE_URL}/generation-task/list`, params),
    page: async (params?: PlatformPageParams & Partial<GenerationTask>): Promise<PageList<GenerationTask>> => {
      const result = await platformGet<PlatformPageList<GenerationTask>>(
        `${PLATFORM_BASE_URL}/generation-task/page`,
        params
      )
      return {
        page: result.page,
        size: result.page_size,
        total: result.total,
        items: result.items,
      }
    },
    create: (data: GenerationTask) =>
      platformPost<GenerationTask>(`${PLATFORM_BASE_URL}/generation-task`, data),
    update: (data: GenerationTask) =>
      platformPut<GenerationTask>(`${PLATFORM_BASE_URL}/generation-task/${data.id}`, data),
    del: async (id: string) => {
      await platformDelete<boolean>(`${PLATFORM_BASE_URL}/generation-task/${id}`)
    },
  },

  tagTree: {
    list: () => platformGet<TagTreeBrief[]>(`${PLATFORM_BASE_URL}/tag-tree/list-brief`),
    detail: (id: string) =>
      platformGet<TagTreeDetail>(`${PLATFORM_BASE_URL}/tag-tree/${id}`),
    create: (data: { name: string; description?: string; tree: object }) =>
      platformPost<TagTreeDetail>(`${PLATFORM_BASE_URL}/tag-tree`, data),
    upload: (data: { name: string; description?: string; tree: object }) =>
      platformPost<TagTreeDetail>(`${PLATFORM_BASE_URL}/tag-tree`, data),
    update: (id: string, data: { name: string; description?: string; tree: object }) =>
      platformPut<TagTreeDetail>(`${PLATFORM_BASE_URL}/tag-tree/${id}`, data),
    del: async (id: string) => {
      await platformDelete<boolean>(`${PLATFORM_BASE_URL}/tag-tree/${id}`)
    },
    exportUrl: (id: string) => `${PLATFORM_BASE_URL}/tag-tree/export/${id}`,
    preview: (name: string) =>
      platformGet<string>(`${PLATFORM_BASE_URL}/tag-tree/${encodeURIComponent(name)}/preview`),
  },

  scenarioPlan: {
    generate: (data: { query: string; tag_tree_name: string; task_id: string }) =>
      platformPost<ScenarioPlan>(`${PLATFORM_BASE_URL}/scenario-planning/generate`, data),
    update: (id: string, data: Partial<ScenarioPlan>) =>
      platformPut<ScenarioPlan>(`${PLATFORM_BASE_URL}/scenario-planning/${id}`, data),
    detail: (id: string) =>
      platformGet<ScenarioPlan>(`${PLATFORM_BASE_URL}/scenario-planning/${id}`),
  },

  scenario: {
    list: (params?: {
      keyword?: string
      tag?: string
      tag_tree_id?: string
      generation_task_id?: string
    }) => platformGet<GenerationScenario[]>(`${PLATFORM_BASE_URL}/scenario-management/list`, params),
    listByGenerationTask: (taskId: string) =>
      platformGet<GenerationScenario[]>(`${PLATFORM_BASE_URL}/scenario-management/by-generation-task/${taskId}`),
    generate: (data: GenerateScenarioRequest) =>
      platformPost<GenerateScenarioResult>(`${PLATFORM_BASE_URL}/scenario-generation`, data),
    generateStream: (
      data: {
        scenarioPlanId: string
        saveToDb: boolean
        maxIterations?: number
        initialBatchSize?: number
        maxRefineRoundsPerBatch?: number
      },
      onEvent: (event: ScenarioStreamEvent) => void,
      onClose?: () => void,
      signal?: AbortSignal
    ) => platformPostSSE<ScenarioStreamEvent['data']>(
      `${PLATFORM_BASE_URL}/scenario-generation-stream`,
      data,
      (event) => onEvent(event as ScenarioStreamEvent),
      onClose,
      signal
    ),
    cancelGeneration: (data: { scenarioPlanId?: string; generationTaskRunId?: string }) =>
      platformPost<boolean>(`${PLATFORM_BASE_URL}/scenario-generation-stream/cancel`, data),
    create: (data: GenerationScenario) =>
      platformPost<GenerationScenario>(`${PLATFORM_BASE_URL}/scenario-management`, data),
    update: (data: GenerationScenario) =>
      platformPut<GenerationScenario>(`${PLATFORM_BASE_URL}/scenario-management/${data.id}`, data),
    del: async (id: string) => {
      await platformDelete<boolean>(`${PLATFORM_BASE_URL}/scenario-management/${id}`)
    },
  },

  dataset: {
    list: () =>
      platformGet<ComplexReasoningDataset[]>(`${PLATFORM_BASE_URL}/complex_reasoning_dataset/list`),
    create: (data: ComplexReasoningDataset) =>
      platformPost<ComplexReasoningDataset>(`${PLATFORM_BASE_URL}/complex_reasoning_dataset`, data),
  },

  caseGeneration: {
    generate: (data: GenerateCasesRequest) =>
      platformPost<GenerateCasesResult>(`${PLATFORM_BASE_URL}/case-generation`, data),
    generateStream: (
      data: GenerateCasesRequest & {
        generationTaskRunId?: string
        maxIterations?: number
        maxRefineRoundsPerBatch?: number
        auditConcurrency?: number
        fixConcurrency?: number
      },
      onEvent: (event: CaseStreamEvent) => void,
      onClose?: () => void,
      signal?: AbortSignal
    ) => platformPostSSE<CaseStreamEvent['data']>(
      `${PLATFORM_BASE_URL}/case-generation-stream`,
      data,
      (event) => onEvent(event as CaseStreamEvent),
      onClose,
      signal
    ),
    cancelGeneration: (data: { datasetId?: string; generationTaskRunId?: string }) =>
      platformPost<boolean>(`${PLATFORM_BASE_URL}/case-generation-stream/cancel`, data),
    page: (params?: PlatformPageParams & { dataset_id?: string; source_scenario_id?: string; keyword?: string }) =>
      platformGet<PlatformPageList<GeneratedCase>>(`${PLATFORM_BASE_URL}/complex_reasoning_case/page`, params),
  },
}
