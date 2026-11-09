import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ConsoleState } from '../app/consoleReducer'
import {
  completedDiagnosisSummaries,
  diagnosingNodeCount,
  type PlanDagPage,
} from '../app/planDagReducer'
import type { DiagnosisDecision } from '../domain/planEvents'
import { getFocusWrapIndex } from '../utils/focus'
import {
  DagGraph,
  DIAGNOSIS_OUTCOME_LABELS,
  DIAGNOSIS_SOURCE_LABELS,
} from './DagGraph'

type PlannerPanelProps = {
  state: ConsoleState
  onSelectPage?: (pageId: string) => void
  onCollapse?: () => void
}

export const PLANNER_FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  '[contenteditable="true"]',
].join(', ')

const PAGE_STATUS_LABELS: Record<PlanDagPage['status'], string> = {
  planning: '规划中',
  running: '执行中',
  replanning: '正在重规划',
  replanned: '已被后续计划替代',
  success: '完成',
  partial: '部分完成',
  failed: '失败',
}

function stringifyEvidence(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function diagnosisDecisionSummary(decision: DiagnosisDecision): string {
  if (decision.outcome === 'replan') return decision.retryDirection
  if (decision.outcome === 'skip_unsolvable') return decision.unsolvableReason
  return decision.limitation
}

export function resolvePlannerPageSelection(
  selectedPageId: string | undefined,
  previousActivePageId: string | undefined,
  activePageId: string | undefined,
  pageIds: string[],
): string | undefined {
  const availablePageIds = new Set(pageIds)
  if (
    activePageId !== previousActivePageId
    && activePageId !== undefined
    && availablePageIds.has(activePageId)
  ) {
    return activePageId
  }
  if (selectedPageId !== undefined && availablePageIds.has(selectedPageId)) {
    return selectedPageId
  }
  return pageIds.at(-1)
}

export function PlannerPanel({ state, onSelectPage, onCollapse }: PlannerPanelProps) {
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [selectedPageId, setSelectedPageId] = useState<string>()
  const [selectedDetailNodeId, setSelectedDetailNodeId] = useState<string>()
  const pages = state.planner.pages
  const latestPageId = pages.at(-1)?.id
  const previousActivePageIdRef = useRef<string | undefined>(undefined)
  const fullscreenTriggerRef = useRef<HTMLButtonElement>(null)
  const fullscreenDialogRef = useRef<HTMLDivElement>(null)
  const fullscreenCloseRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!isFullscreen) return undefined

    fullscreenCloseRef.current?.focus()
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setIsFullscreen(false)
        return
      }
      if (event.key !== 'Tab') return

      const focusableElements = Array.from(
        fullscreenDialogRef.current?.querySelectorAll<HTMLElement>(
          PLANNER_FOCUSABLE_SELECTOR,
        ) ?? [],
      )
      const currentIndex = focusableElements.indexOf(
        document.activeElement as HTMLElement,
      )
      const wrapIndex = getFocusWrapIndex({
        currentIndex,
        focusableCount: focusableElements.length,
        backwards: event.shiftKey,
      })
      if (wrapIndex === undefined) return

      event.preventDefault()
      focusableElements[wrapIndex]?.focus()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      fullscreenTriggerRef.current?.focus()
    }
  }, [isFullscreen])

  useEffect(() => {
    const previousActivePageId = previousActivePageIdRef.current
    const activePageId = state.planner.activePageId
    previousActivePageIdRef.current = activePageId
    const pageIds = pages.map((page) => page.id)
    setSelectedPageId((current) => resolvePlannerPageSelection(
      current,
      previousActivePageId,
      activePageId,
      pageIds,
    ))
  }, [pages, state.planner.activePageId])

  const resolvedPageId = selectedPageId ?? state.planner.activePageId ?? latestPageId
  const matchedPageIndex = pages.findIndex((page) => page.id === resolvedPageId)
  const selectedPageIndex = matchedPageIndex >= 0
    ? matchedPageIndex
    : Math.max(0, pages.length - 1)
  const selectedPage = pages[selectedPageIndex]
  const isHistoricalPage = selectedPage !== undefined && selectedPage.id !== latestPageId
  const selectedPageDiagnosingNodeCount = selectedPage
    ? diagnosingNodeCount(selectedPage)
    : 0
  const selectedPageDiagnosisSummaries = selectedPage
    ? completedDiagnosisSummaries(selectedPage)
    : []
  const canGoPrevious = selectedPageIndex > 0
  const canGoNext = selectedPageIndex >= 0 && selectedPageIndex < pages.length - 1
  const requestMessageIds = useMemo(
    () => [...new Set(pages.map((page) => page.messageId))],
    [pages],
  )
  const requestIndex = selectedPage
    ? requestMessageIds.indexOf(selectedPage.messageId)
    : -1
  const requestPages = selectedPage
    ? pages.filter((page) => page.messageId === selectedPage.messageId)
    : []
  const roundIndex = selectedPage
    ? requestPages.findIndex((page) => page.id === selectedPage.id)
    : -1

  useEffect(() => {
    setSelectedDetailNodeId(undefined)
  }, [selectedPage?.id])

  const goToPage = useCallback((offset: number) => {
    if (pages.length === 0) return
    const nextIndex = Math.min(Math.max(selectedPageIndex + offset, 0), pages.length - 1)
    const nextPageId = pages[nextIndex].id
    setSelectedDetailNodeId(undefined)
    setSelectedPageId(nextPageId)
    onSelectPage?.(nextPageId)
  }, [onSelectPage, pages, selectedPageIndex])

  const renderPageSwitcher = () => {
    if (pages.length <= 1) return null
    return (
      <nav className="dag-page-switcher" aria-label={`计划轮次切换，当前 ${selectedPage?.title}`}>
        <button
          aria-label="上一轮计划"
          className="dag-page-button"
          type="button"
          disabled={!canGoPrevious}
          onClick={() => goToPage(-1)}
        >
          &lt;
        </button>
        <span className="dag-page-indicator">
          请求 {requestIndex + 1} · Round {roundIndex + 1} / {requestPages.length}
        </span>
        <button
          aria-label="下一轮计划"
          className="dag-page-button"
          type="button"
          disabled={!canGoNext}
          onClick={() => goToPage(1)}
        >
          &gt;
        </button>
      </nav>
    )
  }

  const renderRoundEvidence = () => {
    if (!selectedPage) return null
    const runnerErrorKeys = new Set(
      selectedPage.runnerErrors.map((error) => JSON.stringify(error)),
    )
    const distinctRoundErrors = selectedPage.roundErrors.filter(
      (error) => !runnerErrorKeys.has(JSON.stringify(error)),
    )
    const hasEvidence =
      selectedPage.runnerErrors.length > 0
      || distinctRoundErrors.length > 0
      || Boolean(selectedPage.repairPolicy)
      || Boolean(selectedPage.finish?.reason)
      || selectedPageDiagnosisSummaries.length > 0
    if (!hasEvidence) return null
    return (
      <section className="plan-round-evidence" aria-label="重规划证据">
        <strong>重规划证据</strong>
        <dl>
          <div><dt>策略</dt><dd>{selectedPage.repairPolicy ?? '无'}</dd></div>
          <div>
            <dt>Runner 错误</dt>
            <dd><pre>{stringifyEvidence(selectedPage.runnerErrors)}</pre></dd>
          </div>
          <div>
            <dt>Round 错误</dt>
            <dd><pre>{stringifyEvidence(distinctRoundErrors)}</pre></dd>
          </div>
          <div><dt>结束原因</dt><dd>{selectedPage.finish?.reason ?? '无'}</dd></div>
        </dl>
        {selectedPageDiagnosisSummaries.length > 0 && (
          <section className="plan-diagnosis-summaries" aria-label="最终裁决">
            <strong>最终裁决</strong>
            <div className="plan-diagnosis-summary-list">
              {selectedPageDiagnosisSummaries.map((summary) => (
                <button
                  className="plan-diagnosis-summary-button"
                  key={`${summary.stepId}:${summary.completedAt}`}
                  type="button"
                  onClick={() => setSelectedDetailNodeId(summary.stepId)}
                >
                  <span className="plan-diagnosis-summary-meta">
                    <strong>{summary.stepId}</strong>
                    <span>{DIAGNOSIS_SOURCE_LABELS[summary.source]}</span>
                    <span>{DIAGNOSIS_OUTCOME_LABELS[summary.outcome]}</span>
                  </span>
                  <span className="plan-diagnosis-summary-decision">
                    {diagnosisDecisionSummary(summary.decision)}
                  </span>
                </button>
              ))}
            </div>
          </section>
        )}
      </section>
    )
  }

  const renderDagGraph = (className = 'dag-flow-container') => {
    if (!selectedPage) {
      return (
        <div className={className}>
          <div className="empty-copy dag-empty">ReAct 模式或当前会话尚未产生 Plan DAG</div>
        </div>
      )
    }
    const graphClassName = isHistoricalPage
      ? `${className} diagnosis-animation-disabled`
      : className
    const hasGraph = selectedPage.nodes.length > 0
    const hasError =
      selectedPage.status === 'failed'
      || selectedPage.runnerErrors.length > 0
      || selectedPage.roundErrors.length > 0
    if (!hasGraph && hasError) {
      return (
        <div className={graphClassName}>
          <div className="dag-error-card" role="status">
            <span className="dag-error-label">Plan 执行失败</span>
            <pre>{stringifyEvidence({
              runnerErrors: selectedPage.runnerErrors,
              roundErrors: selectedPage.roundErrors,
              finish: selectedPage.finish,
            })}</pre>
          </div>
        </div>
      )
    }
    return (
      <div className={graphClassName}>
        <DagGraph
          nodes={selectedPage.nodes}
          edges={selectedPage.edges}
          goal={selectedPage.goal}
          selectedDetailNodeId={selectedDetailNodeId}
          onSelectedDetailNodeIdChange={setSelectedDetailNodeId}
        />
      </div>
    )
  }

  const renderContent = (className?: string) => (
    <>
      {renderRoundEvidence()}
      {renderDagGraph(className)}
    </>
  )

  return (
    <section className="panel planner-panel">
      <header className="panel-header compact">
        <div>
          <p className="eyebrow">plan dag</p>
          <h2>任务如何展开</h2>
          {selectedPage && (
            <span className="plan-page-status-row">
              <span className={`plan-page-status status-${selectedPage.status}`}>
                {PAGE_STATUS_LABELS[selectedPage.status]}
              </span>
              {selectedPageDiagnosingNodeCount > 0 && (
                <span className="plan-diagnosing-count">
                  {selectedPageDiagnosingNodeCount} 个节点诊断中
                </span>
              )}
            </span>
          )}
        </div>
        <div className="dag-panel-actions">
          {renderPageSwitcher()}
          <button
            ref={fullscreenTriggerRef}
            aria-label="全屏查看任务拆解 DAG"
            className="dag-fullscreen-toggle"
            type="button"
            onClick={() => setIsFullscreen(true)}
          >
            全屏
          </button>
          {onCollapse && (
            <button
              aria-label="收起任务拆解面板"
              className="dag-fullscreen-toggle planner-collapse-toggle"
              type="button"
              title="收起"
              onClick={onCollapse}
            >
              收起 ›
            </button>
          )}
        </div>
      </header>
      {renderContent()}
      {isFullscreen && (
        <div
          ref={fullscreenDialogRef}
          className="dag-fullscreen-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="任务拆解 DAG 全屏视图"
        >
          <section className="dag-fullscreen-panel">
            <header className="dag-fullscreen-header">
              <div>
                <p className="eyebrow">plan dag</p>
                <h2>任务如何展开</h2>
              </div>
              <div className="dag-panel-actions">
                {renderPageSwitcher()}
                <button
                  ref={fullscreenCloseRef}
                  aria-label="退出任务拆解 DAG 全屏"
                  className="dag-fullscreen-close"
                  type="button"
                  onClick={() => setIsFullscreen(false)}
                >
                  退出
                </button>
              </div>
            </header>
            {renderContent('dag-flow-container dag-flow-fullscreen')}
          </section>
        </div>
      )}
    </section>
  )
}
