import { Component, type PropsWithChildren } from 'react'

export default class DataErrorBoundary extends Component<PropsWithChildren, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (this.state.failed) return <main className="app-shell" role="alert">
      <h1>ASX Income Radar</h1>
      <p>市场数据无法显示。请刷新页面重试；若仍失败，请重新生成数据快照。</p>
      <button type="button" onClick={() => window.location.reload()}>刷新页面</button>
    </main>
    return this.props.children
  }
}
