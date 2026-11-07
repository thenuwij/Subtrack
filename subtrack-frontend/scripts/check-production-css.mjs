import { readFileSync, existsSync } from 'node:fs'
import { resolve, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

// Inspect only CSS actually linked by the rendered page, not old files that
// might still exist in the build directory after a cached build.
export function assertSharedStyles(css) {
  const required = {
    'page-heading': ['font-size:', 'font-weight:', 'letter-spacing:'],
    'page-description': ['line-height:', 'color:'],
    eyebrow: ['font-size:', 'text-transform:uppercase'],
    'money-hero': ['background:', 'border:', 'padding:', 'border-radius:'],
    'page-shell': ['max-width:', 'padding-inline:'],
    'assistant-page': ['flex:', 'min-height:'],
  }
  for (const [name, properties] of Object.entries(required)) {
    const declarations = [...css.matchAll(new RegExp(`\\.${name}\\s*\\{([^}]*)\\}`, 'g'))]
      .map(match => match[1].replace(/\s+/g, '')).join(';')
    for (const property of properties) {
      if (!declarations.includes(property)) {
        throw new Error(`Production CSS is missing ${name}: ${property}. Refusing to ship incomplete shared styles.`)
      }
    }
  }
}

export function checkProductionCss(buildDir = '.next') {
  const root = resolve(buildDir)
  for (const page of ['dashboard', 'subscriptions/save', 'assistant']) {
    const html = readFileSync(resolve(root, 'server/app', `${page}.html`), 'utf8')
    const assets = [...html.matchAll(/href="([^"?#]+\.css)(?:[?#][^"]*)?"/g)]
      .map(match => match[1]).filter(url => url.startsWith('/_next/static/'))
    if (!assets.length) throw new Error(`No production stylesheets linked by ${page}`)
    const css = assets.map(url => {
      const path = resolve(root, url.slice('/_next/'.length))
      if (relative(root, path).startsWith('..') || !existsSync(path)) {
        throw new Error(`Missing production CSS asset: ${url}`)
      }
      return readFileSync(path, 'utf8')
    }).join('\n')
    assertSharedStyles(css)
  }
  console.log('Production CSS verified: overview, savings and assistant share complete styles.')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  checkProductionCss()
}
