// frontend/src/components/ErrorBoundary.jsx
//
// React ErrorBoundary — App.jsx 顶层包一层，渲染异常不再白屏。
//
// 触发条件：
//   · 组件 render 抛错（属性 undefined / map 在 null 上 / etc.）
//   · 组件 lifecycle / commit phase 抛错
// 不会捕获：
//   · 事件 handler 里的 throw（async 不会冒泡到 boundary）
//   · setTimeout / Promise.reject 里的错（这俩到 window.onerror）
//   · SSR 阶段的错（boundary 只在客户端 render）
//
// 兜底界面用静态 HTML（不依赖任何 React 上下文 / store / router），保证
// 即便 store/router 自己崩了也能渲染出"刷新"按钮。
import { Component } from 'react';

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // 内测期不接 Sentry，先打 console — 用户报问题时让他们截图给我们
    console.error('[ErrorBoundary]', error, info?.componentStack);
  }

  handleReload = () => {
    try {
      window.location.reload();
    } catch {
      // 极端情况下 location.reload 也挂了，没办法
    }
  };

  handleHome = () => {
    try {
      window.location.href = '/';
    } catch {
      /* noop */
    }
  };

  render() {
    if (this.state.error) {
      const isDev = !!(import.meta?.env?.DEV);
      const message = String(this.state.error?.message || this.state.error || '未知错误');
      return (
        <div className="error-boundary-screen" role="alert">
          <div className="error-boundary-wrap">
            <p className="error-boundary-eyebrow">出 了 点 问 题</p>
            <h1 className="error-boundary-title serif">页面崩了一下</h1>
            <p className="error-boundary-detail">
              界面渲染时遇到一个意料外的错。刷新页面通常能恢复；
              如果反复出现，请告诉我们。
            </p>
            {isDev ? (
              <details className="error-boundary-trace">
                <summary>开发详情（仅 dev 可见）</summary>
                <pre>{message}</pre>
              </details>
            ) : null}
            <div className="error-boundary-actions">
              <button type="button" className="btn-primary" onClick={this.handleReload}>
                刷新页面
              </button>
              <button type="button" className="btn-inline" onClick={this.handleHome}>
                回到首页
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
