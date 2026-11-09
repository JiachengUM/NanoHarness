import React from 'react'
import { message } from 'antd'

type MessageInstance = ReturnType<typeof message.useMessage>[0]

export const MessageContext = React.createContext<MessageInstance>(null!)
