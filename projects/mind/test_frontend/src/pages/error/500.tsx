import React from 'react'
import { Button, Result } from 'antd'

const App: React.FC = () => (
  <Result
    status="500"
    title="500"
    subTitle="抱歉，您访问的页面发生错误！"
    extra={
      <Button type="primary" href="/">
        回到首页
      </Button>
    }
  />
)

export default App
