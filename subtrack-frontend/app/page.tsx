import Link from 'next/link'
import type { Metadata } from 'next'
import { Mail, PiggyBank, Wallet } from 'lucide-react'
import { Logo } from '@/components/layout/Logo'
import { Button } from '@/components/ui/button'
import { PublicFooter } from '@/components/layout/PublicFooter'

export const metadata: Metadata = {
  title: 'Subtrack',
  description: 'Know what’s yours to spend until payday. Your bills and savings set aside first, no bank login.',
}

const FEATURES = [
  {
    icon: Mail,
    title: 'A payday email',
    body: 'On payday morning: the bills before your next pay, what you’ve set aside, and what’s free per day.',
  },
  {
    icon: PiggyBank,
    title: 'Set money aside first',
    body: 'Savings and spending pots like “Eating out, $60 a pay” come off before you see what’s free.',
  },
  {
    icon: Wallet,
    title: 'Can I afford it?',
    body: 'Type an amount and get a straight yes or no, with what you’d have left until payday.',
  },
]

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <Logo />
        <Button asChild size="sm">
          <Link href="/login">Sign in</Link>
        </Button>
      </nav>

      <section className="mx-auto grid max-w-6xl gap-12 px-5 pb-20 pt-16 sm:px-8 sm:pt-24 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-primary">For people paid weekly or fortnightly</p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-6xl">
            Know what&apos;s yours to spend until payday.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-7 text-muted-foreground sm:text-lg">
            Enter your pay and bills once. Subtrack sets aside what&apos;s already spoken for and tells you what&apos;s free, every payday. No tracking every coffee.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            {/* Not "Start with Google" any more — email sign-up exists, and
                naming only one provider reads as though it is the only way in. */}
            <Button asChild size="lg"><Link href="/login">Get started</Link></Button>
            <Button asChild size="lg" variant="outline"><Link href="/privacy">How your data is handled</Link></Button>
          </div>
          <p className="mt-4 text-xs leading-5 text-muted-foreground">
            Setup takes about three minutes. Subtrack never asks for your bank login.
          </p>
        </div>

        <div className="rounded-3xl bg-card p-6 shadow-sm ring-1 ring-foreground/5 sm:p-8" aria-label="Example of Subtrack's Home screen">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Safe to spend</p>
            <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-xs text-muted-foreground">Example</span>
          </div>
          <p className="mt-2 text-5xl font-semibold tracking-tight tabular-nums">$845</p>
          <p className="mt-2 text-sm text-muted-foreground">About $60 a day · payday Tue 24 Nov</p>
          <div className="mt-8 divide-y divide-border text-sm">
            {[
              ['Usual pay', '$1,400'],
              ['Rent, phone and streaming', '−$445'],
              ['Eating out pot', '−$60'],
              ['Buffer', '−$50'],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between py-2.5">
                <span className="text-muted-foreground">{label}</span>
                <span className="tabular-nums">{value}</span>
              </div>
            ))}
          </div>
          <div className="mt-6 rounded-2xl bg-primary/5 p-4">
            <p className="text-sm font-medium">Can I afford $120 on Friday?</p>
            <p className="mt-1 text-sm text-muted-foreground">Yes. You&apos;d have $725 left until payday.</p>
          </div>
        </div>
      </section>

      <section className="border-y border-border bg-card/40">
        <div className="mx-auto grid max-w-6xl gap-5 px-5 py-16 sm:px-8 md:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <article key={title} className="rounded-2xl bg-card p-6 shadow-sm">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <h2 className="mt-5 text-lg font-semibold tracking-tight">{title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-3xl px-5 py-16 text-center sm:px-8">
        <h2 className="text-3xl font-semibold tracking-tight">Your numbers, not your bank login.</h2>
        <p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-muted-foreground">
          You enter your pay and bills yourself, and nothing changes without your approval. Subtrack doesn&apos;t give investment or financial product advice. You can export or delete your data from Account at any time.
        </p>
        <Button asChild className="mt-7"><Link href="/login">Continue to Subtrack</Link></Button>
      </section>

      <PublicFooter />
    </main>
  )
}
