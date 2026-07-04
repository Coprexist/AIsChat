/**
 * Result / Option discriminated union types
 *
 * 用于统一处理成功/失败和可选值，减少散落的 try/catch 和 null 检查。
 *
 * 用法:
 *   function getUser(id: number): Result<User> { ... }
 *   const result = getUser(1)
 *   if (result.ok) { result.value.username }
 *   else { result.error }
 *
 *   // 链式
 *   const name = map(getUser(1), u => u.username)
 */

export type Result<T, E = string> =
  | { ok: true; value: T }
  | { ok: false; error: E }

/** 创建成功 Result */
export function success<T>(value: T): Result<T, never> {
  return { ok: true, value }
}

/** 创建失败 Result */
export function failure<E = string>(error: E): Result<never, E> {
  return { ok: false, error }
}

/** 成功时变换值，失败时透传 */
export function map<T, U, E>(
  result: Result<T, E>,
  fn: (value: T) => U,
): Result<U, E> {
  return result.ok ? success(fn(result.value)) : result
}

/** 成功时链式调用可能失败的操作，失败时透传 */
export function andThen<T, U, E>(
  result: Result<T, E>,
  fn: (value: T) => Result<U, E>,
): Result<U, E> {
  return result.ok ? fn(result.value) : result
}

/** 解包，失败时返回默认值 */
export function unwrapOr<T, E>(result: Result<T, E>, defaultValue: T): T {
  return result.ok ? result.value : defaultValue
}

/** 解包成功值，失败时抛异常 */
export function unwrap<T, E>(result: Result<T, E>): T {
  if (!result.ok) throw new Error(String(result.error))
  return result.value
}

/** 安全的 JSON.parse，返回 Result */
export function safeParse<T = unknown>(text: string): Result<T, string> {
  try {
    return success(JSON.parse(text) as T)
  } catch {
    return failure('JSON 解析失败')
  }
}
