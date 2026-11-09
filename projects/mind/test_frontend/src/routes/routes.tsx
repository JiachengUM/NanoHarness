import {
  SendOutlined,
  DatabaseOutlined,
  ProfileOutlined,
  ExperimentOutlined,
  CarryOutOutlined,
  MoreOutlined,
} from '@ant-design/icons'

export type RouteItem = {
  name: string
  path: string
  index?: boolean
  icon?: React.ReactNode
  permCode?: string
  element?: React.ReactNode
  children?: RouteItem[]
  hiddenInMenu?: boolean // 菜单中隐藏
}

import { lazy } from 'react'

export const pages = {
  Error403: lazy(() => import('@/pages/error/403')),
  Error404: lazy(() => import('@/pages/error/404')),
  Home: lazy(() => import('@/pages/advisor')),
  Intent: lazy(() => import('@/pages/intent')),
  DomainUser: lazy(() => import('@/pages/domain-data/user')),
  DomainVehicleState: lazy(() => import('@/pages/domain-data/vehicle-state')),
  DomainVisualInterior: lazy(() => import('@/pages/domain-data/visual-interior')),
  DomainVisualExterior: lazy(() => import('@/pages/domain-data/visual-exterior')),
  DomainWorldInfo: lazy(() => import('@/pages/domain-data/world-info')),
  DomainMemory: lazy(() => import('@/pages/domain-data/memory')),
  DomainContextLog: lazy(() => import('@/pages/domain-data/context-log')),
  IntentCategory: lazy(() => import('@/pages/intent-data/category')),
  AdvisorDataset: lazy(() => import('@/pages/dataset/advisor')),
  AdvisorInput: lazy(() => import('@/pages/dataset/advisor/advisor-input')),
  IntentDataset: lazy(() => import('@/pages/dataset/intent')),
  IntentInput: lazy(() => import('@/pages/dataset/intent/intent-input')),
  ComplexReasoningDataset: lazy(() => import('@/pages/dataset/complex-reasoning')),
  ComplexReasoningCase: lazy(() => import('@/pages/dataset/complex-reasoning/complex-reasoning-input')),
  AdvisorRun: lazy(() => import('@/pages/advisor-run')),
  IntentRun: lazy(() => import('@/pages/intent-run')),
  ComplexReasoning: lazy(() => import('@/pages/complex-reasoning')),
  ComplexReasoningChat: lazy(() => import('@/pages/complex-reasoning/chatbox')),
  VoiceTest: lazy(() => import('@/pages/voice-test')),
  VoiceTestDzy: lazy(() => import('@/pages/voice-test/dzy-index')),
  V2AgentExperience: lazy(() => import('@/pages/v2-agent-experience')),
  Task: lazy(() => import('@/pages/task/task')),
  TaskRun: lazy(() => import('@/pages/task/task-run')),
  TaskRunItem: lazy(() => import('@/pages/task/task-run-item')),
  GenerationTask: lazy(() => import('@/pages/data-generation/task')),
  GenerationScenario: lazy(() => import('@/pages/data-generation/scenario')),
  TagTree: lazy(() => import('@/pages/data-generation/tag-tree')),
  CaseGeneration: lazy(() => import('@/pages/data-generation/case-generation')),
}

