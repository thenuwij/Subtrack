import type { NextConfig } from "next";

function origin(value: string | undefined): string | null {
  try { return value ? new URL(value).origin : null } catch { return null }
}

const isDev = process.env.NODE_ENV !== 'production'
const supabaseOrigin = origin(process.env.NEXT_PUBLIC_SUPABASE_URL)
const apiOrigin = origin(process.env.NEXT_PUBLIC_API_URL)
const connectSrc = [
  "'self'",
  supabaseOrigin,
  supabaseOrigin?.replace(/^https:/, 'wss:'),
  apiOrigin,
  isDev ? 'http://localhost:* http://127.0.0.1:* ws://localhost:*' : null,
].filter(Boolean).join(' ')

// 'unsafe-inline' scripts are required because Next.js emits inline bootstrap
// scripts and no per-request nonce is set up; 'unsafe-eval' is dev-only (React
// debugging). Moving to nonces would tighten this further.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https://lh3.googleusercontent.com",
  `connect-src ${connectSrc}`,
  "font-src 'self' data:",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "object-src 'none'",
].join('; ')

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Release builds must transform the current stylesheet rather than restore
  // persisted compiler output from a previous deployment.
  experimental: { turbopackFileSystemCacheForBuild: false },
  async headers() {
    return [{
      source: '/:path*',
      headers: [
        { key: 'X-Content-Type-Options', value: 'nosniff' },
        { key: 'X-Frame-Options', value: 'DENY' },
        { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        {
          key: 'Permissions-Policy',
          value: 'camera=(), microphone=(self), geolocation=(), browsing-topics=()',
        },
        {
          key: 'Content-Security-Policy',
          value: csp,
        },
        { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains' },
      ],
    }]
  },
};

export default nextConfig;
