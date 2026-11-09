# Subtrack Product Direction

Read this before starting any product work. It has three parts:

1. **[The product today](#part-1-the-product-today)**: what's live now.
2. **[Vision and problem](#part-2-vision-and-problem)**: why Subtrack exists and where it's heading.
3. **[Build plan](#part-3-build-plan)**: phases, status and the rules each phase must meet.

---

# Part 1: The product today

*As of 7 November 2026.*

**Subtrack tells young Australians paid weekly or fortnightly how much they can safely spend until payday,** by combining their balance with every bill and subscription due before then. Gmail finds those payments automatically.

### What it does

**Dashboard**
- **Coming up:** what's due today (or tomorrow), then the next payment.
- **Safe to spend:** a calculator, not a running total. You type today's balance; it sets aside every payment and your buffer until payday and shows what's left, dated "As of 7 Nov". Older results are dimmed with a box to check again.
- **Needs attention:** one row listing anything that needs a decision (findings to check, payments missing a date).
- **Where your money goes:** this calendar month's real cost by category. A weekly payment counts 4 or 5 times depending on the month.

**Payments**
- Every recurring payment, with this month's real cost and the yearly total.
- **Paid** tab: the last 3 months, confirmed (✓) when a Gmail receipt arrived, or expected (○) when none was seen. Late fees listed.
- Pricing: regular, free trial, or intro price ("A$2.99 a month for 3 months, then A$32.99").
- Variable bills (electricity, water) update their own estimate from each new bill (average of the last 3).
- Shared bills (½, ⅓, or an exact share) and late fees recorded as one-off extras.

**Gmail (Inbox)**
- Read-only. The first scan covers 3 months; then a daily scan at 6am reads only new email.
- Plain rules find clear recurring payments for free; only unclear senders reach the AI (Claude Haiku).
- "Is this your Anytime Fitness payment?" matching, remembered per sender and business. Billing platforms like Debitsuccess are never decided by sender alone.
- Nothing changes without approval, except variable bills updating their estimate (shown in What changed).

**Assistant**
- Answers questions about your payments using backend tools only (safe to spend, can I afford it, upcoming charges and more). It never calculates amounts itself and gives no financial product advice.

### What it doesn't do (yet)
- See your bank. The balance is typed in, and everyday spending isn't tracked.
- Answer "where did my pay go?" for a whole pay cycle.
- Let real users connect Gmail. Google verification is still to do, so only listed test users can connect.

### Stack
Next.js 16 frontend (Vercel), FastAPI + PostgreSQL backend (Render free plan, Neon), Supabase auth, Claude Haiku for Gmail analysis and the assistant, GitHub Actions for CI, evals and the daily scan.

---

# Part 2: Vision and problem

## The problem

Real example from the owner (October 2026): a $1,422 pay landed. Over the month it was spent, moved between accounts (everyday, savings) and partly used for trip planning. By the end of the month there was no way to tell where it went or what was left. Answering that took a long ChatGPT session, plus planning in Notion.

Why the existing tools fail:

- **Manual logging dies.** People won't record every transaction.
- **Bank trackers (for example CommBank) can't see past middlemen.** An electricity bill paid through Afterpay shows up only as "Afterpay". The real purpose is lost.
- **Moving money between your own accounts looks like spending,** or gets counted twice.
- **Everything is organised by transaction and calendar month.** People think "where did this pay go?"
- **A bank app shows a balance; a subscription tracker shows commitments.** Neither answers "how much can I safely spend until payday?"

## The vision

Subtrack should act like a **personal financial assistant (bookkeeper), not an app.** A human assistant beats any number of apps because they:

1. answer questions in your own words
2. chase missing info and remember the answer
3. remember context (goals, what the odd payments were for)
4. speak up before problems happen
5. show their working and say "I don't know yet" instead of guessing

**Goal for the owner:** it's genuinely useful to the owner first, so they can honestly promote it ("this worked for me").

## The advice boundary

Everyday money help, not financial product advice. There is no AFSL.

It can:
- Report what happened, what's committed and what's left.
- Answer questions about the user's own spending.
- Suggest where to cut back, based on that spending.
- Suggest cheaper everyday alternatives (streaming, gyms, phone plans, groceries).
- Share general budgeting tips.

It can't:
- Recommend or compare financial products: investments, shares, crypto, super, insurance, loans, credit cards or BNPL services.
- Tell the user to buy, sell, switch or hold any of those products.
- Give tax or debt-restructuring advice specific to the user.

If asked, it says plainly that this is outside what it can help with, then offers the relevant facts from the user's own data. Check the wording against ASIC guidance before public launch.

## Design rules

- **Numbers come only from the backend.** The AI never calculates or invents amounts. Every figure comes from a backend tool, with its source (statement, date, email receipt). Same principle as recurrence and FX in `CLAUDE.md`.
- **Honest about gaps.** If data is missing, say which data and ask for it.
- **Results are dated.** A number based on a typed-in balance says when it was true.
- **Memory the user can see and edit.** Matching rules and links are stored as data and can be corrected.
- **Proactive but rare.** A payday check-in and a few high-value alerts. No noise.
- **Suggestions are labelled as suggestions.** Prices of alternatives are looked up and sourced, or left out.

## The bigger idea: "Where did my pay go?"

The long-term feature, if statement import is built:

- **Input, no daily logging:** a CommBank CSV dropped in once per pay cycle (under a minute), plus Gmail receipts for middlemen (Afterpay, PayPal, BPAY), bills and subscriptions. No bank feed or CDR for now.
- **Engine:** find pay cycles; pair transfers between the user's own accounts (moved, not spent); match Afterpay/PayPal charges to the receipts that explain them; group the rest; ask about unknowns and save the answers as rules.
- **Output, one screen per pay cycle:**
  > Pay $1,422 (3 Oct) → Bills $380 · Spending $410 · Moved to savings $400 (still yours) · **Left: $232** · Trip fund: $650 of $1,200

  Gaps are stated openly ("Missing savings statement after 15 Oct, so 'Left' may be off").

**Acceptance test:** rebuild the owner's real October 2026 pay cycle from their CommBank statements and Gmail, with the same answer as the manual ChatGPT and Notion session, sources shown.

## Risks

- **Trust.** One wrong or made-up number breaks it, hence backend-only numbers with sources.
- **Privacy.** Gmail and statements are sensitive; people may refuse to connect them or let AI see them.
- **Friction.** Anything that takes more than about a minute per cycle gets abandoned, like manual logging.
- **Bank formats vary** (if import is built). Limit to CommBank first.
- **Afterpay instalment matching is fiddly.**

---

# Part 3: Build plan

## Phases

| # | Phase | Status | Done when |
|---|---|---|---|
| 1 | Money engine: safe to spend and can I afford it | ✅ Done | Tests cover shortfalls, stale balances, missing FX and bills due on payday |
| 2 | Home screen | ✅ Done (redesigned 7 Nov) | The owner uses it for real spending decisions |
| 3 | Automatic Gmail scanning | ✅ Done (live 7 Nov) | Findings reach Inbox without a prompt, and failed runs lose no emails |
| B | Variable bills | ✅ Done | A new bill updates the estimate without a review item |
| C | Paid history | ✅ Done | Past payments shown as confirmed or expected |
| 4 | Assistant tools | ⬜ Planned last | The assistant answers from paid history, this month's cost and late fees |
| 5 | Evals and guardrails | ⬜ Planned last | Evals cover the new tools and the advice boundary, and regressions fail CI |
| 6 | CommBank import | ❓ Optional | A statement updates balance and pay in under a minute |
| 7 | "Where did my pay go?" | ❓ Optional, needs 6 | It reproduces the real October answer |
| 8 | Middlemen and rules | ❓ Optional | The owner's real cycle needs fewer questions each time |
| 9 | Plans and goals | ❓ Optional | "I'll spend $60 Friday" updates the number |
| 10 | Alerts and MCP | ❓ Optional | Alerts fire correctly; an MCP client gets the same numbers |
| 11 | Launch and proof | ⬜ To do | ~20 students using it, usage numbers, README with diagram and decisions |

**Open decision (7 Nov 2026):** typing one balance is easier than importing a CSV, so phases 6–7 only make sense if "where did my pay go?" is worth the extra step. Without them, the remaining work is phase 11, then 4–5, then Google verification (about 7–10 hours).

**Launch blocker:** the Google OAuth app is in Testing, so Gmail access expires after 7 days and only listed test users can connect. Gmail read access needs Google's restricted-scope verification (CASA), which can take 4–8+ weeks. Start it well before phase 11.

## Progress log

- **31 Oct 2026:** safety guards (migrations, test database), ledger data model (`0015`), phase 1 money engine (`0016`), phase 2 home screen.
- **6–7 Nov 2026:** dashboard and sign-in redesign; calendar-month costs; payday-bills setting (`0018`); intro prices (`0019`); automatic Gmail scanning with a daily GitHub Actions run (`0020`); rules before AI; late fees and remembered sender links (`0021`); variable bills (`0022`); paid history; Safe to spend as a dated calculator.

Local dev should use a Neon dev branch, not prod.

## Rules for Gmail scanning

- **First connect** scans about 3 months back. **Later scans** run daily and read only email since the last complete scan; that point moves forward only on success.
- **Rules first.** Clear repeat charges from single-product senders are decided by code. Unclear senders, trials, cancellations and billing platforms go to the AI.
- **No silent money changes,** except variable bills updating their estimate, which is shown in What changed.
- **Receipts kept for paid history** store sender, business name, amount and date only, never email text.
- **Consent.** Automatic scanning is stated at connect time and on the privacy page, and users can turn it off.
- **Gmail push is optional, added later.** The daily scan stays as the safety net.

## Rules for bank data and AI (if phase 6 is built)

Statement import stays optional: a typed balance and tracked payments still give the number.

- **Code parses statements.** Import never sends the file to an AI.
- **Keep the minimum.** Discard the file and store only date, amount and description. Never ask for bank logins or full account numbers.
- **Minimum data to the AI.** The assistant gets totals, not transaction history; when it needs specific lines, names and reference numbers are removed.
- **Separate AI consent.** Importing doesn't allow AI access to bank data.
- **Easy deletion.** "Delete this import", "delete all bank data" and account deletion.
- **Prove it.** Evals check what is actually sent to the model. Real statements never go in the repo or test fixtures.

## How it fits the existing system

- Recurrence (`app/services/recurrence.py`) is the authority for every due date, month total and "committed" amount.
- Gmail ingestion and review (`app/routers/gmail.py`, `detected.py`, `app/gmail/rules.py`) feed payments, receipts and links.
- The agent (`app/routers/agent.py`) with confirmations and actions is the assistant interface.
- Multi-currency stays as is: amounts stored in their own currency, conversion done by the backend.