export const routes: RouteItem[] = [
  {
    name: '首页',
    path: '',
    index: true,
    hiddenInMenu: true,
  },
  {
    name: '数据管理',
    path: 'data',
    icon: <DatabaseOutlined />,
    children: [
      {
        name: '测试数据集',
        path: 'complex-reasoning-dataset',
        element: <pages.ComplexReasoningDataset />,
      },
      {
        name: '测试用例',
        path: 'complex-reasoning-dataset/:dataset_id',
        element: <pages.ComplexReasoningCase />,
        hiddenInMenu: true,
      },
    ],
  },
  {
    name: '数据合成',
    path: 'data-generation',
    icon: <ExperimentOutlined />,
    children: [
      {
        name: '管理数据合成任务',
        path: 'task',
        element: <pages.GenerationTask />,
      },
      {
        name: '场景',
        path: 'task/:taskId/scenarios',
        element: <pages.GenerationScenario />,
        hiddenInMenu: true,
      },
      {
        name: '管理测试维度',
        path: 'tag-tree',
        element: <pages.TagTree />,
      },
      {
        name: '开始数据合成',
        path: 'case-generation',
        element: <pages.CaseGeneration />,
      },
    ],
  },
  {
    name: '测试工具',
    path: 'test-tools',
    icon: <SendOutlined />,
    children: [
      {
        name: 'Agent对话',
        path: 'agent-chat',
        element: <pages.ComplexReasoningChat />,
      },
      {
        name: 'v2 Agent 体验',
        path: 'v2-agent',
        element: <pages.V2AgentExperience />,
      },
      {
        name: '自动测试',
        path: 'voice-test',
        element: <pages.VoiceTest />,
      },
      // {
      //   name: '自动测试（新版）',
      //   path: 'voice-test-dzy',
      //   element: <pages.VoiceTestDzy />,
      // },
    ],
  },
  {
    name: '测试任务',
    path: 'task',
    icon: <CarryOutOutlined />,
    children: [
      {
        name: '任务列表',
        path: 'task',
        element: <pages.Task />,
      },
      {
        name: '运行记录',
        path: 'task-run',
        element: <pages.TaskRun />,
      },
      {
        name: '任务运行详情',
        path: 'task-run/:task_run_id',
        element: <pages.TaskRunItem />,
        hiddenInMenu: true,
      },
    ],
  },
  {
    name: '其他',
    path: 'other',
    icon: <MoreOutlined />,
    children: [
      {
        name: 'Advisor',
        path: '',
        index: true,
        icon: <SendOutlined />,
        element: <pages.Home />,
      },
      {
        name: '意图识别',
        path: 'intent',
        icon: <SendOutlined />,
        element: <pages.Intent />,
      },
      {
        name: '复杂推理',
        path: 'complex-reasoning',
        icon: <SendOutlined />,
        element: <pages.ComplexReasoning />,
      },
      {
        name: '数据管理',
        path: 'data',
        icon: <DatabaseOutlined />,
        children: [
          {
            name: 'Advisor数据集',
            path: 'advisor-dataset',
            element: <pages.AdvisorDataset />,
          },
          {
            name: '测试用例',
            path: 'advisor-dataset/:dataset_id',
            element: <pages.AdvisorInput />,
            hiddenInMenu: true,
          },
          {
            name: 'Intent数据集',
            path: 'intent-dataset',
            element: <pages.IntentDataset />,
          },
          {
            name: '测试用例',
            path: 'intent-dataset/:dataset_id',
            element: <pages.IntentInput />,
            hiddenInMenu: true,
          },
        ],
      },
      {
        name: '测试记录',
        path: 'run',
        icon: <ProfileOutlined />,
        children: [
          {
            name: 'Advisor记录',
            path: 'advisor',
            element: <pages.AdvisorRun />,
          },
          {
            name: 'Intent记录',
            path: 'intent',
            element: <pages.IntentRun />,
          },
        ],
      },
      {
        name: 'domain-data',
        path: 'domain-data',
        icon: <DatabaseOutlined />,
        children: [
          {
            name: '用户画像',
            path: 'user',
            element: <pages.DomainUser />,
          },
          {
            name: '记忆信息',
            path: 'memory',
            element: <pages.DomainMemory />,
          },
          {
            name: '车辆状态',
            path: 'vehicle-state',
            element: <pages.DomainVehicleState />,
          },
          {
            name: '内部视觉',
            path: 'visual-interior',
            element: <pages.DomainVisualInterior />,
          },
          {
            name: '外部视觉',
            path: 'visual-exterior',
            element: <pages.DomainVisualExterior />,
          },
          {
            name: '世界信息',
            path: 'world-info',
            element: <pages.DomainWorldInfo />,
          },
          {
            name: '实车日志',
            path: 'context-log',
            element: <pages.DomainContextLog />,
          },
        ],
      },
      {
        name: 'intent-data',
        path: 'intent-data',
        icon: <DatabaseOutlined />,
        children: [
          {
            name: '意图分类',
            path: 'category',
            element: <pages.IntentCategory />,
          },
        ],
      },
    ],
  },
]
