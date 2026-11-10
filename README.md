# Subtrack

[![Live demo](https://img.shields.io/badge/Live_demo-Explore-0A84FF?style=for-the-badge&logo=vercel&logoColor=white&labelColor=0060DF)](https://subtrack.twij.app/login)

![Next.js](https://img.shields.io/badge/Next.js-20232A?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-20232A?logo=typescript&logoColor=3178C6)
![FastAPI](https://img.shields.io/badge/FastAPI-20232A?logo=fastapi&logoColor=009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-20232A?logo=postgresql&logoColor=4169E1)
![Claude API](https://img.shields.io/badge/Claude_API-20232A?logo=anthropic&logoColor=D97757)
[![MIT License](https://img.shields.io/badge/License-MIT-20232A?labelColor=555)](LICENSE)

Subtrack tells you what's actually yours to spend until payday.

It's for people paid weekly or fortnightly who don't want to track every purchase. You enter your pay and your bills once, and Subtrack sets aside what's already spoken for. No bank login.

## Key Features

### Three-minute setup

Tell Subtrack when you're paid and what comes out regularly, and you see your first number straight away.

- Pick your pay schedule, next payday and usual pay after tax.
- Tap common Australian bills, or type them in one line ("rent 400 weekly, phone 35 monthly").
- Add today's balance if you like. It's optional.

### Safe to spend

One number on Home: what's free until your next payday, and about how much a day.

| Without a balance | With today's balance |
| --- | --- |
| Estimated from your usual pay, minus this pay cycle's bills and a small buffer | Exact, dated, and based on what's in your account today |

Tap "How this is worked out" to see every bill and amount behind the number.

### Bills

Every recurring payment in one place, with what it costs this month and over a year.

- Subscriptions, rent, utilities, trials and intro prices.
- Paid history for the last three months.
- An optional read-only Gmail scan suggests bills for you to approve.

### Set aside each pay

Hold money back before you spend it, every payday.

- **Saving:** "Trip, $100 a pay".
- **Spending pot:** "Eating out, $60 a pay", with what's left this cycle.
- Logging a spend is optional. A spend from a pot uses up the pot, not your free money.

### Payday email and alerts

On payday morning, an email shows the bills before your next pay, what's set aside and what's free.

- Turn it on during setup or in Account.
- At most two alerts a pay cycle: if bills won't fit, or a free trial is about to end.

### Can I afford it?

Type an amount and get a yes or no, with what you'd have left until payday.

- Add Subtrack to your phone's home screen for a one-tap shortcut.

### AI Assistant

Ask questions about your own bills and spending in plain words.

- Every change it suggests waits for your approval.
- It doesn't give investment or financial product advice.

## Built With

Next.js, TypeScript, FastAPI, PostgreSQL and the Claude API. Try the [live demo](https://subtrack.twij.app/login).

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
