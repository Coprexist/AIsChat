import { createBrowserRouter, createHashRouter, Navigate, Outlet, useLocation } from 'react-router-dom'
import { lazy } from 'react'
import { useAuth } from './context/AuthContext'
import Layout from './components/Layout'
import { getPublicRoutes, getProtectedRoutes } from './utils/pageRegistry'

const NotFoundPage = lazy(() => import('./pages/NotFoundPage'))
const DemoChat = lazy(() => import('./pages/DemoChat'))

const isDemo = window.location.pathname.includes('/AIsChat/')

function DemoLayout() {
  return <DemoChat />
}

function ProtectedLayout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
      </div>
    )
  }
  if (!user) return <Navigate to="/login" replace />

  // 新用户需先完成初始化设置向导
  if (!user.setup_completed && location.pathname !== '/setup') {
    return <Navigate to="/setup" replace />
  }

  // 桌面端首次启动：未配置实例地址则跳转到配置页
  if (
    '__TAURI_INTERNALS__' in window &&
    !localStorage.getItem('instance_url') &&
    location.pathname !== '/instance-setup'
  ) {
    return <Navigate to="/instance-setup" replace />
  }

  return <Layout />
}

function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user || user.role !== 'admin') return <Navigate to="/chat" replace />
  return <>{children}</>
}

const createRouter = isDemo ? createHashRouter : createBrowserRouter

export const router = createRouter([
  ...(isDemo ? [{ path: '/', element: <DemoLayout /> }] : []),
  ...getPublicRoutes(),
  {
    path: '/',
    element: <ProtectedLayout />,
    children: getProtectedRoutes(AdminGuard),
  },
  { path: '*', element: <NotFoundPage /> },
])
