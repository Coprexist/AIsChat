// 自更新原语的真实换入/回滚验证。全程在临时目录进行，不触碰 profile 安装副本。
//
// 覆盖：状态判定（up-to-date / update-available）、hot 与 restart 两种 applyMode、
// 幂等重复换入、清单不符时的完整性闸门、以及回滚。
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { applyUpdate, computeStatus, manifestId, readManifest, rollback } from '../lib/index.js'

const REPO = fileURLToPath(new URL('..', import.meta.url))
const BACKEND = 'http://127.0.0.1:5228'

const sha = (p) => createHash('sha256').update(readFileSync(p)).digest('hex')

function copyArtifacts(from, to, manifest) {
  const rels = [...Object.keys(manifest.files), 'lib/manifest.json', 'package.json']
  for (const rel of rels) {
    const src = join(from, rel)
    if (!existsSync(src)) continue
    const dst = join(to, rel)
    mkdirSync(dirname(dst), { recursive: true })
    copyFileSync(src, dst)
  }
}

/** 改动一个产物并同步其清单摘要，得到更新的构建。 */
function touchArtifact(root, rel, marker) {
  const target = join(root, rel)
  writeFileSync(target, readFileSync(target, 'utf8') + `\n/*${marker}*/\n`, 'utf8')
  const manifestPath = join(root, 'lib/manifest.json')
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  manifest.files[rel] = sha(target)
  manifest.buildStamp = new Date().toISOString()
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8')
  return manifest
}

function assert(cond, message) {
  if (!cond) throw new Error('ASSERT FAILED: ' + message)
  console.log('  ok -', message)
}

const base = readManifest(REPO)
assert(base && Object.keys(base.files).length > 0, `源码构建清单存在（${base ? Object.keys(base.files).length : 0} 个产物）`)

const work = mkdtempSync(join(tmpdir(), 'aischat-plugin-update-'))
try {
  const install = join(work, 'install')
  const source = join(work, 'source')
  copyArtifacts(REPO, install, base)
  copyArtifacts(REPO, source, base)

  // 1. 同源同清单 -> up-to-date
  let status = await computeStatus(install, BACKEND, source)
  assert(status.state === 'up-to-date', `相同构建判为 up-to-date（实际 ${status.state}）`)

  // 2. 源码侧改动 client 产物 -> update-available 且 applyMode=hot
  touchArtifact(source, 'lib/client.js', 'client-updated')
  status = await computeStatus(install, BACKEND, source)
  assert(status.state === 'update-available', `构建不同判为 update-available（实际 ${status.state}）`)
  assert(status.applyMode === 'hot', `仅 client 变更时 applyMode=hot（实际 ${status.applyMode}）`)

  // 3. 换入 -> 内容与清单都对上
  const sourceManifest = readManifest(source)
  const applied = applyUpdate(install, source)
  assert(applied.ok, `换入成功（${applied.error ?? ''}）`)
  assert(applied.changed.includes('lib/client.js'), 'changed 报出 lib/client.js')
  assert(sha(join(install, 'lib/client.js')) === sourceManifest.files['lib/client.js'], '换入后文件内容与清单一致')
  assert(manifestId(readManifest(install)) === manifestId(sourceManifest), '换入后身份与源一致')

  // 4. 幂等：再换一次不报错，且没有新增改动
  const again = applyUpdate(install, source)
  assert(again.ok && again.changed.length === 0, `重复换入幂等（changed=${again.changed.length}）`)

  // 5. 完整性闸门：源码被改但未重新构建 -> 拒绝，且不半途换入
  writeFileSync(join(source, 'lib/client.js'), 'tampered', 'utf8')
  const tampered = applyUpdate(install, source)
  assert(!tampered.ok && /清单不符/.test(tampered.error ?? ''), `篡改源码被拒绝（${tampered.error}）`)
  assert(sha(join(install, 'lib/client.js')) === sourceManifest.files['lib/client.js'], '被拒绝后安装副本未被改动')

  // 6. host 半变更 -> applyMode=restart
  copyArtifacts(REPO, source, base)
  touchArtifact(source, 'lib/index.js', 'host-updated')
  status = await computeStatus(install, BACKEND, source)
  assert(status.applyMode === 'restart', `host 变更时 applyMode=restart（实际 ${status.applyMode}）`)
  const hostApplied = applyUpdate(install, source)
  assert(hostApplied.ok && hostApplied.applyMode === 'restart', 'host 变更换入成功并标记需重启')

  // 7. 回滚：回到换入前的 host 产物
  const rolled = rollback(install)
  assert(rolled.ok, `回滚成功（${rolled.error ?? ''}）`)
  assert(sha(join(install, 'lib/index.js')) === base.files['lib/index.js'], '回滚后 host 产物恢复为上一版')
} finally {
  rmSync(work, { recursive: true, force: true })
}

console.log('UPDATE-TEST OK')
