import { Component, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { hasError: boolean; error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-canvas p-6">
          <div className="text-center max-w-sm">
            <div className="text-6xl mb-4 text-textMuted/30 font-bold">⚠</div>
            <h1 className="text-xl font-semibold text-textPrimary mb-2">出错了</h1>
            <p className="text-sm text-textMuted mb-6 leading-relaxed">
              应用发生了意外错误。请刷新页面重试，或联系管理员。
            </p>
            <div className="flex items-center justify-center gap-3">
              <button
                onClick={() => window.location.reload()}
                className="px-5 py-2.5 rounded-xl bg-primary-500 text-white hover:bg-primary-400 transition-colors text-sm font-medium"
              >
                刷新页面
              </button>
              <button
                onClick={() => this.setState({ hasError: false, error: null })}
                className="px-5 py-2.5 rounded-xl border border-border text-textSecondary hover:bg-elevated transition-colors text-sm"
              >
                重试
              </button>
            </div>
            {this.state.error && (
              <details className="mt-6 text-left">
                <summary className="text-xs text-textMuted cursor-pointer hover:text-textSecondary">错误详情</summary>
                <pre className="mt-2 text-[11px] text-textMuted bg-elevated rounded-lg p-3 overflow-auto max-h-40 whitespace-pre-wrap">
                  {this.state.error.message}
                  {this.state.error.stack}
                </pre>
              </details>
            )}
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
