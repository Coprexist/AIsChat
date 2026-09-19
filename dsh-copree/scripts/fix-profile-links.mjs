// 修复 DSH profile 的 pnpm-lock.yaml 里被 realpath 分歧写歪的本地依赖路径。
//
// 背景：DSH_HOME 默认 /root/.dsh 是指向 /data_s001/relocated/dsh-home 的符号链接，
// 两者还落在不同的文件系统上。pnpm 写 lockfile 时按符号链接路径计算 file: 依赖的
// 相对路径，解析时却按真实路径计算，于是把 file:/tmp/x 记成 ../../../../tmp/x
// （少一层），解析结果指向不存在的 /data_s001/tmp/x。
//
// 本脚本不去猜哪条路径"看起来对"，而是按 bug 模型精确重算：
//   错误形式 = relative(符号链接路径, 目标)
//   正确形式 = relative(真实路径,   目标)
// 目标取自 package.json 里 file: 规格的绝对路径。因此它是幂等的：已经正确时
// 找不到错误形式，直接报告 0 处改动。
//
// 用法：
//   node scripts/fix-profile-links.mjs              # 检查并修复（默认 DSH_HOME/profiles/web）
//   node scripts/fix-profile-links.mjs --dry-run    # 只报告，不写盘
//   node scripts/fix-profile-links.mjs --dir <profile> --lockfile <path>
import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { isAbsolute, join, relative, resolve } from 'node:path'

const argv = process.argv.slice(2)
const flag = (name) => argv.includes(name)
const value = (name, fallback) => {
  const i = argv.indexOf(name)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}

const dshHome = process.env.DSH_HOME ?? join(homedir(), '.dsh')
const profileDir = value('--dir', join(dshHome, 'profiles', 'web'))
const lockPath = value('--lockfile', join(profileDir, 'pnpm-lock.yaml'))
const dryRun = flag('--dry-run')

for (const p of [profileDir, lockPath]) {
  if (!existsSync(p)) {
    console.error(`找不到 ${p}`)
    process.exit(1)
  }
}

const pkg = JSON.parse(readFileSync(join(profileDir, 'package.json'), 'utf8'))
const linkBase = profileDir
const realBase = realpathSync(profileDir)

if (linkBase === realBase) {
  console.log(`profile 路径本身就是真实路径（${realBase}），不存在 realpath 分歧，无需处理。`)
  process.exit(0)
}

let yaml = readFileSync(lockPath, 'utf8')
console.log(`符号链接路径 ${linkBase}`)
console.log(`真实路径     ${realBase}`)
console.log(`lockfile     ${lockPath}${dryRun ? '（dry-run）' : ''}`)
console.log('')

let total = 0
for (const [name, spec] of Object.entries(pkg.dependencies ?? {})) {
  if (typeof spec !== 'string' || !spec.startsWith('file:')) continue
  const raw = spec.slice('file:'.length)
  const target = isAbsolute(raw) ? raw : resolve(profileDir, raw)
  if (!existsSync(target)) {
    console.log(`跳过 ${name}：依赖目标不存在 ${target}`)
    continue
  }
  const wrongRel = relative(linkBase, target).split('\\').join('/')
  const rightRel = relative(realBase, target).split('\\').join('/')
  if (wrongRel === rightRel) {
    console.log(`跳过 ${name}：符号链接与真实路径同源，相对路径一致`)
    continue
  }
  // 必须按整词匹配：4 层的错误形式恰好是 5 层正确形式的子串，
  // 用 split/join 会在已经正确的文件上"匹配"并每跑一次多加一层。
  const escaped = wrongRel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const pattern = new RegExp(`(?<![\\w./-])${escaped}(?![\\w/-])`, 'g')
  const hits = (yaml.match(pattern) ?? []).length
  if (hits === 0) {
    console.log(`\u2713 ${name}：已是正确形式（${rightRel}）`)
    continue
  }
  yaml = yaml.replace(pattern, rightRel)
  total += hits
  console.log(`\u2192 ${name}：修正 ${hits} 处\n    ${wrongRel}\n  \u21b3 ${rightRel}`)
}

console.log('')
if (total === 0) {
  console.log('无需改动：lockfile 里没有写歪的相对路径。')
  process.exit(0)
}
if (dryRun) {
  console.log(`dry-run：将修正 ${total} 处，未写盘。`)
  process.exit(0)
}
writeFileSync(lockPath + '.bak-links', readFileSync(lockPath), 'utf8')
writeFileSync(lockPath, yaml, 'utf8')
console.log(`已修正 ${total} 处；原文件备份为 ${lockPath}.bak-links`)
