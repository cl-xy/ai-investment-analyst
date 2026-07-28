import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/ErrorBoundary'

// Apply theme before React hydration to prevent flash
const theme = localStorage.getItem('invest-theme') || 'petroleum'
document.documentElement.setAttribute('data-theme', theme)

// Clear chunk reload flag on successful load
sessionStorage.removeItem('chunk_reload')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
)
