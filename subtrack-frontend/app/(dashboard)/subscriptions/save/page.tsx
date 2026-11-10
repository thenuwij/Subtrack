"use client";
import Link from "next/link";
import { getDuplicates, getWaysToSave } from "@/lib/api";
import { useApi, errorMessage } from "@/lib/hooks/useApi";
import { formatCurrency } from "@/lib/utils/currency";
import { formatStoredDate } from "@/lib/utils/dates";
import { PaymentsTabs } from "@/components/subscriptions/PaymentsTabs";
import { Button } from "@/components/ui/button";

export default function SavingsPage() {
  const query = useApi("ways-to-save", getWaysToSave);
  const duplicateQuery = useApi("duplicates", getDuplicates);
  const data = query.data ? { ...query.data, duplicates: {
    temporarily_unavailable: Boolean(duplicateQuery.error),
    suggestions: (duplicateQuery.data ?? []).map(pair => ({keep: pair.keep, possible_duplicate: pair.merge})),
  }} : undefined;
  const money = (amount: number) =>
    formatCurrency(amount, data?.base_currency ?? "AUD");
  return (
    <div className="page-shell space-y-6">
      <PaymentsTabs />
      <header>
        <p className="eyebrow mb-2">Small changes add up</p>
        <h1 className="page-heading">Ways to save</h1>
        <p className="page-description">
          A few things worth a look. You decide what&apos;s right for you.
        </p>
      </header>
      {query.error ? (
        <section className="rounded-2xl bg-card p-6">
          <p>{errorMessage(query.error, "Could not load savings insights.")}</p>
          <Button
            className="mt-3"
            variant="outline"
            onClick={() => void query.mutate()}
          >
            Try again
          </Button>
        </section>
      ) : null}
      {!data ? (
        !query.error && (
          <div
            role="status"
            className="h-64 animate-pulse rounded-3xl bg-muted"
          >
            <span className="sr-only">Loading ways to save</span>
          </div>
        )
      ) : (
        <>
          <section className="money-hero">
            <h2 className="text-sm font-medium">Your recurring commitments</h2>
            <p className="mt-3 text-4xl font-semibold tracking-tight tabular-nums">
              {data.income_share === null
                ? money(data.monthly_total)
                : `${data.income_share}%`}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {data.income_share === null
                  ? "monthly average"
                  : "of your income"}
              </span>
            </p>
            <p className="mt-3 text-sm text-muted-foreground">
              {money(data.monthly_total)} monthly average across tracked
              payments. Actual calendar-month costs vary.
            </p>
            {data.unconverted_count > 0 ? (
              <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                {data.unconverted_count} payments excluded because exchange
                rates are unavailable.
              </p>
            ) : null}
            <Link
              href="/account#income"
              className="mt-4 inline-block text-sm text-primary"
            >
              {data.income_share === null
                ? "Add your income"
                : "Update your income"}
            </Link>
          </section>
          <section className="rounded-2xl bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Price rises</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Recorded changes over the last 90 days, shown as monthly
              equivalents.
            </p>
            {data.price_rises.length ? (
              <ul className="mt-4 divide-y divide-border">
                {data.price_rises.map((row) => (
                  <li
                    key={row.id}
                    className="flex flex-wrap justify-between gap-2 py-3 text-sm"
                  >
                    <span>{row.name}</span>
                    <span className="tabular-nums">
                      {formatCurrency(
                        row.old_monthly_native,
                        row.native_currency,
                      )}{" "}
                      →{" "}
                      {formatCurrency(
                        row.new_monthly_native,
                        row.native_currency,
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-muted-foreground">
                No recorded price rises in this period.
              </p>
            )}
          </section>
          <section className="rounded-2xl bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Possible duplicates</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Duplicate records can inflate your totals. They don&apos;t prove
              you were charged twice.
            </p>
            {duplicateQuery.isLoading ? <p className="mt-4 text-sm text-muted-foreground">Checking for duplicates…</p> : data.duplicates.temporarily_unavailable ? (
              <p className="mt-4 text-sm">
                Duplicate checking is temporarily unavailable.{" "}
                <button
                  className="text-primary"
                  onClick={() => void duplicateQuery.mutate()}
                >
                  Try again
                </button>
              </p>
            ) : data.duplicates.suggestions.length ? (
              <ul className="mt-4 space-y-3">
                {data.duplicates.suggestions.map((pair) => (
                  <li key={pair.possible_duplicate.id} className="text-sm">
                    {pair.keep.name} and {pair.possible_duplicate.name}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-muted-foreground">
                No possible duplicates found.
              </p>
            )}
            <Link
              href="/subscriptions"
              className="mt-4 inline-block text-sm text-primary"
            >
              Review tracked payments
            </Link>
          </section>
          <section className="rounded-2xl bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">
              Trials & introductory offers ending
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              In the next 30 days.
            </p>
            {data.trials.length ? (
              <ul className="mt-4 divide-y divide-border">
                {data.trials.map((trial) => (
                  <li key={trial.id} className="py-3 text-sm">
                    <p className="font-medium">{trial.name}</p>
                    <p className="mt-1 text-muted-foreground">
                      Ends {formatStoredDate(trial.trial_ends_at)} · then{" "}
                      {formatCurrency(trial.price_after_trial, trial.currency)}{" "}
                      per billing cycle
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-muted-foreground">
                No tracked offers ending in the next 30 days.
              </p>
            )}
            <Link
              href="/subscriptions"
              className="mt-4 inline-block text-sm text-primary"
            >
              Manage payments & reminders
            </Link>
          </section>
          <section className="rounded-2xl bg-card p-6 shadow-sm">
            <h2 className="text-lg font-semibold">Late fees</h2>
            <p className="mt-3 text-3xl font-semibold tabular-nums">
              {money(data.late_fees_total)}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Fees stated on bills or confirmed by you over the last 3 months.
              These are past costs, not guaranteed savings.
            </p>
            {data.above_plan_total > 0 ? (
              <p className="mt-3 text-sm">
                Another {money(data.above_plan_total)} above your plan needs
                checking.
              </p>
            ) : null}
            <Link
              href="/subscriptions/paid"
              className="mt-4 inline-block text-sm text-primary"
            >
              Review payment history
            </Link>
          </section>
        </>
      )}
    </div>
  );
}
