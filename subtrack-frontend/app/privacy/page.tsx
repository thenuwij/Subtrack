import Link from 'next/link'
import type { Metadata } from 'next'
import { Logo } from '@/components/layout/Logo'
import { PublicFooter } from '@/components/layout/PublicFooter'

const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL

export const metadata: Metadata = {
  title: 'Privacy — Pocketday',
  description: 'How Pocketday accesses, processes, stores, and protects account and forwarded-email data.',
}

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <nav className="mx-auto flex max-w-4xl items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/" aria-label="Pocketday home"><Logo /></Link>
        <Link href="/login" className="text-sm font-medium text-primary hover:underline">Sign in</Link>
      </nav>
      <article className="prose prose-neutral mx-auto max-w-3xl px-5 py-12 dark:prose-invert sm:px-8">
        <p className="text-sm font-medium text-primary">Last updated 10 November 2026</p>
        <h1>Privacy policy</h1>
        <p>
          Pocketday shows what&apos;s free to spend until payday, after your bills and the money you set aside. This policy explains what information Pocketday accesses, why it is used, which services process it, how long it is kept, and the controls available to you. It applies to the Pocketday website, API, emails, forwarded bills, and AI assistant.
        </p>

        <h2>Information Pocketday handles</h2>
        <h3>Account and sign-in information</h3>
        <p>
          When you sign in, Google and Supabase provide identifiers and basic profile information such as your email address, display name, avatar, and account creation time. Supabase manages the sign-in session. Pocketday&apos;s API uses the verified Supabase user identifier to keep each user&apos;s records separate.
        </p>
        <h3>Financial organisation data</h3>
        <p>
          Pocketday stores information you enter or approve, including recurring-payment names, amounts, currencies, billing cadence, categories, due and lifecycle dates, shared-bill details, free trials, reminders, income preference, and essential or optional labels. For safe to spend it also stores your pay schedule, usual pay, buffer, any balance you type in and when you typed it, the savings and spending budgets you set aside each pay, and any spends you choose to log. Pocketday is not a bank ledger and does not connect to a bank account.
        </p>
        <h3>Demo sessions</h3>
        <p>
          The demo creates a private sandbox with sample data and no account. To limit abuse, Pocketday stores a one-way keyed hash of the visitor&apos;s network address with each demo, never the address itself. A demo expires 24 hours after it starts. Expired demos, including anything typed into the assistant, are deleted the next time a new demo starts or the service restarts.
        </p>
        <h3>Assistant data</h3>
        <p>
          Pocketday stores assistant conversations, limited page context, proposed actions, confirmations, and cited alternative-research results so conversations survive refreshes and actions can be audited. Page context contains allow-listed route, filter, and record identifiers; it does not grant the assistant access to another user&apos;s records.
        </p>

        <h2>Bills you forward</h2>
        <p>
          Pocketday does not read your mailbox. To bring in bills from Gmail you set up a filter that forwards only matching emails to a private Pocketday address. Pocketday reads only the emails that filter forwards, and you can pause, replace or delete the address at any time.
        </p>
        <p>
          Raw emails are never stored. Pocketday keeps only derived fields: the merchant, amount, date and due date, plus a hashed message identifier used to avoid counting the same email twice. Emails that look sensitive, such as verification codes, password resets and health messages, are dropped without being kept. Before anything is sent to Anthropic&apos;s API for classification, Pocketday removes personal details such as email addresses, phone numbers, card digits, addresses, reference numbers and links, and sends only a short excerpt.
        </p>

        <h2>How information is used</h2>
        <ul>
          <li>Operate sign-in and keep records scoped to the correct user.</li>
          <li>Calculate recurring-cost equivalents, forecast expected charges, and work out what&apos;s free to spend until payday.</li>
          <li>Find possible recurring payments in the bills you forward, for you to review.</li>
          <li>Show in-app reminders, free trials, data-quality warnings, and possible duplicates.</li>
          <li>Send the emails you turn on: payment reminders, the payday email, and payday alerts.</li>
          <li>Count pseudonymous usage, as described below, to see whether Pocketday is useful.</li>
          <li>Answer assistant questions and prepare changes that require your confirmation.</li>
          <li>Protect, diagnose, and improve the reliability and security of the service.</li>
        </ul>

        <h2>AI processing and automated decisions</h2>
        <p>
          Anthropic processes redacted candidate email excerpts, assistant messages, and the minimum relevant recurring-payment context needed for the requested feature. When you ask for cheaper alternatives, the payment&apos;s name, category, price and cadence, plus any requirements you give, are redacted in the same way and then used to search the web for current prices. AI results can be wrong. Findings from forwarded bills enter a review queue, and every AI-proposed data change remains inert until you confirm it. Pocketday does not make investment, credit, insurance, employment, or other legally significant decisions about users.
        </p>

        <h2>Emails</h2>
        <p>All emails are optional and off by default. There are two switches in Account: payment reminders, and the payday email and alerts (which you can also turn on during setup). To deliver them, Pocketday shares your account email address and the email&apos;s content with Resend. A reminder contains a payment name and date. The payday email contains your usual pay or balance, the names, dates and amounts of bills before your next payday, your set-asides, your buffer and what&apos;s free to spend. An alert contains a shortfall amount or a trial&apos;s name, end date and price. Pocketday keeps delivery metadata and a copy of each email to prevent duplicate sends. You can turn either switch off in Account at any time. Deleting your Pocketday app data removes these settings and delivery records.</p>

        <h2>Pseudonymous usage counts</h2>
        <p>To learn whether Pocketday is useful, it counts a few actions: starting and finishing setup, first seeing your number, opening Home (at most once a day), checking whether you can afford something, updating your balance, logging a spend, and opening the link in a payday email. Each count stores only the action&apos;s name, the time, and a keyed hash of your account identifier (a pseudonym, not your identity), so returning users can be counted without storing who they are. Counts never include amounts, payment names, or email content. Demo sessions are not counted. Deleting your Pocketday app data deletes your counts.</p>
        <h2>Service providers and disclosure</h2>
        <p>
          Pocketday uses Google for sign-in, Supabase for authentication, Neon for the application database, Render for the API, Vercel for the website, Anthropic for AI processing, Resend for email delivery, and Frankfurter for exchange-rate data. Providers process information for their stated technical role and under their own terms and privacy practices. Information may be processed in countries where these providers operate. Pocketday may also disclose information when legally required or necessary to protect users and the service. Pocketday does not sell personal information.
        </p>

        <h2>Retention</h2>
        <ul>
          <li>Recurring-payment records, pay details, set-asides, logged spends, reminders, preferences, derived findings from forwarded bills, and assistant history remain until you delete them or delete your Pocketday app data.</li>
          <li>Pseudonymous usage counts remain until you delete your Pocketday app data.</li>
          <li>Forwarded emails are processed when they arrive and their content is not retained in Pocketday&apos;s database.</li>
          <li>Expired demo sandboxes and their hashed visitor identifier are deleted the next time a demo starts or the service restarts.</li>
          <li>Alternative-research cache entries stop being used after approximately 24 hours; an expired database row may remain until your app data is deleted.</li>
          <li>Operational and security logs may be retained for the periods configured by the relevant hosting provider. Pocketday avoids intentionally logging email bodies, assistant financial content, and raw external error bodies.</li>
        </ul>

        <h2>Your choices and controls</h2>
        <ul>
          <li>You can use core tracking without forwarding anything, and can pause, replace or delete your forwarding address at any time.</li>
          <li>Deleting your forwarding address stops new bills arriving. Previously approved payment records remain until you delete them.</li>
          <li>You can approve, correct, dismiss, edit, pause, end, or delete app records from Pocketday.</li>
          <li>You can download an authenticated JSON export from Account. It excludes refresh tokens, shared exchange-rate cache data, pseudonymous usage counts, and the external Supabase identity.</li>
          <li>You can permanently delete all user-owned Pocketday application records from Account using an exact confirmation phrase.</li>
        </ul>
        <p>
          App-data deletion removes Pocketday&apos;s database records and signs the current browser out. It does not delete the identity held by Supabase because the current API is not configured with Supabase administrator credentials. If you sign in again, a new empty Pocketday data set can be created. This limitation will remain disclosed until external identity deletion is implemented and verified.
        </p>

        <h2>Cookies and local browser storage</h2>
        <p>
          Supabase uses browser storage and cookies needed to maintain authentication. Pocketday also stores limited interface preferences, such as theme and assistant panel size or view choice. Pocketday does not currently use advertising cookies.
        </p>

        <h2>Security</h2>
        <p>
          Controls include API verification of access tokens, user-scoped database queries, signed delivery of forwarded email, restricted CORS configuration, bounded external calls, and confirmation-gated AI actions with expiry and replay protection. Data is protected in transit using HTTPS in production. No internet service can promise absolute security.
        </p>

        <h2>Children</h2>
        <p>
          Pocketday is not directed to children. Do not use the service if you are not legally able to consent to its data handling in your location.
        </p>

        <h2>Policy changes</h2>
        <p>
          Material changes will be reflected on this page with an updated date. If a change materially affects how forwarded email is used, Pocketday will provide notice appropriate to the change before relying on it.
        </p>

        <h2>Contact</h2>
        <p>
          For privacy questions, access concerns, or deletion assistance, {SUPPORT_EMAIL ? (
            <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
          ) : (
            <>you can request a data export or deletion from the Account page. A support email will be listed here. Do not post personal or financial information in a public issue.</>
          )}
        </p>
      </article>
      <PublicFooter />
    </main>
  )
}
