# Plan four: payday copilot

Builds [product-design.md](product-design.md). Replaces plans two and three. Each phase is one or a few small PRs.

## What we start from

- **Money engine:** `services/safe_to_spend.py` (safe to spend, can I afford it) and `SafeToSpendProfile` (balance, pay schedule, buffer).
- **Bills:** recurring payments, paid history, trials, ways to save, recurrence service.
- **Email:** Resend reminder pipeline with an hourly protected cron (`services/email_reminders.py`).
- **Assistant:** approval-only actions, transaction parsing (`services/transaction_parse.py`), voice entry.
- **Goals, budgets, transactions, workspace:** built, behind `enabled_features`.

## Phase 1: One default experience

1. Remove the feature picker from onboarding. New users get Home, Bills, Ask, Account.
2. Goals, budgets, transactions and workspace default to off and are hidden from navigation. No code or data is deleted.
3. Home leads with free to spend, then bills before payday, then needs attention.

**Done when** a new account sees only the four screens and existing data still loads.

✅ Done 10 Nov 2026. Parked features are opt-in under Account → Extras.

## Phase 2: Estimate without a balance

1. Add optional `pay_amount` to `SafeToSpendProfile` (migration).
2. With no fresh balance, safe to spend = pay amount − bills before next payday − goal set-aside − buffer, labelled "Estimate: add today's balance for an exact number".
3. Tests: no balance, stale balance, bills due on payday, missing FX.

**Done when** a user with no balance gets a labelled estimate.

✅ Done 10 Nov 2026 (`0032_pay_amount`). Balance is now optional. An estimate also replaces a balance older than the last payday, and its per-day figure spreads over the whole pay cycle because spending so far is unknown.

## Phase 3: Three-minute setup

1. Steps: pay schedule and amount → bills → optional balance and goal → payday message → first number.
2. Bills step: a pick list of about 30 common Australian services with typical prices, plus one typed or spoken line parsed into bills for the user to confirm.
3. Record setup start and finish times (Phase 7).

**Done when** a fresh account reaches its first number in under 3 minutes.

## Phase 4: Payday message

1. Opt-in at setup and in Account. Uses the existing Resend pipeline, durable delivery keys and cron.
2. Sent on the morning of each payday in the user's time zone: pay in, bills before next pay, set aside, free per day.
3. One link opens a one-field "today's balance" page.
4. Tests: weekly and fortnightly schedules, time zones, opt-out, demo accounts never send.

**Done when** a test account gets exactly one correct message per payday.

## Phase 5: Goals and big spends feed the number

1. Each goal's per-pay target comes off free-to-spend as "set aside".
2. "Spent something big?" quick add (typed or voice) lowers free-to-spend until the next balance update.
3. Can I afford it accounts for both.

**Done when** adding a goal or a big spend changes the Home number with the reason shown.

## Phase 6: Quick check and rare alerts

1. Installable web app (PWA) with a "Can I afford it?" shortcut opening a one-field page.
2. Alerts, by email, only for: a bill that won't fit before payday, a trial ending in 3 days, a recorded price rise.
3. No more than 2 alerts per pay cycle.

**Done when** each alert fires once in its test case and never otherwise.

## Phase 7: Measure

1. Anonymous event counts (no amounts, names or payment details): setup started, setup finished, first number seen, payday message opened, balance updated, afford check.
2. A script like `scripts/ai_usage_report.py` prints activation and per-cycle retention.

**Done when** the report shows real numbers from test accounts.

## Phase 8: Pilot

1. Update the README, landing page and privacy page to the new promise.
2. Invite 20 students or shift workers. The owner uses it for their own pay cycles too.
3. Run for 2 pay cycles. Interview 5 users.
4. **Gate:** 10 or more still active after 2 cycles → plan email forwarding or statement upload. Fewer → revisit the wedge.

## Order

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8. Phase 7 can run alongside 4–6.

## Not in this plan

Email forwarding, statement upload, shared bills, workspace, budgets, paid features.
