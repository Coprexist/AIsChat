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

class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = localStorage.getItem('access_token')

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${getApiBaseUrl()}${path}`, {
    ...options,
    headers,
  })

  if (res.status === 401) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new ApiError('Unauthorized', 401)
  }

  if (res.status === 503) {
    try { const body = JSON.parse(await res.clone().text()); if (body.maintenance) { window.dispatchEvent(new CustomEvent('maintenance-mode')); throw new ApiError('服务器维护中', 503) } } catch {}
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

  if (res.status === 401) {
    localStorage.removeItem('access_token')
    window.location.href = '/login'
    throw new ApiError('Unauthorized', 401)
  }

  // 安全解析 JSON：处理空 body / 非 JSON 响应
  let data: any
  try {
    const text = await res.text()
    data = text ? JSON.parse(text) : {}
  } catch {
    if (!res.ok) {
      throw new ApiError(`Upload failed (${res.status})`, res.status)
    }
    return {}
  }

  if (!res.ok) {
    throw new ApiError(data.detail || `Upload failed (${res.status})`, res.status)
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

export const api = {
  get: <T = any>(path: string) => request<T>(path),
  post: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T = any>(path: string, body?: any) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T = any>(path: string) =>
    request<T>(path, { method: 'DELETE' }),
  upload: uploadFile,
  // Result 风格 API（不抛异常）
  safe: {
    get: <T = any>(path: string) => safeRequest<T>(path),
    post: <T = any>(path: string, body?: any) =>
      safeRequest<T>(path, { method: 'POST', body: JSON.stringify(body) }),
    put: <T = any>(path: string, body?: any) =>
      safeRequest<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
    patch: <T = any>(path: string, body?: any) =>
      safeRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: <T = any>(path: string) =>
      safeRequest<T>(path, { method: 'DELETE' }),
  },
}

export { ApiError }
