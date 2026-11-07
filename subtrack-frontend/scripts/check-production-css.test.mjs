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
