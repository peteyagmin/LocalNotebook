import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { captureToken } from './api'
import { applyAppearance } from './appearance'
import './index.css'

captureToken()
applyAppearance({ theme: 'system', font_size: 16 }) // until the saved settings arrive

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
