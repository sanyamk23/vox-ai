import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { crashed: false, error: null }
  }
  static getDerivedStateFromError(error) {
    return { crashed: true, error }
  }
  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info)
  }
  render() {
    if (this.state.crashed) {
      return (
        <div style={{ minHeight: '100vh', background: '#010828', color: '#EFF4FF', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', fontFamily: 'monospace', gap: '16px' }}>
          <div style={{ fontSize: '48px', color: '#6FFF00' }}>⚡</div>
          <div style={{ fontSize: '14px', textTransform: 'uppercase', letterSpacing: '0.2em' }}>Something went wrong</div>
          <div style={{ fontSize: '11px', color: 'rgba(239,244,255,0.4)', maxWidth: '400px', textAlign: 'center' }}>{String(this.state.error)}</div>
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: '16px', padding: '10px 24px', background: '#6FFF00', color: '#010828', border: 'none', borderRadius: '24px', fontFamily: 'monospace', fontSize: '11px', textTransform: 'uppercase', cursor: 'pointer' }}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
