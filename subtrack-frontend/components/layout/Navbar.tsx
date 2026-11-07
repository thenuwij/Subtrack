'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { LayoutDashboard, CreditCard, LogOut, UserCircle, MailCheck, Sparkles } from 'lucide-react'
import { getDetected } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { signOut } from '@/lib/auth/session'
import { useCurrentUser } from '@/lib/hooks/useCurrentUser'
import { UserAvatar } from '@/components/layout/UserAvatar'
import { Logo, LogoMark } from '@/components/layout/Logo'

const links = [
  { href: '/dashboard',     label: 'Dashboard',     icon: LayoutDashboard },
  { href: '/subscriptions', label: 'Payments',      icon: CreditCard },
  { href: '/review',        label: 'Inbox',         icon: MailCheck },
  { href: '/assistant',     label: 'Assistant',     icon: Sparkles },
  { href: '/account',       label: 'Account',       icon: UserCircle },
]

export default function Navbar() {
  const pathname = usePathname()
  const router = useRouter()
  const detected = useApi(apiKeys.detected('pending'), token => getDetected(token, 'pending'))
  const pendingCount = detected.data?.length ?? 0
    const currentUser = useCurrentUser()

  async function handleLogout() {
    await signOut()
    router.push('/login')
  }

  function renderNavItems(mobile = false) {
    return links.map(({ href, label, icon: Icon }) => {
      const active = pathname === href || pathname.startsWith(`${href}/`)
      return (
        <Link
          key={href}
          href={href}
          data-tour={`nav-${href.slice(1)}`}
          aria-current={active ? 'page' : undefined}
          className={mobile
            ? `relative flex min-w-0 flex-1 flex-col items-center gap-1 rounded-lg px-1 py-2 text-[10px] font-medium transition-colors ${
                active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
              }`
            : `relative flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors ${
                active
                  ? 'bg-muted font-medium text-foreground'
                  : 'text-muted-foreground hover:text-foreground'
              }`
          }
        >
          {mobile ? <Icon className="h-4 w-4 shrink-0" /> : null}
          <span className={mobile ? 'truncate' : undefined}>{label}</span>
          {href === '/review' && pendingCount > 0 && (
            <span
              aria-label={`${pendingCount} waiting for review`}
              className={mobile
                ? 'absolute right-[calc(50%-18px)] top-1 rounded-full bg-primary px-1 text-[9px] font-semibold leading-4 text-primary-foreground'
                : 'ml-auto rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold leading-none text-primary-foreground'
              }
            >
              {pendingCount}
            </span>
          )}
        </Link>
      )
    })
  }

  return (
    <>
      {/* Mobile top bar */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center border-b border-border bg-sidebar/80 px-4 backdrop-blur-xl md:hidden">
        <Link href="/dashboard" className="flex items-center gap-2" aria-label="Subtrack dashboard">
          <LogoMark className="h-6 w-6" />
          <span className="text-sm font-semibold tracking-tight text-foreground">Subtrack</span>
        </Link>
        <button
          type="button"
          onClick={handleLogout}
          className="ml-auto flex h-9 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </button>
      </header>

      {/* Desktop: one slim bar across the top, so the page gets the full width. */}
      <header className="sticky top-0 z-40 hidden h-14 items-center gap-6 border-b border-border bg-background/80 px-6 backdrop-blur-xl md:flex">
        <Link href="/dashboard" aria-label="Subtrack dashboard" className="shrink-0">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1" aria-label="Main">
          {renderNavItems()}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <Link
            href="/account"
            title={currentUser.email || 'Your account'}
            aria-label="Your account"
            className="rounded-full p-1 transition-colors hover:bg-muted"
          >
            <UserAvatar
              name={currentUser.name}
              email={currentUser.email}
              avatarUrl={currentUser.avatarUrl}
              className="h-7 w-7 text-xs"
            />
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            title="Sign out"
            aria-label="Sign out"
            className="flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      <nav
        className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-card/80 px-1 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden"
        aria-label="Main"
      >
        {renderNavItems(true)}
      </nav>
    </>
  )
}
