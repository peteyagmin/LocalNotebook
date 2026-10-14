import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { captureToken } from './api'
import './index.css'

captureToken()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
