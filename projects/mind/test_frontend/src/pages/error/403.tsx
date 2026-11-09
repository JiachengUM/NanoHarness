import React from 'react'
import { Button, Result } from 'antd'

const App: React.FC = () => (
  <Result
    status="403"
    title="403"
    subTitle="抱歉，您无权访问该页面！"
    extra={
      <Button type="primary" href="/">
        回到首页
      </Button>
    }
  />
)

export default App
