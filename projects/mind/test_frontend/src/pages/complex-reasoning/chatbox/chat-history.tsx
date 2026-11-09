import React from 'react'
import { Button, Empty, List } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import Api from '@/apis/task-data'
import styles from './index.module.less'
import ExDeleteButton from '@/components/DeleteButton'

export type HandleType = {
  loadChatSessions: () => void
}

type Props = {
  value?: string
  onChange?: (chatSession?: ChatSession) => void
  list?: ChatSession[]
  onCreate?: () => void
  ref: React.Ref<HandleType>
  onDeleteSuccess?: () => void
}

const App: React.FC<Props> = ({ value, onChange, onCreate, list = [], onDeleteSuccess }) => {
  return (
    <>
      <div className={styles.chatHistory}>
        <div className={styles.historyHeader}>
          <Button type="primary" ghost block icon={<PlusOutlined />} onClick={onCreate}>
            新建会话
          </Button>
        </div>

        {/* <Divider className={styles.divider} /> */}
        <div className={styles.sessionList}>
          {list.length === 0 ? (
            <Empty style={{ marginTop: 120 }} description="暂无会话历史" />
          ) : (
            <List
              dataSource={list}
              renderItem={(session) => (
                <div
                  key={session.id}
                  className={`${styles.sessionItem} ${value === session.id ? styles.active : ''}`}
                  onClick={() => onChange?.(session)}
                >
                  <div className={styles.sessionName}>
                    {session.title}
                    {/* <Tag>张晓明</Tag> */}
                  </div>
                  {session.id !== value && (
                    <div className={styles.sessionAction} onClick={(e) => e.stopPropagation()}>
                      <ExDeleteButton id={session?.id} API={Api.chatHistory.del} onSuccess={onDeleteSuccess}>
                        <DeleteOutlined style={{ color: 'red' }} />
                      </ExDeleteButton>
                    </div>
                  )}
                </div>
              )}
            />
          )}
        </div>
      </div>
    </>
  )
}

export default App
