/**
 * CSS 滤镜工具（魔视界）
 * 定义、构建、持久化、注入
 * "仅对 UI" 模式使用 CSS :has() 选择器，浏览器原生实时生效
 * 参见 docs/magic-vision.md
 */

// ── 类型 ──

export type MagicVisionScope = 'all' | 'ui' | 'images'

export interface FilterState {
  enabled: boolean
  value: number
}

export interface MagicVisionPrefs {
  enabled: boolean
  scope: MagicVisionScope
  filters: Record<string, FilterState>
}

export interface FilterDef {
  id: string
  label: string
  unit: string
  css: (v: number) => string
  min: number
  max: number
  step: number
  defaultVal: number
}

// ── 定义 ──

export const FILTER_DEFS: FilterDef[] = [
  { id: 'blur',        label: '模糊',   unit: 'px',  css: (v) => `blur(${v}px)`,                        min: 0, max: 20,  step: 0.5, defaultVal: 0   },
  { id: 'brightness',  label: '亮度',   unit: '%',   css: (v) => `brightness(${v}%)`,                    min: 0, max: 300, step: 1,   defaultVal: 100 },
  { id: 'contrast',    label: '对比度', unit: '%',   css: (v) => `contrast(${v}%)`,                      min: 0, max: 300, step: 1,   defaultVal: 100 },
  { id: 'drop-shadow', label: '投影',   unit: '',    css: (v) => `drop-shadow(${v}px ${v}px ${v*.5}px rgba(0,0,0,.5))`, min: 0, max: 30, step: 1, defaultVal: 0 },
  { id: 'grayscale',   label: '灰度',   unit: '%',   css: (v) => `grayscale(${v}%)`,                     min: 0, max: 100, step: 1,   defaultVal: 0   },
  { id: 'hue-rotate',  label: '色相旋转', unit: 'deg', css: (v) => `hue-rotate(${v}deg)`,              min: 0, max: 360, step: 1,   defaultVal: 0   },
  { id: 'invert',      label: '反色',   unit: '%',   css: (v) => `invert(${v}%)`,                        min: 0, max: 100, step: 1,   defaultVal: 0   },
  { id: 'opacity',     label: '透明度', unit: '%',   css: (v) => `opacity(${v}%)`,                       min: 0, max: 100, step: 1,   defaultVal: 100 },
  { id: 'saturate',    label: '饱和度', unit: '%',   css: (v) => `saturate(${v}%)`,                      min: 0, max: 500, step: 1,   defaultVal: 100 },
  { id: 'sepia',       label: '棕褐色', unit: '%',   css: (v) => `sepia(${v}%)`,                         min: 0, max: 100, step: 1,   defaultVal: 0   },
]

// ── 默认值构造 ──

function defaultFilters(): Record<string, FilterState> {
  const f: Record<string, FilterState> = {}
  FILTER_DEFS.forEach(d => { f[d.id] = { enabled: false, value: d.defaultVal } })
  return f
}

export function defaultPrefs(): MagicVisionPrefs {
  return { enabled: false, scope: 'ui', filters: defaultFilters() }
}

// ── 标准化 ──

export function normalizePrefs(raw: unknown): MagicVisionPrefs {
  const base = defaultPrefs()
  if (!raw || typeof raw !== 'object') return base
  const r = raw as Record<string, unknown>
  const out: MagicVisionPrefs = {
    enabled: r.enabled === true,
    scope: ['all', 'ui', 'images'].includes(r.scope as string) ? (r.scope as MagicVisionScope) : 'ui',
    filters: { ...base.filters },
  }
  if (r.filters && typeof r.filters === 'object') {
    for (const [key, val] of Object.entries(r.filters)) {
      if (out.filters[key] && typeof val === 'object' && val !== null) {
        const v = val as Record<string, unknown>
        out.filters[key] = {
          enabled: v.enabled === true,
          value: typeof v.value === 'number' ? v.value : base.filters[key].value,
        }
      }
    }
  }
  return out
}

// ── CSS 构建 ──

export function buildCSS(filters: Record<string, FilterState>): string {
  return FILTER_DEFS
    .filter(d => filters[d.id]?.enabled && filters[d.id].value !== d.defaultVal)
    .map(d => d.css(filters[d.id].value))
    .join(' ')
}

// ── DOM 注入 ──

