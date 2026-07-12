/**
 * Tauri 平台 API 封装
 *
 * 集中管理所有 Tauri IPC 调用，统一错误处理。
 * 调用方无需重复写 `__TAURI__ in window` 检查 + 动态 import。
 *
 * 使用方式：
 *   import { isTauri, invoke, getPlatform } from '../utils/tauri'
 *   const platform = await getPlatform()
 *   const result = await invoke('some_command', { arg1: 'value' })
 */

/** 是否运行在 Tauri 环境中 */
export function isTauri(): boolean {
  return '__TAURI_INTERNALS__' in window
}

/** 是否运行在 Tauri Android 环境中 */
export async function isAndroid(): Promise<boolean> {
  if (!isTauri()) return false
  try {
    const info = await getPlatform()
    return info === 'android'
  } catch {
    return false
  }
}

/** 调用 Tauri 命令的统一入口 */
export async function invoke<T = unknown>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) {
    throw new Error('Tauri 环境不可用')
  }
  const { invoke: tauriInvoke } = await import('@tauri-apps/api/core')
  return tauriInvoke<T>(command, args)
}

/** 获取当前平台标识 */
export async function getPlatform(): Promise<string> {
  try {
    const result = await invoke<{ platform: string }>('io_bridge_call', {
      request: { target: null, method: 'getPlatform', args: [] },
    })
    return result.platform
  } catch {
    return 'web'
  }
}

/** 获取应用版本号 */
export async function getAppVersion(): Promise<string> {
  try {
    const result = await invoke<{ version: string }>('io_bridge_call', {
      request: { target: null, method: 'getAppVersion', args: [] },
    })
    return result.version
  } catch {
    return '0.0.0'
  }
}

// ═══════════════════════════════════════════════════════════════
// 键盘可见性检测（visualViewport API，纯前端方案）
// ═══════════════════════════════════════════════════════════════

let _keyboardListeners: Array<(visible: boolean) => void> = []
let _lastKeyboardVisible: boolean | null = null

/** 注册键盘可见性变化回调 */
export function onKeyboardChange(callback: (visible: boolean) => void): () => void {
  _keyboardListeners.push(callback)

  // 首次注册时启动监听
  if (_keyboardListeners.length === 1 && window.visualViewport) {
    window.visualViewport.addEventListener('resize', _handleVisualViewportResize)
  }

  return () => {
    _keyboardListeners = _keyboardListeners.filter((cb) => cb !== callback)
    if (_keyboardListeners.length === 0 && window.visualViewport) {
      window.visualViewport.removeEventListener('resize', _handleVisualViewportResize)
    }
  }
}

function _handleVisualViewportResize(): void {
  if (!window.visualViewport) return
  // 视觉视口高度 < 屏幕高度 * 0.8 → 键盘弹出
  const screenHeight = window.screen.height
  const vvHeight = window.visualViewport.height
  const visible = vvHeight < screenHeight * 0.8

  if (visible !== _lastKeyboardVisible) {
    _lastKeyboardVisible = visible
    _keyboardListeners.forEach((cb) => cb(visible))
  }
}
