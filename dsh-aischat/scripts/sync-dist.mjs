// 把前端产物镜像进插件包 dist/。
//
// 为什么需要它：dist/ 是插件包的一部分（宿主半从 dist/ 服务 /aischat-ui/*），
// 但前端产物里混着**只属于仓库**的东西——docs/assets（README/推广图）不该随包分发。
// 手抄 cp -a 很容易把它们一起带上（35M 里有 3.8M 是文档，其中大头就是这些图），
// 所以同步只走这一个入口，排除清单也写在这里一处。
//
// 用法（前端在容器里构建，产物落在 frontend/dist）：
//   docker exec -w /app ai_group_frontend sh -c "BASE_URL=/aischat-ui/ node_modules/.bin/vite build"
//   node scripts/sync-dist.mjs
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC = join(__dirname, '../../frontend/dist')
const DST = join(__dirname, '../dist')

/** 相对 dist 根的排除清单：只属于仓库、不属于插件包的路径 */
const EXCLUDE = ['docs/assets']

if (!existsSync(SRC)) {
  console.error('没有找到前端产物：' + SRC + '\n先在 frontend 容器里构建（见文件顶部注释）。')
  process.exit(1)
}

const excluded = (rel) => EXCLUDE.some((e) => rel === e || rel.startsWith(e + '/'))

/** 递归复制，跳过排除项 */
function copy(from, to, rel = '') {
  mkdirSync(to, { recursive: true })
  for (const entry of readdirSync(from, { withFileTypes: true })) {
    const childRel = rel ? rel + '/' + entry.name : entry.name
    if (excluded(childRel)) continue
    const src = join(from, entry.name)
    const dst = join(to, entry.name)
    if (entry.isDirectory()) copy(src, dst, childRel)
    else if (entry.isFile()) cpSync(src, dst)
  }
}

rmSync(DST, { recursive: true, force: true })
copy(SRC, DST)
const kb = (dir) => {
  let total = 0
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name)
    total += entry.isDirectory() ? kb(p) : statSync(p).size
  }
  return total
}
console.log('dist 已同步（排除 ' + EXCLUDE.join(', ') + '）：' + Math.round(kb(DST) / 1048576) + ' MB')
