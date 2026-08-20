// SPDX-License-Identifier: MIT
/**
 * Build both plugin halves.
 * - Host half (`lib/index.js`): ESM for the harness process; only Node builtins
 *   and framework externals are used, so the bundle stays self-contained.
 * - Client half (`lib/client.js`): CJS wrapped in the web boot factory
 *   (`window.__ModuleLoader__.load({ id, factory })`), the format the
 *   client-module system materializes at `/plugins/<id>/client.js`.
 *   `react` stays external (the shell's own instance resolves at load time).
 */
import { build } from 'esbuild'
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')

const ID = 'dsh-aischat'
const HOST_EXTERNALS = ['@deepseek-ai/schemastery', '@deepseek-ai/dsh-settings']
// Client externals stay external at bundle time and resolve through the web
// ModuleLoader at runtime (same mechanism the shipped ui-* bundles use).
const CLIENT_EXTERNALS = [
  'react',
  'react/jsx-runtime',
  // Reuse the shipped Markdown/KaTeX renderer so AIsChat messages render
  // exactly like DSH conversation text (GFM + LaTeX + safe-HTML filtering).
  '@deepseek-ai/dsh-client-ui-primitives',
]

mkdirSync(join(root, 'lib'), { recursive: true })

await build({
  entryPoints: [join(root, 'src/index.ts')],
  bundle: true,
  format: 'esm',
  platform: 'node',
  target: 'es2024',
  outfile: join(root, 'lib/index.js'),
  sourcemap: true,
  external: HOST_EXTERNALS,
})

await build({
  entryPoints: [join(root, 'src/client.ts')],
  bundle: true,
  format: 'cjs',
  platform: 'browser',
  target: 'es2022',
  outfile: join(root, 'lib/client.js'),
  sourcemap: true,
  external: CLIENT_EXTERNALS,
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV ?? 'production'),
  },
  banner: {
    js: `window.__ModuleLoader__.load({ id: ${JSON.stringify(ID)}, factory: (require) => {\nvar module = { exports: {} }; var exports = module.exports;`,
  },
  footer: {
    js: 'return module.exports; } });',
  },
})

const clientBundle = readFileSync(join(root, 'lib/client.js'), 'utf8')
// Purity: the only @deepseek-ai packages allowed in the client bundle are the
// declared runtime externals (resolved by the web ModuleLoader). Anything else
// would mean a value import got bundled in, which must not happen.
const allowed = new Set(CLIENT_EXTERNALS.filter((id) => id.startsWith('@deepseek-ai/')))
for (const match of clientBundle.matchAll(/@deepseek-ai\/[a-z0-9-]+/g)) {
  if (!allowed.has(match[0])) {
    throw new Error(
      `client bundle purity: '@deepseek-ai/${match[0].slice('@deepseek-ai/'.length)}' must not reach the client bundle `
      + '(declare it in CLIENT_EXTERNALS if it is a runtime ModuleLoader dependency)',
    )
  }
}

console.log('built lib/index.js and lib/client.js')
