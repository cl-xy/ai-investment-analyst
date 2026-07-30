import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'

// Apply theme before React hydration to prevent flash
let theme = 'petroleum'
try {
  theme = localStorage.getItem('invest-theme') || 'petroleum'
} catch {
  // Storage blocked (SecurityError in private browsing / sandboxed iframe)
}
document.documentElement.setAttribute('data-theme', theme)

// Clear chunk reload flag on successful load
try {
  sessionStorage.removeItem('chunk_reload')
} catch {
  // Storage unavailable
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
)
