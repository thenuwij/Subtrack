# Run Subtrack locally


## Requirements

- Python 3.13 and Node.js 22 with npm (the versions used in CI).
- A PostgreSQL database, either local or hosted.
- A Supabase project for authentication.
- An Anthropic API key for AI features.
- Google OAuth credentials if you want to test Gmail integration.

## 1. Clone the repository

```bash
git clone https://github.com/thenuwij/subtrack.git
cd subtrack
```

## 2. Configure the backend

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

## 3. Configure the frontend

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

