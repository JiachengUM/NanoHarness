export type CapabilityExperienceId = 'progress' | 'cancel' | 'modify'

export type CapabilityExperience = {
  id: CapabilityExperienceId
  title: string
  summary: string
  architecture: string
  prompts: string[]
}

export const CAPABILITY_EXPERIENCES: CapabilityExperience[] = [
  {
    id: 'progress',
    title: '随时问进度',
    summary: '不用干等结果，任务运行时直接问一句“查到哪了？”。',
    architecture: 'Task Manager 持续维护当前任务状态。',
    prompts: [
      '帮我查一下上海静安寺附近的酒店。',
      '刚刚酒店查到哪了？',
    ],
  },
  {
    id: 'cancel',
    title: '取消指定任务',
    summary: '同时查多件事时，不明确会先确认，不会误停其它任务。',
    architecture: '按任务名称和查询条件匹配，不明确时先确认。',
    prompts: [
      '同时帮我查上海明天的天气和上海的酒店。',
      '上海那个不用查了。',
      '酒店。',
    ],
  },
  {
    id: 'modify',
    title: '直接修改条件',
    summary: '只说要改什么，其余条件会从原任务继续继承。',
    architecture: '结合原任务上下文，继承已有条件并处理新的修改。',
    prompts: [
      '帮我查一下香港尖沙咀附近的酒店。',
      '换成上海的，要安静一点，人均 100 左右。',
    ],
  },
]

type CapabilityGuideProps = {
  variant: 'empty' | 'popover'
  disabled?: boolean
  onClose: () => void
  onTry: (experience: CapabilityExperience) => void
}

function CapabilityIcon({ id }: { id: CapabilityExperienceId }) {
  if (id === 'progress') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="7.5" />
        <path d="M12 7.8v4.6l3 1.8M8.6 3.8 6.8 5.6" />
      </svg>
    )
  }

  if (id === 'cancel') {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="7.5" />
        <path d="m9.4 9.4 5.2 5.2m0-5.2-5.2 5.2" />
      </svg>
    )
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5.5 8.5A7.5 7.5 0 0 1 18 6.8l1.6 1.7" />
      <path d="M19.5 4.8v3.7h-3.7M18.5 15.5A7.5 7.5 0 0 1 6 17.2l-1.6-1.7" />
      <path d="M4.5 19.2v-3.7h3.7" />
    </svg>
  )
}

export function CapabilityGuide({
  variant,
  disabled = false,
  onClose,
  onTry,
}: CapabilityGuideProps) {
  const titleId = `capability-guide-title-${variant}`

  return (
    <section
      aria-labelledby={titleId}
      aria-modal={variant === 'popover' ? false : undefined}
      className={`capability-guide capability-guide-${variant}`}
      id="capability-guide-surface"
      role={variant === 'popover' ? 'dialog' : undefined}
    >
      <header className="capability-guide-header">
        <div className="capability-guide-heading">
          <span className="capability-spark" aria-hidden="true">✦</span>
          <div>
            <p className="capability-guide-kicker">能力升级</p>
            <h3 id={titleId}>任务开始后，也可以继续聊</h3>
          </div>
        </div>
        <button
          aria-label="收起能力介绍"
          className="capability-guide-close"
          title="收起"
          type="button"
          onClick={onClose}
        >
          <svg viewBox="0 0 20 20" aria-hidden="true">
            <path d="m6 6 8 8m0-8-8 8" />
          </svg>
        </button>
      </header>

      <p className="capability-guide-intro">
        不必干等。随时问进度、取消其中一个任务，或直接修改已经说过的条件。
      </p>

      <div className="capability-list">
        {CAPABILITY_EXPERIENCES.map((experience) => (
          <article className="capability-item" key={experience.id}>
            <span className={`capability-icon capability-icon-${experience.id}`}>
              <CapabilityIcon id={experience.id} />
            </span>
            <div className="capability-item-copy">
              <strong>{experience.title}</strong>
              <span>{experience.summary}</span>
            </div>
            <button
              className="capability-try"
              disabled={disabled}
              type="button"
              onClick={() => onTry(experience)}
            >
              {disabled ? '连接后体验' : '体验'}
            </button>
          </article>
        ))}
      </div>

      <details className="capability-details">
        <summary>为什么它能做到</summary>
        <ul>
          {CAPABILITY_EXPERIENCES.map((experience) => (
            <li key={experience.id}>
              <strong>{experience.title}：</strong>
              {experience.architecture}
            </li>
          ))}
        </ul>
      </details>
    </section>
  )
}
