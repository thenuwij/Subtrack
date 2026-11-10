'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { House, CreditCard, LogOut, MessageCircle, Settings2 } from 'lucide-react'
import { getDetected } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { signOut } from '@/lib/auth/session'
import { useCurrentUser } from '@/lib/hooks/useCurrentUser'
import { UserAvatar } from '@/components/layout/UserAvatar'
import { Logo, LogoMark } from '@/components/layout/Logo'

const links: { href: string; label: string; icon: typeof House }[] = [
  { href: '/dashboard', label: 'Home', icon: House },
  { href: '/subscriptions', label: 'Bills', icon: CreditCard },
  { href: '/assistant', label: 'Ask', icon: MessageCircle },
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

  function navItems(mobile = false) {
    return links.map(({ href, label, icon: Icon }) => {
      const active = pathname === href || pathname.startsWith(`${href}/`) || (href === '/subscriptions' && pathname === '/review')
      return (
        <Link key={href} href={href} data-tour={`nav-${href.slice(1)}`}
          aria-current={active ? 'page' : undefined}
          className={mobile
            ? `relative flex min-h-16 min-w-0 flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors ${active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'}`
            : `flex min-h-11 items-center gap-3 rounded-xl px-3 text-[13px] font-medium transition-colors ${active ? 'bg-card text-primary shadow-sm' : 'text-foreground hover:bg-card/60'}`}>
          <span className="relative"><Icon className={mobile ? 'h-5 w-5' : 'h-[18px] w-[18px]'} strokeWidth={active ? 2 : 1.7} />
            {mobile && href === '/subscriptions' && pendingCount > 0 ? <span className="absolute -right-2 -top-1 h-2 w-2 rounded-full bg-primary ring-2 ring-card" /> : null}
          </span>
          <span>{label}</span>
          {href === '/subscriptions' && pendingCount > 0 ? <span className={mobile ? 'sr-only' : 'ml-auto rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] tabular-nums text-primary'}>{pendingCount}<span className="sr-only"> waiting for review</span></span> : null}
        </Link>
      )
    })
  }

  return (
    <>
      <a href="#main-content" className="sr-only z-[100] rounded-lg bg-card px-4 py-3 focus:not-sr-only focus:fixed focus:left-4 focus:top-4">Skip to content</a>
      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-border/70 bg-background/90 px-5 backdrop-blur-xl md:hidden">
        <Link href="/dashboard" className="flex items-center gap-2.5" aria-label="Subtrack overview"><LogoMark className="h-7 w-7" /><span className="text-[15px] font-semibold tracking-tight">Subtrack</span></Link>
        <Link href="/account" aria-label="Account and settings" className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-muted"><UserAvatar name={currentUser.name} email={currentUser.email} avatarUrl={currentUser.avatarUrl} className="h-8 w-8 text-xs" /></Link>
      </header>
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-56 flex-col border-r border-sidebar-border/60 bg-sidebar px-4 py-8 md:flex lg:w-60">
        <Link href="/dashboard" aria-label="Subtrack overview" className="mb-12 px-3"><Logo /></Link>
        <p className="eyebrow mb-3 px-3">Your money</p>
        <nav aria-label="Main" className="space-y-1.5">{navItems()}</nav>
        <div className="mt-auto space-y-5 pt-10">
          <Link href="/account" data-tour="nav-account" aria-current={pathname === '/account' ? 'page' : undefined} className={`flex min-h-11 items-center gap-3 rounded-xl px-3 text-[13px] font-medium ${pathname === '/account' ? 'bg-card text-primary shadow-sm' : 'text-foreground hover:bg-card/60'}`}><Settings2 className="h-[18px] w-[18px]" strokeWidth={1.7} />Account & settings</Link>
          <div className="flex items-center gap-2 border-t border-sidebar-border/70 px-1 pt-5">
            <Link href="/account" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-lg p-1" aria-label="Your account"><UserAvatar name={currentUser.name} email={currentUser.email} avatarUrl={currentUser.avatarUrl} className="h-8 w-8 shrink-0 text-xs" /><span className="min-w-0"><span className="block truncate text-xs font-semibold">{currentUser.name || 'Your account'}</span><span className="block truncate text-[11px] text-muted-foreground">{currentUser.email || 'Personal workspace'}</span></span></Link>
            <button type="button" onClick={handleLogout} aria-label="Sign out" title="Sign out" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted-foreground hover:bg-card"><LogOut className="h-4 w-4" /></button>
          </div>
        </div>
      </aside>
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border/70 bg-card/95 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden">{navItems(true)}</nav>
    </>
  )
}
