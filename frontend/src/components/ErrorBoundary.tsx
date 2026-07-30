import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertCircle, RefreshCw, Home, RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: unknown): State {
    const normalized =
      error instanceof Error ? error : new Error(String(error))
    return { hasError: true, error: normalized }
  }

  componentDidCatch(error: unknown, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary] Caught error:', error)
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack)
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  handleReload = () => {
    window.location.reload()
  }

  handleHome = () => {
    window.location.href = '/'
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen bg-[var(--bg)] flex items-center justify-center p-6"
          role="alert"
        >
          <div className="max-w-md w-full bg-[var(--surface-elevated)] rounded-2xl border border-[var(--border)] p-8 text-center space-y-5">
            <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center mx-auto">
              <AlertCircle className="w-6 h-6 text-red-500" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                Something went wrong
              </h2>
              <p className="text-sm text-[var(--text-secondary)] mt-2">
                An unexpected error occurred. Try reloading the page.
              </p>
            </div>
            {import.meta.env.DEV && this.state.error?.message && (
              <pre className="text-xs text-[var(--text-muted)] bg-[var(--surface)] rounded-lg p-3 overflow-x-auto text-left max-h-32 overflow-y-auto border border-[var(--border)]">
                {this.state.error.message}
              </pre>
            )}
            <div className="flex gap-3 justify-center flex-wrap">
              <button
                type="button"
                onClick={this.handleReset}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent)]/90 transition-colors focus-ring min-h-[44px]"
              >
                <RotateCcw className="w-4 h-4" aria-hidden="true" />
                Try Again
              </button>
              <button
                type="button"
                onClick={this.handleReload}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] text-sm font-medium hover:text-[var(--text-primary)] transition-colors focus-ring min-h-[44px]"
              >
                <RefreshCw className="w-4 h-4" aria-hidden="true" />
                Reload Page
              </button>
              <button
                type="button"
                onClick={this.handleHome}
                className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] text-sm font-medium hover:text-[var(--text-primary)] transition-colors focus-ring min-h-[44px]"
              >
                <Home className="w-4 h-4" aria-hidden="true" />
                Go Home
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
