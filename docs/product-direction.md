# Subtrack Product Direction: Pay-Cycle Money Assistant

Status: in progress, paused after Phase 1 (30 Oct 2026). Read this before starting any work on this direction.

## 1. The problem

Real example from the owner (October 2026): a $1,422 pay landed. Over the month it was spent, moved between accounts (everyday, savings) and partly used for trip planning. By the end of the month there was no way to tell where it went or what was left. Answering that took a long ChatGPT session, plus planning in Notion.

Why the existing tools fail:

- **Manual logging dies.** People won't record every transaction.
- **Bank trackers (for example CommBank) can't see past middlemen.** An electricity bill paid through Afterpay shows up only as "Afterpay". The real purpose is lost.
- **Moving money between your own accounts looks like spending,** or gets counted twice.
- **Everything is organised by transaction and calendar month.** People think "where did this pay go?"
- **Subtrack today only covers subscriptions.** Those rarely change, so there's little reason to open it.

## 2. The vision

Subtrack should act like a **personal financial assistant (bookkeeper), not an app.** A human assistant beats any number of apps because they:

1. answer questions in your own words
2. chase missing info and remember the answer
3. remember context (goals, what the odd payments were for)
4. speak up before problems happen
5. show their working and say "I don't know yet" instead of guessing

Subtrack has more data than a human assistant could hold (statements and Gmail) and can already talk with tool calling. The job is to put those pieces together properly.

**Boundary: everyday money help, not financial product advice.** There is no AFSL, but the assistant should still be useful in the way ChatGPT is for basic money questions.

It can:
- Report what happened, what's committed and what's left.
- Answer questions about the user's own spending ("which category did I spend the most on?").
- Suggest where to cut back, based on that spending ("eating out is your biggest flexible cost this cycle").
- Suggest cheaper everyday alternatives for ordinary goods and services, such as streaming, gyms, phone plans or groceries.
- Share general budgeting tips.

It can't:
- Recommend or compare financial products: investments, shares, crypto, super, insurance, loans, credit cards or BNPL services.
- Tell the user to buy, sell, switch or hold any of those products.
- Give tax or debt-restructuring advice specific to the user.

If asked, it says plainly that this is outside what it can help with, then offers the relevant facts from the user's own data. The exact wording of this boundary should be checked against ASIC guidance before public launch.

**Goal for the owner:** it's genuinely useful to the owner first, so they can honestly promote it ("this worked for me").

## 3. The core feature: "Where did my pay go?"

### Input (no daily logging)
- **Statement import** for each account, as CSV and/or PDF. The user drops them in once per pay cycle, and it should take under a minute. Start with **CommBank** formats only, then add more banks.
- **Gmail**, which is already integrated. It supplies receipts for middlemen (Afterpay, PayPal, BPAY, and so on), bills and subscriptions.
- No bank feed or CDR integration for now. Email plus statements is the chosen route.

### Engine
1. **Find pay cycles.** Detect pay deposits. A cycle runs from one pay to the next.
2. **Match own-account transfers.** Pair outgoing and incoming transfers across the user's own accounts. They are *moved*, not *spent*.
3. **Resolve middlemen.** Match Afterpay/PayPal charges to the Gmail receipt that explains them (for example Afterpay → Origin Energy $142). Afterpay instalments split one purchase into 4 charges and must be handled.
4. **Group the rest:** bills, subscriptions (from existing tracking), everyday spending, one-offs.
5. **Unknowns go to the user** as questions. The answers are saved as **rules** (for example "J Smith = rent share"), so each cycle needs fewer questions.

### Output: one plain screen for each pay cycle
> Pay $1,422 (3 Oct) → Bills $380 · Spending $410 · Moved to savings $400 (still yours) · **Left: $232** · Trip fund: $650 of $1,200

It also shows:
- **Committed before next pay:** subscriptions, bills and Afterpay instalments due. The existing recurrence engine supplies this.
- **Goals / pots:** for example a trip fund, with progress.
- **Gaps stated openly,** for example "Missing savings statement after 15 Oct, so 'Left' may be off."

## 4. Assistant-first design rules

