/**
 * 插件自更新：内容寻址 + 暂存校验 + 原子换入 + 可回滚。
 *
 * 身份不用人肉维护的版本号，而是构建产物清单的摘要（manifest id）。清单里每个
 * 文件带 sha256，对清单规范化序列化后取摘要即为该次构建的身份——与用 digest
 * 定位镜像同一思路：内容变了身份就变，不需要谁去记得 bump 版本号。
 *
 * 更新源来自安装溯源：profile 的 package.json 里 dependencies['dsh-copree']
 * 的 file: 规格（pnpm/npm 记录的就是它），因此默认零配置。显式配置可覆盖。
 *
 * 边界：host 半（lib/index.js）正被 dsh-web 进程加载，覆盖文件不会让它热替换。
 * 因此换入后返回 applyMode：只动了 client/dist 即为 hot（刷新页面即可），
 * 动了 host 半则为 restart（必须重启 dsh-web）。本模块不自行重启宿主进程。
 */
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import {
  copyFileSync, existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync,
} from 'node:fs'
import { basename, dirname, isAbsolute, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export interface PluginManifest {
  name: string
  version: string
  buildStamp: string
  backendVersion: string | null
  /** 相对包根的路径 -> sha256（十六进制） */
  files: Record<string, string>
}

export type ApplyMode = 'hot' | 'restart'

export const PLUGIN_NAME = 'dsh-copree'
export const MANIFEST_REL = 'lib/manifest.json'
export const PLUGIN_PREFIX = '/copree-plugin'

const HOST_ENTRY = 'lib/index.js'
const STAGING_DIR = '.copree-plugin-staging'
const BACKUP_DIR = '.copree-plugin-previous'

/** 包根目录：本文件被打进 lib/index.js，故其所在目录的上一级即包根。 */
export const PACKAGE_ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

export function sha256File(path: string): string {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

/** 清单摘要：文件集合或任一文件内容变化都会改变身份。 */
export function manifestId(manifest: PluginManifest): string {
  const canonical = JSON.stringify(
    Object.keys(manifest.files).sort().map((rel) => [rel, manifest.files[rel]]),
  )
  return createHash('sha256').update(canonical).digest('hex')
}

export function readManifest(root: string): PluginManifest | null {
  const path = join(root, MANIFEST_REL)
  if (!existsSync(path)) return null
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf8')) as PluginManifest
    if (!parsed || typeof parsed !== 'object' || !parsed.files || typeof parsed.files !== 'object') return null
    return parsed
  } catch {
    return null
  }
}

function packageNameOf(root: string): string | null {
  try {
    const pkg = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8')) as { name?: string }
    return typeof pkg.name === 'string' ? pkg.name : null
  } catch {
    return null
  }
}

export interface SourceResolution {
  root: string | null
  /** 解析依据，用于把失败原因如实告诉用户，而不是笼统报错 */
  how: 'config' | 'config-invalid' | 'profile-file-spec' | 'no-profile-package' | 'no-file-spec' | 'source-missing'
}

/**
 * 解析更新源。优先显式配置，否则回溯安装来源：安装目录形如
 * <profile>/node_modules/<name>，其 <profile>/package.json 记录了 file: 规格。
 */
export function resolveSourceRoot(installRoot: string, explicit?: string): SourceResolution {
  if (explicit && explicit.trim()) {
    const root = resolve(explicit.trim())
    return packageNameOf(root) === PLUGIN_NAME
      ? { root, how: 'config' }
      : { root: null, how: 'config-invalid' }
  }
  const profileRoot = dirname(dirname(installRoot))
  if (packageNameOf(profileRoot) === null && !existsSync(join(profileRoot, 'package.json'))) {
    return { root: null, how: 'no-profile-package' }
  }
  try {
    const pkg = JSON.parse(readFileSync(join(profileRoot, 'package.json'), 'utf8')) as {
      dependencies?: Record<string, string>
    }
    const spec = pkg.dependencies?.[PLUGIN_NAME]
    if (!spec || !spec.startsWith('file:')) return { root: null, how: 'no-file-spec' }
    const raw = spec.slice('file:'.length)
    const root = isAbsolute(raw) ? raw : resolve(profileRoot, raw)
    return packageNameOf(root) === PLUGIN_NAME ? { root, how: 'profile-file-spec' } : { root: null, how: 'source-missing' }
  } catch {
    return { root: null, how: 'no-profile-package' }
  }
}

async function fetchBackendVersion(backendUrl: string): Promise<string | null> {
  try {
    const res = await fetch(new URL('/health', backendUrl.endsWith('/') ? backendUrl : backendUrl + '/'), {
      signal: AbortSignal.timeout(1500),
    })
    if (!res.ok) return null
    const body = (await res.json()) as { version?: unknown }
    return typeof body.version === 'string' ? body.version : null
  } catch {
    return null
  }
}

/** 本插件的安装来源；决定该由谁负责更新。 */
export type InstallKind = 'local-file' | 'npm' | 'git' | 'unknown'

/**
 * 更新通道。分发出去的副本不该由本插件用本地构建的版本语义去覆盖：
 * 装在 npm / git 上的副本交给包管理器（有市场就让市场做，它本来就是 GUI）。
 */
export type UpdateChannel = 'self' | 'market' | 'package-manager' | 'unavailable'

/** 插件市场的包名；装了它就把更新让给它。 */
const MARKET_PLUGIN = 'dshmarket'

export interface PluginStatus {
  installed: { version: string; id: string; buildStamp: string } | null
  available: { version: string; id: string; buildStamp: string } | null
  source: SourceResolution
  /** 安装来源与更新通道 */
  installKind: InstallKind
  updateChannel: UpdateChannel
  marketInstalled: boolean
  state: 'up-to-date' | 'update-available' | 'source-unavailable' | 'not-installed'
  /** update-available 的原因：构建落后，或安装副本缺文件 */
  reason: 'behind' | 'incomplete' | null
  /** 安装清单里缺失的产物数量 */
  missing: number
  applyMode: ApplyMode
  backend: { builtAgainst: string | null; running: string | null; mismatch: boolean }
}

/**
 * 安装完整性：只做存在性检查。清单只记录装了什么，一旦产物被包管理器按
 * files 字段裁掉，清单仍会声称一切正常——只有真去看文件在不在才发现得了。
 * 内容哈希开销大，留给 apply 阶段。
 */
function missingArtifacts(root: string, manifest: PluginManifest): string[] {
  return Object.keys(manifest.files).filter((rel) => !existsSync(join(root, rel)))
}

/** profile 根目录：安装目录形如 <profile>/node_modules/<name>。 */
function profileRootOf(installRoot: string): string {
  return dirname(dirname(installRoot))
}

function readProfileDependencies(installRoot: string): Record<string, string> | null {
  try {
    const pkg = JSON.parse(readFileSync(join(profileRootOf(installRoot), 'package.json'), 'utf8')) as {
      dependencies?: Record<string, string>
    }
    return pkg.dependencies ?? {}
  } catch {
    return null
  }
}

function classifySpec(spec: string | undefined): InstallKind {
  if (!spec) return 'unknown'
  if (spec.startsWith('file:') || spec.startsWith('link:')) return 'local-file'
  if (spec.startsWith('github:') || spec.startsWith('git+') || spec.startsWith('git:')) return 'git'
  if (/^https?:\/\/(github\.com|codeload\.github\.com)\//.test(spec)) return 'git'
  return 'npm'
}

function summarize(manifest: PluginManifest | null) {
  return manifest
    ? { version: manifest.version, id: manifestId(manifest), buildStamp: manifest.buildStamp }
    : null
}

export async function computeStatus(
  installRoot: string,
  backendUrl: string,
  explicitSource?: string,
): Promise<PluginStatus> {
  const installedManifest = readManifest(installRoot)
  const dependencies = readProfileDependencies(installRoot)
  const installKind = classifySpec(dependencies?.[PLUGIN_NAME])
  const marketInstalled = Boolean(dependencies?.[MARKET_PLUGIN])
  const source = resolveSourceRoot(installRoot, explicitSource)
  const availableManifest = source.root ? readManifest(source.root) : null
  const running = await fetchBackendVersion(backendUrl)

  const installed = summarize(installedManifest)
  const available = summarize(availableManifest)

  const missing = installedManifest ? missingArtifacts(installRoot, installedManifest) : []

  // 装在 npm / git 上的副本不归本地构建的版本语义管：有市场就推荐走市场，
  // 没有就用包管理器从原来源更新。只有本地 file: 安装才走自己的内容寻址换入。
  const updateChannel: UpdateChannel =
    installKind === 'local-file'
      ? 'self'
      : installKind === 'unknown'
        ? 'unavailable'
        : marketInstalled
          ? 'market'
          : 'package-manager'

  let state: PluginStatus['state']
  let reason: PluginStatus['reason'] = null
  if (!installed) {
    state = 'not-installed'
  } else if (missing.length) {
    state = 'update-available'
    reason = 'incomplete'
  } else if (updateChannel === 'market' || updateChannel === 'package-manager') {
    // 远端来源的版本高低由包管理器判定，这里不猜
    state = 'up-to-date'
  } else if (!available) {
    state = 'source-unavailable'
  } else if (installed.id !== available.id) {
    state = 'update-available'
    reason = 'behind'
  } else {
    state = 'up-to-date'
  }

  const applyMode: ApplyMode =
    installedManifest && availableManifest && installedManifest.files[HOST_ENTRY] !== availableManifest.files[HOST_ENTRY]
      ? 'restart'
      : 'hot'

  const builtAgainst = installedManifest?.backendVersion ?? null
  return {
    installed,
    available,
    source,
    installKind,
    updateChannel,
    marketInstalled,
    state,
    reason,
    missing: missing.length,
    applyMode,
    backend: {
      builtAgainst,
      running,
      mismatch: Boolean(builtAgainst && running && builtAgainst !== running),
    },
  }
}

export interface ApplyResult {
  ok: boolean
  changed: string[]
  applyMode: ApplyMode
  installed?: { version: string; id: string }
  error?: string
}

let applying = false

/**
 * 换入更新源构建。流程：暂存 + 逐文件校验 -> 备份 -> 逐文件原子改名 ->
 * 清单最后落盘（提交点）。任何一步失败都在换入前中止，不留半新半旧的状态。
 */
export function applyUpdate(installRoot: string, sourceRoot: string): ApplyResult {
  if (applying) return { ok: false, changed: [], applyMode: 'hot', error: '已有更新正在进行' }
  applying = true
  const staging = join(installRoot, STAGING_DIR)
  try {
    const manifest = readManifest(sourceRoot)
    if (!manifest) {
      return { ok: false, changed: [], applyMode: 'hot', error: '更新源没有构建清单，请先在源码目录执行 node scripts/build.mjs' }
    }
    const previous = readManifest(installRoot)
    const rels = Object.keys(manifest.files).sort()

    rmSync(staging, { recursive: true, force: true })
    for (const rel of rels) {
      const src = join(sourceRoot, rel)
      if (!existsSync(src)) {
        return { ok: false, changed: [], applyMode: 'hot', error: `更新源缺少清单列出的文件：${rel}` }
      }
      const actual = sha256File(src)
      if (actual !== manifest.files[rel]) {
        return { ok: false, changed: [], applyMode: 'hot', error: `更新源文件与清单不符：${rel}（源码可能已改动但未重新构建）` }
      }
      const staged = join(staging, rel)
      mkdirSync(dirname(staged), { recursive: true })
      copyFileSync(src, staged)
    }

    const hostChanged = previous?.files[HOST_ENTRY] !== manifest.files[HOST_ENTRY]
    const backup = join(installRoot, BACKUP_DIR)
    const changed: string[] = []

    for (const rel of [...rels, MANIFEST_REL]) {
      const target = join(installRoot, rel)
      if (existsSync(target)) {
        const saved = join(backup, rel)
        mkdirSync(dirname(saved), { recursive: true })
        copyFileSync(target, saved)
      }
      if (rel === MANIFEST_REL) continue
      // 按磁盘实况判断，而不是比两份清单：产物被删掉时清单对比会说“没变化”
      if (!existsSync(target) || sha256File(target) !== manifest.files[rel]) changed.push(rel)
      mkdirSync(dirname(target), { recursive: true })
      renameSync(join(staging, rel), target)
    }

    writeFileSync(join(installRoot, MANIFEST_REL), JSON.stringify(manifest, null, 2), 'utf8')
    return {
      ok: true,
      changed,
      applyMode: hostChanged ? 'restart' : 'hot',
      installed: { version: manifest.version, id: manifestId(manifest) },
    }
  } catch (e) {
    return { ok: false, changed: [], applyMode: 'hot', error: String((e as Error).message ?? e) }
  } finally {
    rmSync(staging, { recursive: true, force: true })
    applying = false
  }
}

export interface PackageManagerUpdateResult {
  ok: boolean
  profile: string
  output: string
  applyMode: ApplyMode
  error?: string
}

/**
 * 兜底更新通道：没有插件市场时，用 DSH 自带的包管理器从原来源更新。
 * 不重复实现版本比对——npm 的 semver 与 git 的 ref 解析都归 pnpm，本函数只负责
 * 调用并如实回传输出。装完比较 host 半的摘要，决定是刷新页面还是必须重启。
 */
export function updateViaPackageManager(installRoot: string): Promise<PackageManagerUpdateResult> {
  const profileRoot = profileRootOf(installRoot)
  const profile = basename(profileRoot)
  const hostEntry = join(installRoot, HOST_ENTRY)
  const before = existsSync(hostEntry) ? sha256File(hostEntry) : null

  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>
    try {
      child = spawn('dsh', ['plugin', '--profile', profile, 'update', PLUGIN_NAME], {
        cwd: profileRoot,
        env: process.env,
      })
    } catch (e) {
      resolve({ ok: false, profile, output: '', applyMode: 'hot', error: String((e as Error).message ?? e) })
      return
    }
    let output = ''
    const collect = (buf: Buffer) => { output += buf.toString('utf8') }
    child.stdout?.on('data', collect)
    child.stderr?.on('data', collect)
    child.on('error', (e) => {
      resolve({ ok: false, profile, output, applyMode: 'hot', error: String(e.message ?? e) })
    })
    child.on('close', (code) => {
      const after = existsSync(hostEntry) ? sha256File(hostEntry) : null
      resolve({
        ok: code === 0,
        profile,
        output: output.slice(-4000),
        applyMode: before !== after ? 'restart' : 'hot',
        error: code === 0 ? undefined : `dsh plugin update 退出码 ${code}`,
      })
    })
  })
}

