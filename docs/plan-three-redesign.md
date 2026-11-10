# Plan three: one money history

Every dollar appears once, in **Transactions**. Payments are scheduled bills that write a Transactions entry when charged. Other pages are views or setup.

## Navigation (one page per feature tick)

| Section | Shown when ticked | Contains |
|---|---|---|
| Home | always | summary cards for ticked features |
| Transactions | Expenses & income | money in/out history (In/Out filter) + this month by category |
| Recurring payments | Payments | tabs: Upcoming · Paid · Inbox (badge) · Save |
| Goals | Goals & budgets | goals and budgets |
| Workspace | Workspace | custom pages |

Assistant is a floating "Ask" button. Account stays as the avatar.

## Rules

- Log money in one place: "+ Add" on Transactions (type or 🎤 speak; the form prefills, the user confirms).
- Set things up on their own page: Add payment, Set budget, New goal, New page.

## Build steps

1. **Navigation and pages** (UI only): five-section nav, Spending becomes Transactions, Recurring payments tabs, floating Ask.
2. **Recurring payments write to Transactions** (backend, money): a charged payment creates one linked transaction; Spending/budget totals read only transactions; backfill existing paid history.
3. **"+ Add" with voice on Transactions**: one In/Out form, browser speech → assistant parse → prefilled form to confirm; mic hidden where unsupported.
