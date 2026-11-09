# Plan one: email forwarding instead of Gmail OAuth

Goal: no Google OAuth scopes for users (no verification, no CASA audit, no warning screen). Users add a one-time Gmail filter that forwards only bill-like emails to a private address. Raw emails are never stored.

The existing pipeline after `ReceiptCandidate` stays the same: `analyze_bounded`, `_apply_detections`, `_save_bills`, `_save_receipts` and the Review page. Only how email gets in and onboarding change.

## Phase 1: Domain and inbound mail (setup only)
- Buy a domain (e.g. `subtrack.app`), move DNS to Cloudflare.
- Turn on Email Routing for `in.subtrack.app` with a catch-all to an Email Worker.
- Check: a test email shows up in the worker logs.

## Phase 2: Backend data model (Alembic migration)
- `inbound_addresses`: `user_id`, random `token`, confirmed `gmail_address`, `status`, `created_at`, `rotated_at`.
- `inbound_messages`: `message_hash` (dedupe), `received_at`, outcome (accepted / dropped by privacy filter / rejected). No subject, body or sender name.
- `GmailReceipt.gmail_message_id` becomes a general `source_message_id` (or holds the hash).

## Phase 3: Ingest endpoint
- `routers/inbound.py` with `POST /inbound/email`, HMAC-signed by the worker with a timestamp (no replays).
- `gmail/mime.py`: raw message → `ReceiptCandidate`, reusing body-text/excerpt helpers from `scanner.py`.
- In memory only: look up user by token → check ARC/DKIM and sender is the confirmed Gmail → deny list (OTP, password reset, security alerts, health) → candidate → existing analyze/detections/bills/receipts → drop raw message.
- Logs and errors show only token and hash.
- Tests: spoofed sender, OTP email dropped, duplicate, normal receipt.

## Phase 4: Email Worker (`subtrack-inbound/`, TypeScript)
- Receive, return 200, forward raw message to `/inbound/email` with signature.
- No storage. Retry once, then drop.
- Detect Gmail's forwarding confirmation email and post only the code to the backend.

## Phase 5: Onboarding UI (replace Gmail connect in `GettingStarted.tsx` and the account page)
1. Personal address with copy button.
2. Link to Gmail Forwarding settings; page shows the confirmation code live.
3. Download `subtrack-filter.xml`, plus search text to paste.
4. "Send test" step with a green tick.
- Account page: rotate address, pause, "what we received" (stored fields only), delete everything.

## Phase 6: Retire OAuth for users
- Config flag turns off `/gmail/connect` in production; keep testing mode for the owner only.
- Remove the daily scan job for users.
- Update `privacy/page.tsx` and `CLAUDE.md`.

## Phase 7: Production checks
- End-to-end test with a real Gmail account.
- Check stored rows contain no raw text.
- Public "How Subtrack reads your bills" page.

Each phase is its own small PR in this order; phases 3 and 4 can run side by side once phase 2 is merged.
