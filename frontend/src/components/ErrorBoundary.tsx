import { Component, type ReactNode } from 'react'

// Shows `fallback` instead of unmounting the whole app when a child throws
// (e.g. the lazily loaded PDF viewer fails to download).
export default class ErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
