> **Superseded on 10 Nov 2026** by [plan four](plan-four-payday-copilot.md). Kept for reference.

# Plan two: four-feature redesign

Builds on [product-design.md](product-design.md). Covers build-order steps 1–4. Step 5 (email forwarding and domain) is [plan one](plan-one-email-forwarding.md).

## What we start from

- **Monthly payments** is built: recurring payments, review, duplicates, paid history, reminders, ways to save, safe to spend.
- **The assistant** already proposes typed actions (`app/agent/actions.py`) that run only after the user approves. All new AI features use this same flow.
- **Expenses, income, budgets and savings goals** existed before and were removed (`a0024eb`, `de59097`); their tables were dropped (`0014`). They come back as a fresh build in the new design. The old commits are reference only.

## Shared foundations (built first, used by everything)

- **One `transactions` table** for money in and out: `kind` (expense/income), amount, currency, base amount, date, category, note, `source` (ai/email/manual), optional `recurring_payment_id` (when it is a payment of a known bill).
- **One category list** shared by transactions, payments and budgets.
- **`enabled_features`** on user preferences: the four ticks from onboarding, editable in Settings. Navigation, the dashboard and agent tools respect it.
- **Duplicate check** extended from payments to transactions (same name, similar amount, close date → flagged for the user).

## Phase A: Feature picker and navigation

1. Onboarding step "What do you want Subtrack for?" with the four ticks.
2. Settings page section to change them.
3. Navigation shows only enabled features: Home, Spending, Payments, Goals & budgets, Workspace. The assistant is reachable from every page.
4. Home shows cards only for enabled features.

## Phase B: Expenses and income

1. Backend: `transactions` model, migration, CRUD router, totals by month and category (converted with the shared rate snapshot; missing FX stays unconverted).
2. Agent tools: log, edit, delete and list transactions as approval cards ("Logged $20 · Food · Undo").
3. Before logging, the agent checks payments and recent transactions for a match ("Is this your AGL bill from the 3rd?").
4. Spending page: this month's in/out, by category, a simple list with quick add and edit.

## Phase C: Goals and budgets

1. **Budgets:** a monthly limit per category; spent = transactions + payments in that category; amount left.
2. **Goals:** name, target amount, optional date, contributions logged by the user or the AI; progress and "per week/day needed" maths.
3. Agent tools for both, with approval.
4. Goals & budgets hub page: clear progress bars and what is left this month.

## Phase D: Custom workspace and guardrails

1. **Blocks** (fixed set): payment list, transaction log, budget, goal progress, upcoming payments, trend chart, checklist, shared costs, notes.
2. **Templates** built from blocks: monthly budget, savings goal, moving house, bill price check, cutting subscriptions, shared household bills, trip budget, debt payoff.
3. **Pages** store only a layout (template, blocks, filters such as category or date range). Blocks read live data, so pages stay up to date.
4. **Flow:** user describes the situation → agent proposes a page (template + blocks + filters) → preview → approve → saved in the workspace. Edits go through the same approval.
5. **Guardrail policy** written once and used in the agent prompt, tool checks and evals: maths on the user's own data is allowed; recommending investments, financial products or "what you should do" is refused with a short explanation.
6. Evals for the new tools and the guardrail.

## Phase E: UI and system audit

Run the app final audit across all four features and the workspace: every page and button, mobile, light/dark, plain language, empty states.

## Order and PRs

Foundations → A → B → C → D → E. Each phase is one or a few small PRs. B and C both need the foundations; D needs B and C so its blocks have data.
