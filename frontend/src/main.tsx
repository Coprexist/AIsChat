import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from './App'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { I18nProvider } from './i18n/I18nContext'
import ErrorBoundary from './components/ErrorBoundary'
import DemoChat from './pages/DemoChat'
import './index.css'
import 'katex/dist/katex.min.css'

const isDemo = window.location.pathname.includes('/AIsChat/') || window.location.hostname === 'coprexist.github.io'

if (isDemo) {
  // 演示模式：完全绕过后端、路由、认证
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <ThemeProvider>
          <DemoChat />
        </ThemeProvider>
      </ErrorBoundary>
    </React.StrictMode>,
  )
} else {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <ThemeProvider>
          <AuthProvider>
            <I18nProvider>
              <RouterProvider router={router} />
            </I18nProvider>
          </AuthProvider>
        </ThemeProvider>
      </ErrorBoundary>
    </React.StrictMode>,
  )
}