const STYLE_ID = 'magic-vision-style'
/** 强制补偿标记：带此标记的元素会被补偿 hue-rotate，保证有/无头像时绿点旋转次数一致 */
const FORCE_ATTR = 'data-mv-force'
/** [id] 属性选择器特异性 (0,1,0) + img = (0,1,1) 压过 :has() 的 (0,0,4)，无需额外 DOM */
const HIGH = '[id]'

function clearAll(): void {
  document.getElementById(STYLE_ID)?.remove()
  document.documentElement.style.filter = ''
  // 清除强制补偿的内联样式，避免关闭魔视界后残留
  document.querySelectorAll(`[${FORCE_ATTR}]`).forEach((el) => {
    ;(el as HTMLElement).style.removeProperty('filter')
  })
  // 断开动态补偿监听
  if (_forceObserver) {
    _forceObserver.disconnect()
    _forceObserver = null
  }
  _lastCompensateCSS = null
}

function applyUI(css: string): void {
  const el = document.createElement('style')
  el.id = STYLE_ID
  // [id] 属性选择器特异性 (0,1,0) + img = (0,1,1)，压过 :has() 的 (0,0,4)
  el.textContent = [
    `*:not(:has(img)):not(:has(video)):not(:has(canvas)):not(:has(picture)) { filter: ${css} !important; }`,
    `${HIGH} img, ${HIGH} video, ${HIGH} canvas, ${HIGH} picture,`,
    `${HIGH} [style*="background-image"], ${HIGH} [class*="avatar"], ${HIGH} [class*="Avatar"], ${HIGH} [data-mv-clean]`,
    `{ filter: none !important; }`,
  ].join(' ')
  document.head.appendChild(el)
}

// ── 强制补偿（hue-rotate）──
// 背景：UI 模式用 `*:not(:has(img))...` 给每个元素单独挂滤镜，嵌套元素会被祖先+自身叠加多次。
// 对绿点来说：有头像时父容器含 img 被豁免（转 1 次），无头像时父容器也转（转 2 次）→ 颜色不一致。
// 补偿：数祖先链上实际挂了 filter 的元素数 k，把绿点自身的 hue-rotate 改成 (1-k)*X，
// 最终总旋转 = (1-k)*X + k*X = X，无论 k 是几都正好转一次。
// 其他滤镜（blur 等）不补偿——叠加是魔视界一贯行为，保持与其他元素一致。
let _forceObserver: MutationObserver | null = null
let _lastCompensateCSS: string | null = null

function compensateHueRotate(css: string): void {
  _lastCompensateCSS = css
  const m = css.match(/hue-rotate\((-?[\d.]+)deg\)/)
  if (!m) return
  const X = parseFloat(m[1])
  const otherParts = css.replace(/hue-rotate\(-?[\d.]+deg\)/, '').trim()

  document.querySelectorAll(`[${FORCE_ATTR}]`).forEach((el) => {
    let k = 0
    for (let p = el.parentElement; p; p = p.parentElement) {
      const f = getComputedStyle(p).filter
      if (f && f !== 'none') k++
    }
    const compensated = (1 - k) * X
    const filter = `${otherParts} hue-rotate(${compensated}deg)`.trim()
    ;(el as HTMLElement).style.setProperty('filter', filter, 'important')
  })

  // 监听后续动态渲染的 data-mv-force 元素（如侧边栏异步加载完列表后才出现），自动补补偿
  if (!_forceObserver) {
    _forceObserver = new MutationObserver(() => {
      if (_lastCompensateCSS) compensateHueRotate(_lastCompensateCSS)
    })
    _forceObserver.observe(document.body, { childList: true, subtree: true })
  }
}

// ── 主入口 ──

export function apply(prefs: MagicVisionPrefs): void {
  clearAll()
  if (!prefs.enabled) return
  const css = buildCSS(prefs.filters)
  if (!css) return

  if (prefs.scope === 'all') {
    document.documentElement.style.filter = css
  } else if (prefs.scope === 'images') {
    const el = document.createElement('style')
    el.id = STYLE_ID
    el.textContent = `* { filter: none !important; } img, video, canvas, picture { filter: ${css} !important; }`
    document.head.appendChild(el)
  } else {
    applyUI(css)
    compensateHueRotate(css)
  }
}

// ── 存储 ──

const LS_KEY = 'magic_vision_prefs'

export function loadFromStorage(): MagicVisionPrefs | null {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? normalizePrefs(JSON.parse(raw)) : null
  } catch {
    return null
  }
}

export function saveToStorage(prefs: MagicVisionPrefs): void {
  try { localStorage.setItem(LS_KEY, JSON.stringify(prefs)) } catch {}
}
