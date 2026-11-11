# Pocketday

Formerly Subtrack.

[![Live demo](https://img.shields.io/badge/Live_demo-Explore-0A84FF?style=for-the-badge&logo=vercel&logoColor=white&labelColor=0060DF)](https://pocketday.app/login)

![Next.js](https://img.shields.io/badge/Next.js-20232A?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-20232A?logo=typescript&logoColor=3178C6)
![FastAPI](https://img.shields.io/badge/FastAPI-20232A?logo=fastapi&logoColor=009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-20232A?logo=postgresql&logoColor=4169E1)
![Claude API](https://img.shields.io/badge/Claude_API-20232A?logo=anthropic&logoColor=D97757)
[![MIT License](https://img.shields.io/badge/License-MIT-20232A?labelColor=555)](LICENSE)

Pocketday shows where your pay goes and what's actually yours to spend until payday.

It's for people paid weekly or fortnightly who don't want to track every purchase. You enter your pay and bills once, Pocketday holds back what's already spoken for, and an AI assistant can answer questions and make changes for you. No bank login.

## Key Features

### Three-minute setup

Tell Pocketday when you're paid and what comes out regularly, and you see where your pay goes straight away.

- Pick your pay schedule (weekly, fortnightly or monthly), next payday and usual pay after tax.
- Tap common Australian bills, or type them in one line ("rent 400 weekly, phone 35 monthly").
- Optionally hold money back for groceries or a trip, and add today's balance.

### Bills

Every recurring payment in one place, with what it costs this month and over a year.

- Subscriptions, rent, utilities and shared bills where you pay only your share.
- Free trials, intro prices, variable bills, and paused or cancelling payments.
- Paid history: mark a payment paid, not paid yet, or didn't happen. Unpaid bills still count as owed.
- Reminders before a bill is due or a trial ends.

### Find bills in Gmail

Set up a Gmail filter that forwards your bills to a private Pocketday address and Pocketday suggests recurring bills you might be missing. It never reads the rest of your mailbox.

- Nothing is added until you approve it on the Review page.
- Raw emails are never stored, only the merchant, amount and dates.
- Pause, replace or delete your forwarding address at any time.

### Budgets and savings

Hold money back before you spend it, every payday.

- **Budget:** "Groceries, $150 a pay", with a bar showing what's left this pay.
- **Saving:** "Trip, $100 a pay".
- Your bills are already counted, so Pocketday warns you if a new budget looks like one of them.
- Logging a spend is optional. Take it from a budget or give it a category, and edit or undo it later.
- Past pay cycles show how each pay went, budget by budget.

### This pay

Home shows where your current pay goes, from payday to payday.

| You see | What it means |
| --- | --- |
| Your pay | Usual pay, plus any extra income you added this pay |
| Bills this pay | Every bill due before payday. Tap to list them |
| Budgets | Money held back for your budgets and savings |
| Spent | Spends outside a budget, or past one |
| Balance | What's left of this pay |

- **Breakdown** shows each category and budget as bars or a pie.
- **Extra income:** got an extra shift or a refund? Add it and it counts for this pay only.

### Check my balance and Can I afford it?

Two quick checks for the moments you need an exact answer.

| Check my balance | Can I afford it? |
| --- | --- |
| Enter today's balance to see what's free to spend and about how much a day | Type an amount and get a yes or no, with what you'd have left until payday |
| Shows afterwards as a dated "last checked" amount, since later spending isn't counted | Add Pocketday to your phone's home screen for a one-tap shortcut |

### Ways to save

One page of things worth a look before your next bill.

- Price rises, possible duplicate payments and late fees.
- Free trials and intro offers ending in the next 30 days.

### AI Assistant

Ask about your own money in plain words, and let the assistant make changes for you.

| Ask things like | Or have it do things like |
| --- | --- |
| "What's left until payday?" | "I spent $18 on Uber" |
| "Can I afford $120 on Friday?" | "Make my groceries budget $120" |
| "Where is this pay going?" | "I got $200 extra this week" |
| "Which subscriptions went up?" | "Add Netflix, $18.99 monthly" |
| "Are there cheaper phone plans?" | "Mark rent as paid" or "my payday is now Friday" |

- Every change waits for you to press Confirm, and is checked again before it's applied.
- It can manage bills, budgets, spends, extra income, pay details, reminders and Gmail suggestions.
- It can search the web for cheaper alternatives to a bill.
- It doesn't give investment or financial product advice.

### Payday email and alerts

On payday morning, an email shows the bills before your next pay, what's set aside and what's free.

- Turn it on during setup or in Account.
- At most two alerts a pay cycle: if bills won't fit, or a free trial is about to end.
- Export or delete all your data from Account at any time.

## Built With

Next.js, TypeScript, FastAPI, PostgreSQL and the Claude API. Try the [live demo](https://pocketday.app/login).

## Project Structure

```text
subtrack/
├── subtrack-frontend/     # The web app
│   ├── app/               # Pages, including setup, Home, Bills and Can I afford it
│   └── components/        # Screens and cards
├── subtrack-backend/      # The API
│   ├── app/               # Money engine, bills, emails and the assistant
│   ├── alembic/           # Database changes
│   └── tests/             # Automated tests
└── docs/                  # Product design, build plans and local setup
```

To run it on your own machine, see [docs/local-setup.md](docs/local-setup.md).

## License

This project is licensed under the [MIT License](LICENSE). You can use, modify and distribute the code under its terms.
