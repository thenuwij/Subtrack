import { test } from 'node:test'
import { strict as assert } from 'node:assert'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { assertSharedStyles, checkProductionCss } from './check-production-css.mjs'

test('rejects the deployed regression: utility styles present, shared component styles missing', () => {
  assert.throws(() => assertSharedStyles('@layer components;@layer utilities{.text-sm{font-size:14px}}'), /page-heading/)
})

test('an unrelated CSS file cannot hide a missing linked stylesheet', () => {
  const root = mkdtempSync(join(tmpdir(), 'subtrack-css-'))
  try {
    mkdirSync(join(root, 'server/app'), { recursive: true })
    mkdirSync(join(root, 'static'), { recursive: true })
    writeFileSync(join(root, 'server/app/dashboard.html'), '<link rel="stylesheet" href="/_next/static/missing.css">')
    writeFileSync(join(root, 'static/unrelated.css'), '.page-heading{font-size:28px}')
    assert.throws(() => checkProductionCss(root), /Missing production CSS asset/)
  } finally { rmSync(root, { recursive: true, force: true }) }
})

test('falls back to the client manifest when a page is not prerendered', () => {
  const root = mkdtempSync(join(tmpdir(), 'subtrack-css-'))
  const css = '.page-heading{font-size:28px;font-weight:700;letter-spacing:0}.page-description{line-height:1.5;color:#555}'
    + '.eyebrow{font-size:12px;text-transform:uppercase}.money-hero{background:#fff;border:0;padding:8px;border-radius:8px}'
    + '.page-shell{max-width:80rem;padding-inline:16px}.assistant-page{flex:1;min-height:0}'
  try {
    mkdirSync(join(root, 'static/chunks'), { recursive: true })
    writeFileSync(join(root, 'static/chunks/app.css'), css)
    for (const page of ['dashboard', 'subscriptions/save', 'assistant']) {
      const dir = join(root, 'server/app/(dashboard)', page)
      mkdirSync(dir, { recursive: true })
      const entry = { entryCSSFiles: { '[project]/app/layout': [{ path: 'static/chunks/app.css', inlined: false }] } }
      writeFileSync(join(dir, 'page_client-reference-manifest.js'),
        `globalThis.__RSC_MANIFEST = globalThis.__RSC_MANIFEST || {};\nglobalThis.__RSC_MANIFEST["/${page}/page"] = ${JSON.stringify(entry)};`)
    }
    assert.doesNotThrow(() => checkProductionCss(root))
    rmSync(join(root, 'static/chunks/app.css'))
    assert.throws(() => checkProductionCss(root), /Missing production CSS asset/)
  } finally { rmSync(root, { recursive: true, force: true }) }
})
