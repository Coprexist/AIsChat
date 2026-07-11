/**
 * 页面路由注册表 — 统一管理所有前端路由
 *
 * 新增页面只需在此文件添加一行，无需修改 App.tsx。
 *
 * 用法：
 *   1. 在 pages/ 下创建组件
 *   2. 在此文件 import 并添加到 registerRoutes() 数组
 *   3. App.tsx 自动扫描注册
 */
import type { RouteObject } from 'react-router-dom'
import { Navigate } from 'react-router-dom'
import type { ComponentType, ReactNode } from 'react'
import LoginPage from '../pages/LoginPage'
import ChatPage from '../pages/ChatPage'
import DMPage from '../pages/DMPage'
import AgentsPage from '../pages/AgentsPage'
import AgentDetailPage from '../pages/AgentDetailPage'
import SettingsPage from '../pages/SettingsPage'
import MePage from '../pages/MePage'
import UsagePage from '../pages/UsagePage'
import AdminPage from '../pages/AdminPage'
import FriendsPage from '../pages/FriendsPage'
import SetupPage from '../pages/SetupPage'
import ManualPage from '../pages/ManualPage'
import InstanceSetupPage from '../pages/InstanceSetupPage'
import LocalModelPage from '../pages/LocalModelPage'

// ── 路由定义类型 ──

export interface RouteDef {
  /** 路由路径（相对于父路由，不加前导 /） */
  path?: string
  /** 页面组件（自动注入，无需 JSX） */
  Component?: ComponentType<any>
  /** 如果是重定向，指定目标路径 */
  redirect?: string
  /** 仅管理员可见 */
  adminOnly?: boolean
  /** 是否为 index 路由 */
  index?: boolean
  /** 嵌套子路由 */
  children?: RouteDef[]
}

// ── 内置路由守卫 ──

export function AdminGuard({ children }: { children: ReactNode }) {
  // 实际实现在 App.tsx 中，这里只是占位
  return <>{children}</>
}

// ── 注册所有路由 ──

/**
 * 公开路由（无需登录）
 */
export function getPublicRoutes(): RouteObject[] {
  return [
    { path: '/login', element: <LoginPage /> },
  ]
}

/**
 * 受保护路由（需要登录，放在 ProtectedLayout 下）
 * 返回 RouteObject[] 供 createBrowserRouter 使用
 */
export function getProtectedRoutes(AdminGuardComponent: ComponentType<{ children: ReactNode }> = AdminGuard): RouteObject[] {
  const A = AdminGuardComponent
  return [
    { index: true, element: <Navigate to="/chat" replace /> },
    { path: 'chat', element: <ChatPage /> },
    { path: 'chat/gm/:groupId', element: <ChatPage /> },
    { path: 'dm', element: <Navigate to="/chat" replace /> },
    { path: 'dm/:sessionId', element: <DMPage /> },
    { path: 'chat/dm/:sessionId', element: <ChatPage /> },
    { path: 'friends', element: <FriendsPage /> },
    { path: 'agents', element: <AgentsPage /> },
    { path: 'agents/:id', element: <AgentDetailPage /> },
    { path: 'me', element: <MePage /> },
    { path: 'me/usage', element: <UsagePage /> },
    { path: 'settings', element: <SettingsPage /> },
    { path: 'setup', element: <SetupPage /> },
    { path: 'instance-setup', element: <InstanceSetupPage /> },
    { path: 'local-models', element: <LocalModelPage /> },
    { path: 'manual', element: <ManualPage /> },
    { path: 'manual/admin', element: <ManualPage /> },
    { path: 'admin', element: <A><AdminPage /></A> },
  ]
}
