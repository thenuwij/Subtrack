'use client'
import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { LogoMark } from '@/components/layout/Logo'
import { useHydrated } from '@/lib/hooks/useHydrated'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Check, Eye, EyeOff } from 'lucide-react'
import { AuthPreviewBanner, AuthPreviewPanel } from '@/components/auth/AuthPreviewPanel'
import { GoogleIcon } from '@/components/auth/GoogleIcon'
import { authErrorMessage, MIN_PASSWORD_LENGTH, passwordProblem } from '@/lib/auth/errors'
import { endDemo, startDemo } from '@/lib/auth/session'

type Mode = 'signin' | 'signup'

export default function LoginPage() {
  const supabase = createClient()
  const router = useRouter()
  const [chosenMode, setMode] = useState<Mode | null>(null)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState<'email' | 'google' | 'demo' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [demoError, setDemoError] = useState<string | null>(null)
  // Set when a sign-up needs the emailed confirmation link before it has a
  // session. Whether that step exists at all is a Supabase project setting,
  // so both outcomes are handled rather than assumed.
  const [checkEmail, setCheckEmail] = useState<string | null>(null)

  const hydrated = useHydrated()
  const reason = hydrated
    ? new URLSearchParams(window.location.search).get('reason')
    : null
  const sessionExpired = reason === 'session_expired'
  const gmailRevocationFailed = reason === 'data_deleted_gmail_revoke_failed'
  const dataDeleted = reason === 'data_deleted' || gmailRevocationFailed
  const passwordUpdated = reason === 'password_updated'
  const linkInvalid = reason === 'link_invalid'
  const requestedMode = hydrated
    ? new URLSearchParams(window.location.search).get('mode')
    : null
  const mode: Mode = chosenMode ?? (requestedMode === 'signup' ? 'signup' : 'signin')

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
    setPassword('')
  }

  async function handleEmailSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    endDemo()

    if (mode === 'signup') {
      const problem = passwordProblem(password)
      if (problem) {
        setError(problem)
        return
      }
    }

    setBusy('email')
    try {
      if (mode === 'signin') {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
        // A full document load, not a client transition: it guarantees the proxy
        // and every server component re-run against the cookies this call just
        // wrote. `replace` so Back doesn't return to a filled-in sign-in form.
        window.location.replace('/dashboard')
        return
      }

      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
      })
      if (error) throw error

      if (data.session) {
        window.location.replace('/dashboard')
        return
      }
      // No session means confirmation is required. Supabase deliberately
      // returns the same shape for an address that already has an account,
      // so this message must not imply the address was or wasn't new.
      setCheckEmail(email)
    } catch (e) {
      setError(authErrorMessage(
        e,
        mode === 'signin'
          ? 'Could not sign you in. Please try again.'
          : 'Could not create your account. Please try again.',
      ))
      setBusy(null)
    }
  }

  async function handleDemo() {
    setBusy('demo')
    setError(null)
    setDemoError(null)
    try {
      await startDemo()
      router.push('/dashboard')
    } catch (demoError) {
      setDemoError(demoError instanceof Error ? demoError.message : 'The demo could not be started.')
      setBusy(null)
    }
  }

  async function handleGoogleLogin() {
    setBusy('google')
    setError(null)
    endDemo()
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      })
      // A failure here used to leave the button looking like it did nothing.
      if (error) throw error
    } catch (e) {
      setError(authErrorMessage(e, 'Could not start sign-in. Please try again.'))
      setBusy(null)
    }
  }

  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-2">
      <main className="flex min-h-screen flex-col px-6 py-10 sm:px-12 lg:px-20">
        <Link href="/" aria-label="Subtrack home" className="inline-flex w-fit">
          <LogoMark className="h-9 w-9" />
        </Link>

        <div className="flex flex-1 items-center justify-center py-12">
          <div className="w-full max-w-sm">
            {checkEmail ? (
              <>
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                  Confirm your email
                </h1>
                <p className="mt-3 text-sm text-muted-foreground">
                  If <span className="font-medium text-foreground">{checkEmail}</span> can
                  be used to create an account, a confirmation link is on its way. Open it
                  to finish signing up.
                </p>
                <p className="mt-4 text-sm text-muted-foreground">
                  Nothing arrived? Check your spam folder, or{' '}
                  <button
                    type="button"
                    className="underline hover:text-foreground"
                    onClick={() => { setCheckEmail(null); setBusy(null); switchMode('signup') }}
                  >
                    try a different address
                  </button>
                  .
                </p>
              </>
            ) : (
              <>
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                  {mode === 'signin' ? 'Sign in to Subtrack' : 'Create your account'}
                </h1>
                <p className="mt-2 text-sm text-muted-foreground">
                  {mode === 'signin'
                    ? 'Welcome back.'
                    : 'Free to use. You can connect Gmail later.'}
                </p>
                <AuthPreviewBanner />

                {sessionExpired ? (
                  <p role="status" className="mt-6 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2.5 text-sm text-foreground">
                    Your session expired. Sign in again to continue.
                  </p>
                ) : linkInvalid ? (
                  <p role="status" className="mt-6 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2.5 text-sm text-foreground">
                    That link has expired or was already used. Sign in, or request a new
                    one from <Link className="underline" href="/forgot-password">forgot password</Link>.
                  </p>
                ) : passwordUpdated ? (
                  <p role="status" className="mt-6 rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
                    Your password was updated. Sign in with it below.
                  </p>
                ) : dataDeleted ? (
                  <p role="status" className="mt-6 rounded-lg border border-border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
                    Your Subtrack app data was deleted and you have been signed out.
                    {gmailRevocationFailed
                      ? ' Google could not be reached to revoke the former Gmail permission, so remove Subtrack from your Google Account permissions as well.'
                      : ''}
                  </p>
                ) : null}

                <Button
                  type="button"
                  variant="outline"
                  onClick={handleGoogleLogin}
                  disabled={busy !== null}
                  className="mt-8 h-10 w-full gap-2"
                >
                  <GoogleIcon className="h-4 w-4" />
                  {busy === 'google' ? 'Opening Google…' : 'Continue with Google'}
                </Button>

                <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  or with email
                  <span className="h-px flex-1 bg-border" />
                </div>

                <form onSubmit={handleEmailSubmit} className="space-y-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={e => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="h-10"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex items-baseline justify-between">
                      <Label htmlFor="password">Password</Label>
                      {mode === 'signin' ? (
                        <Link
                          href="/forgot-password"
                          className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                        >
                          Forgot password?
                        </Link>
                      ) : null}
                    </div>
                    <div className="relative">
                      <Input
                        id="password"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                        required
                        value={password}
                        onChange={e => setPassword(e.target.value)}
                        aria-describedby={mode === 'signup' ? 'password-rule' : undefined}
                        className="h-10 pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(shown => !shown)}
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        aria-pressed={showPassword}
                        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                    {mode === 'signup' ? (
                      <p
                        id="password-rule"
                        className={`flex items-center gap-1.5 text-xs ${
                          password.length >= MIN_PASSWORD_LENGTH ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'
                        }`}
                      >
                        <Check className="h-3.5 w-3.5" aria-hidden="true" />
                        At least {MIN_PASSWORD_LENGTH} characters
                      </p>
                    ) : null}
                  </div>

                  {error && (
                    <p role="alert" className="text-sm text-destructive">
                      {error}
                    </p>
                  )}

                  <Button type="submit" className="h-10 w-full" disabled={busy !== null}>
                    {busy === 'email'
                      ? (mode === 'signin' ? 'Signing in…' : 'Creating account…')
                      : (mode === 'signin' ? 'Sign in' : 'Create account')}
                  </Button>
                </form>


                <p className="mt-8 text-sm text-muted-foreground">
                  {mode === 'signin' ? 'No account yet? ' : 'Already have an account? '}
                  <button
                    type="button"
                    className="font-medium text-primary hover:underline"
                    onClick={() => switchMode(mode === 'signin' ? 'signup' : 'signin')}
                  >
                    {mode === 'signin' ? 'Create one' : 'Sign in'}
                  </button>
                </p>

                <div className="mt-8 rounded-xl border border-border p-4">
                  <p className="text-sm font-medium text-foreground">Just looking?</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Explore Subtrack with sample data. No sign-up needed.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    className="mt-3 h-10 w-full"
                    onClick={() => void handleDemo()}
                    disabled={busy !== null}
                  >
                    {busy === 'demo' ? 'Setting up the demo…' : 'Try the demo'}
                  </Button>
                </div>
                {demoError && (
                  <p role="alert" className="mt-2 text-sm text-destructive">
                    {demoError}
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          By continuing you agree to the <Link className="underline hover:text-foreground" href="/terms">terms</Link> and <Link className="underline hover:text-foreground" href="/privacy">privacy policy</Link>.
        </p>
      </main>
      <AuthPreviewPanel />
    </div>
  )
}
