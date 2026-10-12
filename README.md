# Subtrack

[![Live demo](https://img.shields.io/badge/Live_demo-Explore-0A84FF?style=for-the-badge&logo=vercel&logoColor=white&labelColor=0060DF)](https://subtrack.twij.app/login)

![Next.js](https://img.shields.io/badge/Next.js-20232A?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-20232A?logo=typescript&logoColor=3178C6)
![FastAPI](https://img.shields.io/badge/FastAPI-20232A?logo=fastapi&logoColor=009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-20232A?logo=postgresql&logoColor=4169E1)
![Claude API](https://img.shields.io/badge/Claude_API-20232A?logo=anthropic&logoColor=D97757)
[![MIT License](https://img.shields.io/badge/License-MIT-20232A?labelColor=555)](LICENSE)

A full-stack portfolio project exploring recurring-payment tracking, Gmail receipt analysis and an AI assistant with approval-based actions.

Built by Thenuja Wijesuriya with Next.js, TypeScript, FastAPI and PostgreSQL. Subtrack is a personal engineering project with no active user base; the hosted version is a demonstration of the implementation, rather than a production service.

**[Explore the live demo](https://subtrack.twij.app/login)** — use the demo option to explore sample data without signing up. Demo sessions expire after 24 hours.

## Overview

Subscriptions, bills and free trials can be difficult to keep track of across different billing cycles and currencies. Subtrack explores how receipt extraction and an AI assistant can help organise that information in one place.

The repository includes the web app, API, database migrations and tests so you can inspect the implementation, run it locally or build on it.

## Implemented features

- **Recurring-payment management:** add and review subscriptions, bills and trials, with flexible billing cycles and currency preferences.
- **Gmail receipt analysis:** connect a test mailbox with read-only OAuth access, scan receipts and review detected payments before adding them.
- **Dashboard and insights:** monthly spending, upcoming charges, price changes, duplicate detection and trial tracking.
- **Reminders:** configure reminders for renewals and trial end dates.
- **AI assistant:** ask about spending and upcoming payments, explore savings options and research alternatives with sources. Changes are proposed for confirmation before being applied.
- **Account controls:** authentication through Supabase, data export and account-data deletion.
- **Demo mode:** isolated sessions seeded with sample data for exploring the app.

Gmail integration requires your own Google OAuth configuration. AI receipt analysis and assistant features require an Anthropic API key. The demo provides a way to explore the interface without connecting a mailbox.

## Architecture

| Component | Technology | Role |
| --- | --- | --- |
| Web app | Next.js 16, React 19, TypeScript, Tailwind CSS | Dashboard, receipt review and assistant interface |
| API | FastAPI, Pydantic, SQLAlchemy | Payment management, Gmail scanning and agent actions |
| Database | PostgreSQL, Alembic | Application data and schema migrations |
| Authentication | Supabase Auth | Sign-in and access tokens verified by the API |
| AI | Anthropic Claude API | Receipt extraction and assistant workflows |
| Email integration | Gmail API, Google OAuth | Read-only receipt access |

The frontend sends authenticated requests to the FastAPI backend. The backend scopes data to the authenticated account and stores it in PostgreSQL. Gmail refresh tokens are encrypted with a Fernet key. Assistant mutations pass through a proposal-and-confirmation flow.

```text
subtrack/
├── subtrack-frontend/
│   ├── app/                 # Pages and authentication routes
│   ├── components/          # UI, dashboard widgets and assistant panel
│   └── lib/                 # API client and frontend helpers
├── subtrack-backend/
│   ├── app/
│   │   ├── routers/         # REST endpoints and demo sessions
│   │   ├── agent/           # Assistant tools and proposed actions
│   │   ├── gmail/           # Receipt scanning and extraction
│   │   └── services/        # Recurrence, reminders and duplicate detection
│   ├── alembic/             # Database migrations
│   ├── scripts/             # Database bootstrap and Gmail scan utilities
│   └── tests/
├── .github/workflows/ci.yml
└── render.yaml              # Backend deployment configuration
```

## Local development

### Requirements

- Python 3.13 and Node.js 22 with npm (the versions used in CI).
- A PostgreSQL database, either local or hosted.
- A Supabase project for authentication.
- An Anthropic API key for AI features.
- Google OAuth credentials if you want to test Gmail integration.

### 1. Clone the repository

```bash
git clone https://github.com/thenuwij/subtrack.git
cd subtrack
```

### 2. Configure the backend

```bash
cd subtrack-backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
```

Edit `.env` with your own configuration:

| Variable | Configuration |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string. For a local database, use `postgresql://USER:PASSWORD@localhost:5432/subtrack`; create the database first. Hosted databases may require `sslmode=require`. |
| `SUPABASE_URL` | URL of your Supabase project, matching the frontend configuration. |
| `SUPABASE_JWT_SECRET` | Legacy HS256 JWT secret if your project uses it. This setting is required by the configuration model; for an ES256-only project, supply a non-empty local placeholder, since token verification uses the project's JWKS. |
| `ANTHROPIC_API_KEY` | Your Anthropic API key for receipt analysis and the assistant. |
| `ENVIRONMENT` | Keep `development` for local use. |
| `ALLOWED_ORIGINS` | `http://localhost:3000` |
| `FRONTEND_URL` | `http://localhost:3000` |

For Gmail integration, set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI`. Register `http://127.0.0.1:8000/gmail/callback` as an authorised redirect URI for your Google OAuth web client, enable the Gmail API, configure the `gmail.readonly` scope and add your account as a test user while the OAuth app is in testing mode.

Generate a token-encryption key and save the output as `TOKEN_ENCRYPTION_KEY` in `.env`:

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep this key stable so previously stored Gmail tokens remain readable. Keep private credentials in `.env`; never put them in frontend variables or commit them.

Bootstrap the database and apply migrations, then start the API:

```bash
python scripts/migrate.py
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

The bootstrap script creates the baseline tables before applying Alembic migrations, including when starting with an empty database. Interactive API documentation is available at [localhost:8000/docs](http://127.0.0.1:8000/docs).

### 3. Configure the frontend

In a second terminal, from the repository root:

```bash
cd subtrack-frontend
npm ci
cp .env.example .env.local
```

Set these values in `.env.local`:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-publishable-anon-key
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SUPPORT_EMAIL=your-email@example.com
```

Use your Supabase project's public anon/publishable key. Configure Supabase Auth's Site URL as `http://localhost:3000` and allow `http://localhost:3000/auth/callback` as a redirect URL. Email/password sign-in can be used locally; Google sign-in additionally requires enabling and configuring the Google provider in Supabase.

```bash
npm run dev
```

Open [localhost:3000](http://localhost:3000). Choose demo mode to explore sample data, or create an account through the configured Supabase project to test your own payments and Gmail connection.

## Development checks

Backend, from `subtrack-backend/` with the virtual environment activated:

```bash
ruff check app tests
pytest -q
```

The backend suite uses test credentials and in-memory SQLite rather than your configured PostgreSQL database.

Frontend, from `subtrack-frontend/`:

```bash
npx tsc --noEmit
npm run lint
npm run build
```

GitHub Actions runs these checks on pushes and pull requests to `main`.

## Hosted demo

The demo frontend is hosted on Vercel and the backend on Render, with deployment configuration in `render.yaml`. The hosted app exists to showcase the project. Local setup requires your own database, authentication configuration and service credentials.

## Contributing

Issues and pull requests are welcome. To work on a change, fork the repository, follow the local setup above and run the relevant development checks before opening a pull request. Include a short description of the change and how you verified it.

## License

This project is licensed under the [MIT License](LICENSE). You can use, modify and distribute the code under its terms.
