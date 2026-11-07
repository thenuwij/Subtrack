# Payment history, Ways to save and reminder emails

Manual decisions apply to one scheduled occurrence or one bill. They do not change the recurring schedule, invent a Gmail receipt, or cancel a merchant service. A later matching receipt takes precedence over a manual answer without adding a second occurrence. Undo removes only the user's answer. Skipped payments are excluded from the history subtotal. Bills can be confirmed paid another way; invoice debt cannot be dismissed as a skipped subscription.

Ways to save lives under Payments. It shows recorded price rises over 90 days, possible duplicate records, offers ending within 30 days, confirmed late fees over three months and recurring costs as a share of income. Income share uses normalized monthly equivalents, not a calendar-month total. It does not add the signals together or promise savings. Duplicate records do not establish duplicate bank charges. Missing FX and unavailable duplicate checks stay visible.

## Enabling email delivery

1. Run `python scripts/migrate.py` before deploying the API (schema head `0026_email_reminders`).
2. Verify a sending domain in Resend and configure `RESEND_API_KEY` and `REMINDER_EMAIL_FROM` on the API. Keep `FRONTEND_URL` pointed at the public website.
3. Configure repository secrets `SUBTRACK_API_URL` and `CRON_SECRET`, matching the API's `CRON_SECRET`. The hourly Email reminders workflow calls the protected scheduled-send endpoint. It fails when delivery is unconfigured, failed or expired so failures are visible in Actions.
4. Users explicitly enable email reminders in Account. The destination comes from the authenticated account's signed email claim, never a browser-supplied address. Demo sessions cannot enable delivery. Users create payment reminders through each payment's menu. Existing automatic trial reminders also qualify.
5. Test using a dedicated account and a controlled recipient before public release. Automated tests mock delivery and never send email.

Each reminder occurrence has a durable delivery key and a frozen payload, persisted before making the provider request. Resend replays requests with that idempotency key within 24 hours; retries stop after 23 hours to avoid duplicating an email after that protection expires. An expired uncertain delivery is reported for operator review, not automatically resent. A provider acceptance is recorded as sent; inbox delivery/bounces are not confirmed. Users can disable email in Account, dismiss a reminder, or delete it. No emails are sent for inactive or paused reminders, after their target time, or without explicit opt-in.

The hourly schedule may run late when GitHub Actions is delayed. Due reminders can catch up until their target time. The worker processes up to 500 enabled accounts and the existing reminder service's 200-reminder bound per account per invocation; revisit pagination before exceeding those limits. Email preference and delivery metadata participate in account export and deletion. Export omits the stored delivery payload, which duplicates the opted-in email's payment name and date. Production delivery requires provider credentials and a verified domain; the code does not provision those external resources.

Provider contract: https://resend.com/docs/dashboard/emails/idempotency-keys