/** 回滚到上一次换入前的状态（applyUpdate 会保留一份备份）。 */
export function rollback(installRoot: string): ApplyResult {
  const backup = join(installRoot, BACKUP_DIR)
  const manifest = readManifest(backup)
  if (!manifest) return { ok: false, changed: [], applyMode: 'hot', error: '没有可回滚的备份' }
  try {
    const restored: string[] = []
    for (const rel of [...Object.keys(manifest.files), MANIFEST_REL]) {
      const src = join(backup, rel)
      if (!existsSync(src)) continue
      const target = join(installRoot, rel)
      mkdirSync(dirname(target), { recursive: true })
      copyFileSync(src, target)
      restored.push(rel)
    }
    return {
      ok: true,
      changed: restored,
      applyMode: 'restart',
      installed: { version: manifest.version, id: manifestId(manifest) },
    }
  } catch (e) {
    return { ok: false, changed: [], applyMode: 'hot', error: String((e as Error).message ?? e) }
  }
}

type JsonSender = (status: number, payload: unknown) => void

/** 注册 /copree-plugin 路由。handler 保持薄，逻辑都在上面的纯函数里。 */
export function registerPluginRoutes(
  register: (route: { kind: 'prefix'; path: string; handler: (req: any, res: any) => void }) => void,
  opts: { installRoot: string; backendUrl: string; sourceDir?: string; log?: (message: string) => void },
): void {
  register({
    kind: 'prefix',
    path: PLUGIN_PREFIX,
    handler: (req, res) => {
      const route = (req.url ?? '/').split('?')[0]
      const send: JsonSender = (status, payload) => {
        res.writeHead(status, { 'content-type': 'application/json; charset=utf-8' })
        res.end(JSON.stringify(payload))
      }
      if (req.method === 'GET' && route === `${PLUGIN_PREFIX}/status`) {
        computeStatus(opts.installRoot, opts.backendUrl, opts.sourceDir)
          .then((status) => send(200, status))
          .catch((e) => send(500, { error: String(e?.message ?? e) }))
        return
      }
      if (req.method === 'POST' && route === `${PLUGIN_PREFIX}/apply`) {
        const resolved = resolveSourceRoot(opts.installRoot, opts.sourceDir)
        if (!resolved.root) {
          send(409, { ok: false, error: `无法定位更新源（${resolved.how}）`, source: resolved })
          return
        }
        const result = applyUpdate(opts.installRoot, resolved.root)
        opts.log?.(result.ok
          ? `updated ${result.changed.length} file(s), applyMode=${result.applyMode}`
          : `update failed: ${result.error}`)
        send(result.ok ? 200 : 409, { ...result, source: resolved })
        return
      }
      if (req.method === 'POST' && route === `${PLUGIN_PREFIX}/update`) {
        updateViaPackageManager(opts.installRoot)
          .then((result) => {
            opts.log?.(result.ok
              ? `updated via package manager, applyMode=${result.applyMode}`
              : `package-manager update failed: ${result.error}`)
            send(result.ok ? 200 : 409, result)
          })
          .catch((e) => send(500, { error: String(e?.message ?? e) }))
        return
      }
      if (req.method === 'POST' && route === `${PLUGIN_PREFIX}/rollback`) {
        const result = rollback(opts.installRoot)
        send(result.ok ? 200 : 409, result)
        return
      }
      send(404, { error: 'not found' })
    },
  })
}
