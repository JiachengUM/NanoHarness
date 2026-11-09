import React from 'react'
import { Button, Typography } from 'antd'
import { FullscreenOutlined } from '@ant-design/icons'
import styles from './index.module.less'

const V2_AGENT_APP_PATH = '/v2-agent/'

const V2AgentExperience: React.FC = () => {
  return (
    <section className={styles.page}>
      <header className={styles.header}>
        <div className={styles.heading}>
          <Typography.Title className={styles.title} level={4}>
            v2 Agent 体验
          </Typography.Title>
          <Typography.Text type="secondary">
            当前页面直接运行现有 v2 Agent，文本、任务与语音链路均连接线上服务。
          </Typography.Text>
        </div>
        <Button
          href={V2_AGENT_APP_PATH}
          target="_blank"
          rel="noreferrer"
          icon={<FullscreenOutlined />}
        >
          全屏打开
        </Button>
      </header>
      <iframe
        className={styles.frame}
        src={V2_AGENT_APP_PATH}
        title="v2 Agent 体验"
        allow="microphone; autoplay"
      />
    </section>
  )
}

export default V2AgentExperience
