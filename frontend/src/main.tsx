import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider, createHashRouter } from 'react-router-dom'
import { router, routes } from './App'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { I18nProvider } from './i18n/I18nContext'
import ErrorBoundary from './components/ErrorBoundary'
import { setupDemo } from './demo/demoSetup'
import './index.css'
import 'katex/dist/katex.min.css'

const isDemo = window.location.pathname.includes('/AIsChat/') || window.location.hostname === 'coprexist.github.io'

if (isDemo) {
  setupDemo()
  // 演示模式：HashRouter（不依赖 Vite base 路径）
  const demoRouter = createHashRouter(routes)
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ErrorBoundary>
        <ThemeProvider>
          <AuthProvider>
            <I18nProvider>
              <RouterProvider router={demoRouter} />
            </I18nProvider>
          </AuthProvider>
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
