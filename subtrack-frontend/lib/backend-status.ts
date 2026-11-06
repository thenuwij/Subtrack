import { API_URL } from '@/lib/config'

const AWAKE_KEY = 'subtrack-backend-awake-at'
// The free hosting plan sleeps after about 15 idle minutes, so a check newer
// than this is trusted and the waking screen is skipped.
const TRUST_MS = 10 * 60 * 1000

/** One quick request to the API's root. True only on a 2xx answer. */
export async function pingBackend(timeoutMs = 10_000): Promise<boolean> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API_URL}/`, { cache: 'no-store', signal: controller.signal })
    if (response.ok) markBackendAwake()
    return response.ok
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

export function markBackendAwake() {
  try {
    sessionStorage.setItem(AWAKE_KEY, String(Date.now()))
  } catch {
    // Storage can be blocked; the gate simply checks again.
  }
}

export function backendRecentlyAwake(): boolean {
  try {
    const at = Number(sessionStorage.getItem(AWAKE_KEY))
    return Number.isFinite(at) && Date.now() - at < TRUST_MS
  } catch {
    return false
  }
}

/** Fire-and-forget: starts a sleeping server waking while the user signs in. */
export function warmBackend() {
  if (backendRecentlyAwake()) return
  void pingBackend(60_000)
}
