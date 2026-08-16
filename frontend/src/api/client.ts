/**
 * API 客户端
 * 封装 fetch，自动添加 JWT 认证头
 * 桌面端从 localStorage 读取实例地址拼 API 路径，Web 端保持 '/api' 相对路径
 */
import { type Result, success, failure } from '../utils/result'

function getApiBaseUrl(): string {
  // 桌面端：从 localStorage 读取实例地址
  const stored = localStorage.getItem('instance_url')
  if (stored) {
    return stored.replace(/\/+$/, '') + '/api'
  }
  // Web 端：使用默认值
  return '/api'
}

export { getApiBaseUrl }

class ApiError extends Error {
  status: number
  detail: string
  constructor(message: string, status: number) {
    super(message)
    this.status = status
    this.detail = message
  }
}

async function request<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem('access_token')

  const body = options.body
  const isFormData = body instanceof FormData

  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }
  // FormData 让浏览器自动设置 Content-Type（含 boundary），不要手动盖
  if (!isFormData) {
    headers['Content-Type'] = 'application/json'
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers,
  })

  // 401 且不是登录请求 → token 过期/无效，跳转登录页
  if (res.status === 401 && !path.endsWith('/auth/login') && !path.endsWith('/auth/register')) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new ApiError('Unauthorized', 401)
  }

  // 软维护提示（API 正常但带维护头）
  if (res.headers.get('X-Maintenance') === 'true') {
    localStorage.setItem('_maint_detected', '1')
    window.dispatchEvent(new CustomEvent('maintenance-soft'))
  }

  if (res.status === 503) {
    try { const body = JSON.parse(await res.clone().text()); if (body.maintenance) {
      localStorage.setItem('_maint_detected', '1')
      window.dispatchEvent(new CustomEvent('maintenance-mode', { detail: body }))
      throw new ApiError(body.detail || '服务器维护中', 503)
    } } catch {}
  }

  // 硬维护弹窗清除：仅当之前显示过硬维护弹窗、且本次响应确认非维护时才关闭。
  // 注意：/admin/*、/auth/* 等 bypass 路径永远无维护头，不能据此清除软维护提示；
  // 软维护的关闭统一由 Layout 轮询 /maintenance-msg 权威判定。
  if (res.status !== 503 && res.headers.get('X-Maintenance') !== 'true' && localStorage.getItem('_maint_hard_visible')) {
    localStorage.removeItem('_maint_hard_visible')
    localStorage.removeItem('_maint_detected')
    window.dispatchEvent(new CustomEvent('maintenance-cleared'))
  }

  // 安全解析 JSON：处理空 body / 非 JSON 响应
  let data: any
  try {
    const text = await res.text()
    data = text ? JSON.parse(text) : {}
  } catch {
    if (!res.ok) {
      throw new ApiError(`Request failed (${res.status})`, res.status)
    }
    return {} as T
  }

  if (!res.ok) {
    throw new ApiError(data.detail || `Request failed (${res.status})`, res.status)
  }

  return data
}

/** 上传文件（multipart/form-data），返回 {file_id, name, path, size, mime_type} */
async function uploadFile(path: string, file: File): Promise<any> {
  const token = localStorage.getItem('access_token')
  const formData = new FormData()
  formData.append('file', file)

  const headers: Record<string, string> = {}
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    method: 'POST',
    headers,
    body: formData,
  })

  // 401 且不是登录请求 → token 过期/无效，跳转登录页
  if (res.status === 401 && !path.endsWith('/auth/login') && !path.endsWith('/auth/register')) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new ApiError('Unauthorized', 401)
  }

  // 友好提示：413 文件过大（代理/后端任意层拦截）
  if (res.status === 413) {
    throw new ApiError('文件过大，请检查文件大小限制', 413)
  }

  // 安全解析 JSON：处理空 body / 非 JSON 响应
  let data: any
  try {
    const text = await res.text()
    data = text ? JSON.parse(text) : {}
  } catch {
    if (!res.ok) {
      throw new ApiError(`上传失败 (${res.status})`, res.status)
    }
    return {}
  }

  if (!res.ok) {
    throw new ApiError(data.detail || `上传失败 (${res.status})`, res.status)
  }
  return data
}

/** Result 风格的请求封装（不抛异常，返回 Result<T, ApiError>） */
async function safeRequest<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<Result<T, ApiError>> {
  try {
    const data = await request<T>(path, options)
    return success(data)
  } catch (e) {
    if (e instanceof ApiError) return failure(e)
    return failure(new ApiError(String(e), 0))
  }
}

const jsonBody = (body?: any) => body instanceof FormData ? body : JSON.stringify(body)

export const api = {
  get: <T = any>(path: string) => request<T>(path),
  post: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'POST', body: jsonBody(body) }),
  put: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'PUT', body: jsonBody(body) }),
  patch: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'PATCH', body: jsonBody(body) }),
  delete: <T = any>(path: string) =>
    request<T>(path, { method: 'DELETE' }),
  upload: uploadFile,
  // Result 风格 API（不抛异常）
  safe: {
    get: <T = any>(path: string) => safeRequest<T>(path),
    post: <T = any>(path: string, body?: any) =>
      safeRequest<T>(path, { method: 'POST', body: jsonBody(body) }),
    put: <T = any>(path: string, body?: any) =>
      safeRequest<T>(path, { method: 'PUT', body: jsonBody(body) }),
    patch: <T = any>(path: string, body?: any) =>
      safeRequest<T>(path, { method: 'PATCH', body: jsonBody(body) }),
    delete: <T = any>(path: string) =>
      safeRequest<T>(path, { method: 'DELETE' }),
  },
}

export { ApiError }
