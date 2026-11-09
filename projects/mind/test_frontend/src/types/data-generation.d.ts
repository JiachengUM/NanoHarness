interface PlatformPageParams {
  page?: number
  page_size?: number
}

interface PlatformPageList<T> {
  page: number
  page_size: number
  pages: number
  total: number
  items: T[]
}

interface GenerationTask extends Common {
  name?: string
  description?: string
}

interface TagTreeBrief extends Common {
  name: string
  description?: string
  createdAt?: string
  updatedAt?: string
}

interface TagTreeDetail extends TagTreeBrief {
  tree: object
}

type ScenarioPlanStatus = 'pending' | 'confirmed' | 'generating' | 'completed' | 'cancelled'

interface ScenarioPlan extends Common {
  task_id: string
  original_query: string
  task_description: string
  target_tags: string[]
  interpretation_notes: string
  status: ScenarioPlanStatus
  tag_tree_name: string
}

interface GenerationScenario extends Common {
  scenario_id: string
  scenario_name: string
  description: string
  tags: string[]
  tag_tree_id?: string
  generation_task_id?: string
  source_query?: string
}

interface GenerateScenarioRequest {
  query: string
  tagTreeName: string
  generationTaskId?: string
  saveToDb: boolean
  temperature?: number
}

interface GenerateScenarioResult {
  scenarios: GenerationScenario[]
  count: number
}

interface GeneratedCase extends ComplexReasoningCase {
  source_scenario_id?: string
  source_scenario_name?: string
}

interface GenerateCasesRequest {
  scenarioIds: string[]
  datasetId: string
  casesPerScenario: number
  tagTreeName: string
}

interface GenerateCasesResult {
  cases: GeneratedCase[]
  totalGenerated: number
  errors?: Array<{
    scenarioId: string
    error: string
  }>
}

interface ScenarioGenerationProgress {
  iteration: number
  batchSize: number
  totalScenarios: number
  targetScenarioCount: number
  progressPercentage: number
  coveragePercentage: number
  satisfied: boolean
  stage?: string
  currentStep?: string
  stepProgress?: number
}

interface CaseGenerationProgress {
  stage?: string
  current: number
  total: number
  progressPercentage: number
  currentStep: string
  currentScenarioName?: string
}

type ScenarioStreamEvent =
  | {
      type: 'plan'
      data: {
        scenarioPlanId: string
        target_tags: string[]
        task_description: string
        interpretation_notes: string
      }
    }
  | {
      type: 'patterns'
      data: {
        patterns: string[]
      }
    }
  | {
      type: 'progress'
      data: ScenarioGenerationProgress
    }
  | {
      type: 'scenario'
      data: {
        scenario: GenerationScenario
        iteration: number
        totalScenarios: number
        targetScenarioCount: number
        progressPercentage: number
        coveragePercentage: number
      }
    }
  | {
      type: 'complete'
      data: {
        scenarioPlanId: string | null
        targetCount: number
        actualCount: number
        achievementRate: number
        totalIterations: number
        finalCoveragePercentage: number
        satisfied: boolean
      }
    }
  | {
      type: 'error'
      data: {
        message: string
        code?: string
      }
    }

type CaseStreamEvent =
  | {
      type: 'progress'
      data: CaseGenerationProgress
    }
  | {
      type: 'case'
      data: {
        caseItem: GeneratedCase & {
          _saved?: boolean
          _saveError?: string | null
        }
        scenarioId: string
        scenarioName: string
        iteration: number
        totalPassedCases: number
      }
    }
  | {
      type: 'complete'
      data: {
        totalGenerated: number
        totalScenarios: number
        casesPerScenario: number
      }
    }
  | {
      type: 'error'
      data: {
        message: string
        code?: string
      }
    }