- **The assistant is the main way in.** The dashboard is something the assistant shows, not the only interface.
- **Numbers come only from tools.** The LLM never calculates or invents amounts. Every figure comes from a backend tool using the backend's own calculations, and the answer cites its sources (statement, date, email receipt). This is the same principle already used for recurrence and FX in `CLAUDE.md`.
- **Honest about gaps.** If data is missing, say which data and ask for it.
- **Memory the user can see and edit.** Matching rules and labels are stored as data and can be viewed and corrected in the UI.
- **Proactive but rare.** A payday check-in ("new pay detected, here's last cycle, 2 things I couldn't match") plus a few high-value alerts. No noise.
- **Helpful within the boundary.** Cut-back suggestions, cheaper everyday alternatives, cancellation or refund-chase emails, reminders and calendar blocks are all fine. Financial product recommendations are not (see section 2).
- **Suggestions are labelled as suggestions.** Amounts in them still come from tools. Prices of alternatives are looked up and sourced, or left out, never recalled from memory.

### Agent tools to add or extend (indicative)
| Tool | Purpose |
|---|---|
| `import_statement` | Parse uploaded CSV/PDF into transactions for an account |
| `list_accounts` | User's accounts and their purpose (everyday, savings, ...) |
| `get_pay_cycles` / `explain_pay_cycle` | "Where did my pay go?" breakdown with sources |
| `match_transfers` | Detect own-account transfers |
| `resolve_intermediary` | Link Afterpay/PayPal charges to Gmail receipts |
| `committed_before_next_pay` | Upcoming subscriptions, bills, instalments |
| `goal_progress` | Pots/goals such as a trip fund |
| `search_transactions` | Plain-language search ("Uber since September") |
| `ask_user` / `save_rule` | Resolve unknowns and remember the answer |

## 5. How this fits the existing system

What carries over:
- Subscriptions/recurrence (`app/services/recurrence.py`) become the "committed" part of each cycle.
- Gmail ingestion and review findings (`app/routers/gmail.py`, `detected.py`) are the base for matching receipts to middlemen.
- The agent (`app/routers/agent.py`), conversations, confirmations and actions become the assistant interface.
- Multi-currency handling stays as is. Transactions are stored in their original currency, and the backend does the conversion.

New work:
- Data model: accounts, transactions, pay cycles, transfer links, intermediary links, rules, goals.
- Parsers for statement imports (CommBank CSV first, then PDF).
- Engines for transfer and intermediary matching.
- Pay-cycle view and payday check-in.
- New agent tools (table above).

## 6. Suggested build order

1. **Accounts and transactions data model,** plus Alembic migration. Remember that local dev points at the prod Neon DB, so be careful with migrations.
2. **CommBank CSV import.**
3. **Pay-cycle detection and own-account transfer matching.**
4. **Pay-cycle view (MVP screen).**
5. **Afterpay/PayPal ↔ Gmail receipt matching,** including instalments.
6. **Agent tools,** plus the unknowns → questions → saved rules loop.
7. **Goals/pots and "committed before next pay".**
8. **Payday check-in and alerts.**

### Progress (30 Oct 2026)

Done:
- **Safety and boundary:** migrations refuse remote databases outside production unless the host is in `MIGRATION_ALLOWED_HOST`. Tests are forced onto SQLite. The assistant's advice boundary matches section 2.
- **Step 1, data model:** seven ledger tables and migration `0015_pay_cycle_ledger`, included in account export and deletion.

Next: **step 2, CommBank CSV import.** Check the parser against the column layout of a real export. Real statements never go in the repo or test fixtures.

Local dev should use a Neon dev branch, not prod.

## 7. Acceptance test

Rebuild the owner's **real October 2026 pay cycle** from their CommBank statements and Gmail. Subtrack must give the same "where it went / what's left" answer the manual ChatGPT and Notion session produced, with sources shown and without opening Notion. Once that works, the owner can recommend it.

## 8. Risks

- Bank export formats vary. Limit scope to CommBank first.
- Afterpay instalment matching is fiddly.
- Statement drop-in friction. If it takes more than about a minute per cycle, users will drop off like they do with logging.
- Trust. One wrong or made-up number breaks it. Hence the tools-only rule for numbers, with sources cited.
- Privacy. Statements are sensitive: keep them scoped to the user, store as little as possible, and allow deletion.
