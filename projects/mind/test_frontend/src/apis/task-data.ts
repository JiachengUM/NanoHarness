import { get, post, put, del, BASE_URL, AGENT_ARENA_BASE_URL } from '@/request/https'

export type AdvisorRunType = 'comfort' | 'emotion' | 'comfort_quick' | 'emotion_quick'

export default {
  auth: {
    me: () => get<FeishuUser | null>(`${BASE_URL}/auth/me`),
    logout: () => post<void>(`${BASE_URL}/auth/logout`, {}, false),
    feishuLoginUrl: (redirect?: string) =>
      `${BASE_URL}/auth/feishu/login?redirect=${encodeURIComponent(redirect || '/')}`,
  },
  advisorDataset: {
    page: (params?: PageParams<Dataset>) => get<PageList<Dataset>>(`${BASE_URL}/advisor_dataset/page`, params),
    list: (params?: Dataset) => get<Dataset[]>(`${BASE_URL}/advisor_dataset/list`, params),
    create: (data: Dataset) => post<Dataset>(`${BASE_URL}/advisor_dataset`, data),
    update: (data: Dataset) => put<Dataset>(`${BASE_URL}/advisor_dataset/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/advisor_dataset/${id}`),
  },
  advisorInput: {
    page: (params?: PageParams<AdvisorInput>) => get<PageList<AdvisorInput>>(`${BASE_URL}/advisor_input/page`, params),
    list: (params?: AdvisorInput) => get<AdvisorInput[]>(`${BASE_URL}/advisor_input/list`, params),
    create: (data: AdvisorInput) => post<AdvisorInput>(`${BASE_URL}/advisor_input`, data),
    update: (data: AdvisorInput) => put<AdvisorInput>(`${BASE_URL}/advisor_input/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/advisor_input/${id}`),
  },
  advisorRun: {
    page: (params?: PageParams<AdvisorRun>) => get<PageList<AdvisorRun>>(`${BASE_URL}/advisor_run/page`, params),
    list: (params?: AdvisorRun) => get<AdvisorRun[]>(`${BASE_URL}/advisor_run/list`, params),
    update: (data: AdvisorRun) => put<AdvisorRun>(`${BASE_URL}/advisor_run/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/advisor_run/${id}`),
    run: (type: AdvisorRunType, data: AdvisorInput) => post<AdvisorRun>(`${BASE_URL}/advisor_run/advise/${type}`, data),
  },
  intentDataset: {
    page: (params?: PageParams<Dataset>) => get<PageList<Dataset>>(`${BASE_URL}/intent_dataset/page`, params),
    list: (params?: Dataset) => get<Dataset[]>(`${BASE_URL}/intent_dataset/list`, params),
    create: (data: Dataset) => post<Dataset>(`${BASE_URL}/intent_dataset`, data),
    update: (data: Dataset) => put<Dataset>(`${BASE_URL}/intent_dataset/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/intent_dataset/${id}`),
  },
  intentInput: {
    page: (params?: PageParams<IntentInput>) => get<PageList<IntentInput>>(`${BASE_URL}/intent_input/page`, params),
    list: (params?: IntentInput) => get<IntentInput[]>(`${BASE_URL}/intent_input/list`, params),
    create: (data: IntentInput) => post<IntentInput>(`${BASE_URL}/intent_input`, data),
    update: (data: IntentInput) => put<IntentInput>(`${BASE_URL}/intent_input/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/intent_input/${id}`),
  },
  intentRun: {
    page: (params?: PageParams<IntentRun>) => get<PageList<IntentRun>>(`${BASE_URL}/intent_run/page`, params),
    list: (params?: IntentRun) => get<IntentRun[]>(`${BASE_URL}/intent_run/list`, params),
    update: (data: IntentRun) => put<IntentRun>(`${BASE_URL}/intent_run/${data.id}`, data),
    del: (id: string) => del<void>(`${BASE_URL}/intent_run/${id}`),
    run: (data: IntentInput) => post<IntentRun>(`${BASE_URL}/intent_run/intent`, data),
  },
  complexReasoning: {
    models: () => get<{ name: string; value: string }[]>(`${BASE_URL}/complex_reasoning_run/models`),
    tools: () => get<string[]>(`${BASE_URL}/complex_reasoning_run/tools`),
    systemPrompt: () => get<SystemPrompt>(`${BASE_URL}/complex_reasoning_run/system_prompt`),
    run: (data: AgentRequest) => post<AgentResponse[]>(`${BASE_URL}/complex_reasoning_run/run`, data),
    retrieve_memory: (session_id: string) =>
      get<AgentMemoryResponse>(`${BASE_URL}/complex_reasoning_run/retrieve_memory/${session_id}`),
  },
  complexReasoningDataset: {
    page: (params?: PageParams<ComplexReasoningDataset>) =>
      get<PageList<ComplexReasoningDataset>>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset/page`, params),
    list: (params?: ComplexReasoningDataset) =>
      get<ComplexReasoningDataset[]>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset/list`, params),
    create: (data: ComplexReasoningDataset) =>
      post<ComplexReasoningDataset>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset`, data),
    update: (data: ComplexReasoningDataset) =>
      put<ComplexReasoningDataset>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset/${data.id}`, data),
    copy: (dataset_id: string, dataset_item_ids?: string[]) =>
      post<ComplexReasoningDataset>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset/copy`, {
        dataset_id,
        dataset_item_ids,
      }),
    del: (id: string) => del<void>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset/${id}`),
    build: (data: DatasetBuildParams) =>
      post<ComplexReasoningDataset>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_dataset/build`, data),
  },
  complexReasoningCase: {
    page: (params?: PageParams<ComplexReasoningCase>) =>
      get<PageList<ComplexReasoningCase>>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_case/page`, params),
    list: (params?: ComplexReasoningCase) => {
      if (!params?.dataset_id) return Promise.resolve([])
      return get<ComplexReasoningCase[]>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_case/list`, params)
    },
    create: (data: ComplexReasoningCase) =>
      post<ComplexReasoningCase>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_case`, data),
    update: (data: ComplexReasoningCase) =>
      put<ComplexReasoningCase>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_case/${data.id}`, data),
    del: (id: string) => del<void>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_case/${id}`),
  },
  chatHistory: {
    list: (data?: ChatSession) =>
      get<ChatSession[]>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_chat_history/list`, data),
    get: (id: string) => get<ChatSession>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_chat_history/${id}`),
    del: (id: string) => del<void>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_chat_history/${id}`),
    eval: (data: EvaluationForm) => post<void>(`${AGENT_ARENA_BASE_URL}/complex_reasoning_chat_history/eval`, data),
  },
  task: {
    page: (params?: PageParams<Task>) => get<PageList<Task>>(`${AGENT_ARENA_BASE_URL}/task/page`, params),
    list: (params?: Task) => get<Task[]>(`${AGENT_ARENA_BASE_URL}/task/list`, params),
    create: (data: Task) => post<Task>(`${AGENT_ARENA_BASE_URL}/task`, data),
    update: (data: Task) => put<Task>(`${AGENT_ARENA_BASE_URL}/task/${data.id}`, data),
    del: (id: string) => del<void>(`${AGENT_ARENA_BASE_URL}/task/${id}`),
    run: (task_id: string) => post<TaskRun>(`${AGENT_ARENA_BASE_URL}/task/run/${task_id}`, {}),
  },
  taskRun: {
    get: (id: string) => get<TaskRun>(`${AGENT_ARENA_BASE_URL}/task_run/${id}`),
    page: (params?: PageParams<TaskRun>) => get<PageList<TaskRun>>(`${AGENT_ARENA_BASE_URL}/task_run/page`, params),
    list: (params?: TaskRun) => get<TaskRun[]>(`${AGENT_ARENA_BASE_URL}/task_run/list`, params),
    create: (data: TaskRun) => post<TaskRun>(`${AGENT_ARENA_BASE_URL}/task_run`, data),
    update: (data: TaskRun) => put<TaskRun>(`${AGENT_ARENA_BASE_URL}/task_run/${data.id}`, data),
    del: (id: string) => del<void>(`${AGENT_ARENA_BASE_URL}/task_run/${id}`),
    generateReport: (id: string) => post<void>(`${BASE_URL}/task_run/${id}/generate_report`, {}),
  },
  taskRunItem: {
    get: (id: string) => get<TaskRunItem>(`${AGENT_ARENA_BASE_URL}/task_run_item/${id}`),
    page: (params?: PageParams<TaskRunItem>) =>
      get<PageList<TaskRunItem>>(`${AGENT_ARENA_BASE_URL}/task_run_item/page`, params),
    list: (params?: TaskRunItem) => get<TaskRunItem[]>(`${AGENT_ARENA_BASE_URL}/task_run_item/list`, params),
    create: (data: TaskRunItem) => post<TaskRunItem>(`${AGENT_ARENA_BASE_URL}/task_run_item`, data),
    update: (data: TaskRunItem) => put<TaskRunItem>(`${AGENT_ARENA_BASE_URL}/task_run_item/${data.id}`, data),
    del: (id: string) => del<void>(`${AGENT_ARENA_BASE_URL}/task_run_item/${id}`),
    eval: {
      get_by_item_id: (id: string) =>
        get<TaskRunItemEval>(`${AGENT_ARENA_BASE_URL}/task_run_item/eval/get_by_item_id/${id}`),
      update: (data: TaskRunItemEval) =>
        put<TaskRunItemEval>(`${AGENT_ARENA_BASE_URL}/task_run_item/eval/${data.id}`, data),
    },
  },
}
