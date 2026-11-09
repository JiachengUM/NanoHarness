import { useEffect, useRef, type MutableRefObject, type RefObject } from 'react'
import { type CaseBlock } from './run-state'

const NEAR_BOTTOM_PX = 96

function wasStuckToBottom(element: HTMLElement, prevScrollHeight: number, threshold = NEAR_BOTTOM_PX): boolean {
  // 内容增高后 scrollTop 不变，会“离开”底部；要用增高前的高度判断当时是否贴底
  return element.scrollTop + element.clientHeight >= prevScrollHeight - threshold
}

export function resolveFollowCaseIndex(
  cases: CaseBlock[],
  activeCaseIndex: number | null,
): number | null {
  if (activeCaseIndex != null) {
    return activeCaseIndex
  }
  const running = cases.find((item) => item.status === 'running')
  if (running) {
    return running.index
  }
  const waiting = cases.find((item) => item.status === 'waiting')
  if (waiting) {
    return waiting.index
  }
  return cases[cases.length - 1]?.index ?? null
}

export function buildLiveTailToken(caseBlock: CaseBlock | undefined): string {
  if (!caseBlock) {
    return ''
  }
  const lastTurn = caseBlock.turns[caseBlock.turns.length - 1]
  return [
    caseBlock.status,
    caseBlock.turns.length,
    lastTurn?.id,
    lastTurn?.sessionId,
    lastTurn?.fakePerson,
    lastTurn?.agentPartial,
    lastTurn?.agentFinal,
    lastTurn?.listening,
    caseBlock.verdict?.status,
    caseBlock.error,
  ].join('\u0001')
}

type ScrollOptions = {
  behavior: ScrollBehavior
  force: boolean
}

type ScrollRefs = {
  timelineRef: RefObject<HTMLDivElement | null>
  turnListRefs: MutableRefObject<Record<number, HTMLDivElement | null>>
  liveTailRefs: MutableRefObject<Record<number, HTMLDivElement | null>>
  cardRefs: MutableRefObject<Record<number, HTMLDivElement | null>>
}

type PrevHeights = {
  timeline: number
  turnList: Record<number, number>
}

function scrollToLiveBottom(
  caseIndex: number,
  refs: ScrollRefs,
  prevHeights: MutableRefObject<PrevHeights>,
  options: ScrollOptions,
) {
  const { behavior, force } = options
  const timeline = refs.timelineRef.current
  const turnList = refs.turnListRefs.current[caseIndex]
  const tail = refs.liveTailRefs.current[caseIndex]
  const prev = prevHeights.current

  const stickTimeline =
    Boolean(timeline) && (force || wasStuckToBottom(timeline!, prev.timeline || timeline!.scrollHeight))
  const prevTurn = prev.turnList[caseIndex] ?? turnList?.scrollHeight ?? 0
  const stickTurnList = Boolean(turnList) && (force || wasStuckToBottom(turnList!, prevTurn))

  // 单测：主滚动在 caseDetailMain；批量：主滚动在 timeline。两边都跟，谁溢出谁动。
  if (stickTurnList && turnList) {
    turnList.scrollTo({ top: turnList.scrollHeight, behavior })
  }
  if (stickTimeline && timeline && tail) {
    tail.scrollIntoView({ behavior, block: 'end' })
  }

  if (timeline) {
    prev.timeline = timeline.scrollHeight
  }
  if (turnList) {
    prev.turnList[caseIndex] = turnList.scrollHeight
  }
}

function scheduleScroll(run: () => void): () => void {
  // 双 rAF：等本帧 DOM/布局写完再滚，避免流式增高后仍停在旧高度
  let outer = 0
  let inner = 0
  outer = requestAnimationFrame(() => {
    inner = requestAnimationFrame(run)
  })
  return () => {
    cancelAnimationFrame(outer)
    cancelAnimationFrame(inner)
  }
}

export function useLiveConversationScroll(
  cases: CaseBlock[],
  activeCaseIndex: number | null,
  scrollToIndex: number | null | undefined,
  multiCase: boolean,
) {
  const timelineRef = useRef<HTMLDivElement>(null)
  const turnListRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const liveTailRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const prevHeights = useRef<PrevHeights>({ timeline: 0, turnList: {} })

  const followCaseIndex = resolveFollowCaseIndex(cases, activeCaseIndex)
  const followCase = followCaseIndex == null ? undefined : cases.find((item) => item.index === followCaseIndex)
  const liveTailToken = buildLiveTailToken(followCase)

  const refs: ScrollRefs = {
    timelineRef,
    turnListRefs,
    liveTailRefs,
    cardRefs,
  }

  useEffect(() => {
    if (!liveTailToken || followCaseIndex == null) {
      return
    }
    return scheduleScroll(() => {
      scrollToLiveBottom(followCaseIndex, refs, prevHeights, { behavior: 'auto', force: false })
    })
  }, [liveTailToken, followCaseIndex, multiCase])

  useEffect(() => {
    if (scrollToIndex == null) {
      return
    }
    return scheduleScroll(() => {
      // 切入 case 时强制跟到底部，避免只停在卡片标题
      scrollToLiveBottom(scrollToIndex, refs, prevHeights, { behavior: 'smooth', force: true })
    })
  }, [scrollToIndex, multiCase])

  return {
    timelineRef,
    turnListRefs,
    liveTailRefs,
    cardRefs,
  }
}
