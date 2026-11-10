/** Legacy compatibility value. New recurrence logic uses interval_unit/count. */
export type BillingCycle = 'weekly' | 'monthly' | 'yearly'
export type RecurrenceUnit = 'day' | 'week' | 'month' | 'year'
export type PaymentStatus = 'active' | 'paused' | 'cancelling' | 'cancelled' | 'ended'
export type AmountType = 'fixed' | 'variable'
export type SpendingType = 'unspecified' | 'essential' | 'optional'
/** Manual payments count as money out only once a due date is marked paid. */
export type PaymentMethod = 'automatic' | 'manual'

export type Category =
  | 'housing'
  | 'insurance'
  | 'phone_internet'
  | 'streaming'
  | 'software'
  | 'cloud'
  | 'utilities'
  | 'fitness'
  | 'food'
  | 'transport'
  | 'education'
  | 'childcare'
  | 'debt'
  | 'memberships'
  | 'donations'
  | 'business'
  | 'shopping'
  | 'health'
  | 'travel'
  | 'personal_care'
  | 'gifts'
  | 'income'
  | 'other'

export type Currency = 'AUD' | 'USD' | 'GBP' | 'SGD' | 'EUR' | 'JPY'

export interface Subscription {
  id: string
  user_id: string
  name: string
  category: Category
  amount: number                   // what YOU pay (your share of a split bill)
  full_amount: number | null       // the whole bill, when shared; null = you pay it all
  share_ratio: number              // amount = full_amount * share_ratio
  split_mode: 'full' | 'ratio' | 'fixed'  // fixed shares don't rescale when the bill changes
  currency: string
  exchange_rate: number | null       // null when no honest conversion snapshot exists
  converted_amount: number | null  // null for legacy entries
  cycle: BillingCycle               // compatibility field; never use for new calculations
  interval_unit: RecurrenceUnit
  interval_count: number
  cadence_label: string
  monthly_equivalent: number        // native currency; calculated by the backend
  yearly_equivalent: number         // native currency; calculated by the backend
  next_due: string | null
  next_expected_at: string | null   // projected by the backend from the saved anchor
  next_expected_source: 'recorded' | 'projected_from_recorded_cycle' | 'missing' | 'ended' | 'inactive' | 'paused_without_resume'
  recurrence_end_at: string | null
  trial_ends_at: string | null       // post-trial price is stored in `amount`
  intro_amount?: number | null       // discounted price charged until trial_ends_at
  status: PaymentStatus
  paused_until: string | null
  cancellation_effective_at: string | null
  amount_type: AmountType
  spending_type: SpendingType
  payment_method: PaymentMethod
  is_active: boolean
  created_at: string
}

/** A manual payment's due date, up to a week ahead, not yet marked paid. */
export interface ManualDue {
  payment_id: string
  name: string
  due_date: string
  amount: number
  currency: string
  overdue: boolean
}

// Payload shapes for create/update calls — mirror the backend Pydantic models.
export interface SubscriptionInput {
  name: string
  category: Category
  amount: number
  currency?: string
  exchange_rate?: number
  converted_amount?: number | null
  cycle?: BillingCycle
  interval_unit?: RecurrenceUnit
  interval_count?: number
  next_due?: string | null
  recurrence_end_at?: string | null
  trial_ends_at?: string | null
  intro_amount?: number | null
  status?: PaymentStatus
  paused_until?: string | null
  cancellation_effective_at?: string | null
  amount_type?: AmountType
  spending_type?: SpendingType
  payment_method?: PaymentMethod
  is_active?: boolean
  full_amount?: number | null
  share_ratio?: number
  share_amount?: number
}

export interface GmailStatus {
  connected: boolean
  configured?: boolean
  email_address?: string
  connected_at?: string | null
  last_scanned_at?: string | null
  scan_status?: 'idle' | 'running' | 'done' | 'error'
  scan_error?: string | null
  scan_stage?: 'queued' | 'reading' | 'analysing' | 'finalising' | 'complete' | null
  scan_processed?: number
  scan_total?: number
  scan_partial?: boolean
  scan_message?: string | null
  auto_scan_enabled?: boolean
  scan_cursor_at?: string | null
}

export interface DetectedSubscription {
  id: string
  merchant: string
  sender_domain: string
  category: Category
  cycle: BillingCycle | null
  interval_unit: RecurrenceUnit | null
  interval_count: number | null
  cadence_label: string | null
  cadence_confidence: 'high' | 'medium' | 'unknown'
  cadence_evidence: string | null
  amount_type: AmountType
  amount: number
  currency: string
  previous_amount: number | null
  cancelled: boolean
  confidence: 'high' | 'medium'
  charge_count: number
  trial_ends_at: string | null
  intro_amount?: number | null
  next_due: string | null
  due_date_confidence: 'high' | 'medium' | 'unknown'
  due_date_evidence: string | null
  existing_subscription_id: string | null
  product_key: string
  current_amount: number | null                       // what you pay today, if tracked
  current_currency: string | null
  current_full_amount: number | null
  current_share_ratio: number | null
  current_split_mode: 'full' | 'ratio' | 'fixed' | null
  current_name: string | null                         // name of the subscription it will update
  current_cycle: string | null
  current_interval_unit: RecurrenceUnit | null
  current_interval_count: number | null
  current_cadence_label: string | null
  current_amount_type: AmountType | null
  current_next_due: string | null
  // A tracked subscription that looks like the same service under a different
  // name (e.g. "Claude" vs "Anthropic"). Offered as a choice, never applied.
  similar_subscription_id: string | null
  similar_reason: string | null
  similar_name: string | null
  similar_amount: number | null
  similar_currency: string | null
  similar_full_amount: number | null
  similar_share_ratio: number | null
  similar_split_mode: 'full' | 'ratio' | 'fixed' | null
  similar_cycle: string | null   // set when this is a price change
  similar_interval_unit: RecurrenceUnit | null
  similar_interval_count: number | null
  similar_cadence_label: string | null
  detected_at: string
}

export type ChangeKind = 'added' | 'price_change' | 'removed'

export interface SubscriptionChange {
  id: string
  subscription_id: string
  name: string
  kind: ChangeKind
  old_monthly: number | null
  new_monthly: number | null
  delta: number           // monthly-equivalent change, in the entry's currency
  currency: string
  changed_at: string
}

export interface User {
  id: string
  email: string
  name?: string
}

export interface Rates {
  base: string
  rates: Record<string, number>  // e.g. { USD: 0.63, GBP: 0.52 }
  cached: boolean
  fetched_at: string
  stale: boolean
  provider_date: string | null
}

export type Feature = 'spending' | 'payments' | 'goals' | 'workspace'

export interface Preferences {
  base_currency: Currency
  monthly_income: number | null  // null until the user states it
  timezone: string
  onboarding_completed?: boolean
  enabled_features?: Feature[]
  income_converted?: boolean
  income_conversion_rate_as_of?: string | null
}

export type ReminderKind = 'cancel' | 'renewal' | 'trial_end'
export type ReminderStatus = 'due' | 'upcoming' | 'overdue' | 'dismissed' | 'needs_date'

export interface PaymentReminder {
  id: string
  subscription_id: string
  subscription_name: string
  kind: ReminderKind
  days_before: number
  target_at: string | null
  alert_at: string | null
  date_source: 'fixed_date' | 'recorded' | 'projected_from_recorded_cycle' | 'missing'
  status: ReminderStatus
  days_until_target: number | null
  days_until_alert: number | null
  note: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ReminderInput {
  subscription_id: string
  kind: ReminderKind
  days_before: number
  target_date?: string | null
  note?: string | null
}

export interface DuplicateBrief {
  id: string
  name: string
  amount: number
  currency: string
  cycle: BillingCycle
  interval_unit: RecurrenceUnit
  interval_count: number
  cadence_label: string
}

export interface DuplicatePair {
  keep: DuplicateBrief
  merge: DuplicateBrief
  reason: string
}

/** Optional deployment capabilities. A failed fetch must fall back safely. */
export interface ApiCapabilities {
  flexible_recurrence: boolean
  payment_lifecycle: boolean
  variable_amounts: boolean
  server_equivalents: boolean
  gmail_secure_oauth: boolean
}

export interface ForecastCharge {
  id: string
  name: string
  category: Category
  due_at: string
  amount: number
  currency: string
  base_currency: string
  charge_amount_in_base: number | null
  charge_amount_is_estimate: boolean
  charge_kind: 'renewal' | 'trial_conversion' | 'intro'
  days_until_due: number
  due_date_source: 'recorded' | 'projected_from_recorded_cycle'
}

export interface SubscriptionForecast {
  scope: string
  forecast_semantics: string
  window_start: string
  window_end: string
  window_days: number
  charges: ForecastCharge[]
  occurrence_count: number
  forecast_total_in_base: number
  missing_due_date_count: number
  unconverted_occurrence_count: number
  paused_without_resume_count: number
  currency_conversion: {
    base_currency: string
    status: 'exact' | 'current_rates' | 'estimated' | 'incomplete'
    rates_as_of: string | null
    rates_stale: boolean
    warning: string | null
  }
}

export interface PaymentExtraRow {
  subscription_id: string
  amount: number
  currency: string
  amount_in_base: number | null
  charged_at: string
  reason: 'late_fee' | 'extra'
}

export interface CalendarMonthCharges extends SubscriptionForecast {
  year: number
  month: number
  extras?: PaymentExtraRow[]
}

export interface PaidPayment {
  target?: string
  manual?: string | null
  paid_amount?: number | null
  subscription_id: string
  name: string
  category: Category
  date: string
  amount: number
  currency: string
  amount_in_base: number | null
  status: 'confirmed' | 'expected' | 'unsorted' | 'skipped'
  kind: 'receipt' | 'schedule' | 'late_fee' | 'extra' | 'above_plan'
}

export interface PaidBill {
  target?: string
  manual?: string | null
  id: string
  subscription_id: string
  name: string
  category: Category
  issued_on: string
  due_on: string | null
  amount: number | null
  currency: string
  paid: number
  paid_on: string | null
  owing: number | null
  status: 'paid' | 'credit' | 'part_paid' | 'overdue' | 'due' | 'unknown' | 'carried'
  late_fee: number | null
}

export interface PaidHistory {
  base_currency: string
  since: string
  late_fees_total: number
  above_plan_total: number
  bills: PaidBill[]
  payments: PaidPayment[]
}

export interface PaymentExtrasSummary {
  subscription_id: string
  count: number
  total_in_base: number
  base_currency: string
}

export type PayIntervalUnit = 'week' | 'month'

export interface SafeToSpendProfileInput {
  balance: number
  currency: Currency
  next_payday: string
  pay_interval_unit: PayIntervalUnit
  pay_interval_count: number
  buffer: number
  payday_bills_after_pay: boolean
}

export interface SafeToSpend {
  status: 'needs_setup' | 'ready' | 'balance_outdated' | 'incomplete'
  scope: string
  safe_to_spend: number | null
  per_day?: number | null
  shortfall?: number | null
  next_payday?: string
  days_until_payday?: number
  balance_date?: string
  base_currency?: Currency
  balance?: number
  buffer?: number
  committed?: number
  commitments?: { id: string; name: string; due_at: string; amount: number; is_estimate: boolean }[]
  profile?: Omit<SafeToSpendProfileInput, 'next_payday'>
  warnings?: string[]
}

export type TransactionKind = 'expense' | 'income'

export interface Transaction {
  id: string
  kind: TransactionKind
  name: string
  amount: number
  currency: Currency
  base_amount: number | null
  base_currency: Currency | null
  rate_as_of: string | null
  category: Category
  occurred_on: string
  note: string | null
  source: string
  recurring_payment_id: string | null
  created_at: string | null
  updated_at: string | null
  /** A tracked payment charge shown for completeness; it cannot be edited here. */
  read_only?: boolean
  /** A logged expense whose linked payment is already charged this month. */
  counted_in_payment?: boolean
}

export interface TransactionInput {
  kind: TransactionKind
  name: string
  amount: number
  currency: Currency
  category: Category
  occurred_on?: string
  note?: string | null
}

export interface PossibleDuplicate {
  kind: string
  id: string
  name: string
  amount: number
  currency: Currency
  occurred_on: string | null
}

export interface CreatedTransaction extends Transaction {
  possible_duplicates: PossibleDuplicate[]
}

export interface TransactionSummary {
  month: string
  base_currency: Currency
  income: number
  expenses: number
  net: number
  expenses_by_category: Record<string, number>
  transaction_count: number
  payment_charge_count: number
  unconverted_count: number
  rate_as_of: string | null
  rate_stale: boolean
}

export interface BudgetStatus {
  id: string
  category: Category
  monthly_limit: number
  currency: Currency
  limit_in_base: number | null
  spent: number | null
  spent_logged: number | null
  spent_payments: number | null
  left: number | null
  share_used: number | null
  over: boolean | null
  near: boolean | null
  unconverted_count: number
}

export interface BudgetOverview {
  month: string
  base_currency: Currency
  budgets: BudgetStatus[]
  rate_as_of: string | null
  rate_stale: boolean
}

export interface BudgetInput {
  category: Category
  monthly_limit: number
}

export type GoalStatus = 'reached' | 'no_target_date' | 'on_the_way' | 'due_today' | 'target_date_passed'

export interface GoalContribution {
  id: string
  goal_id: string
  amount: number
  occurred_on: string
  note: string | null
  source: string
  created_at: string | null
}

export interface Goal {
  id: string
  name: string
  target_amount: number
  currency: Currency
  target_date: string | null
  archived_at: string | null
  created_at: string | null
  updated_at: string | null
  saved: number
  remaining: number
  percent: number
  status: GoalStatus
  days_left: number | null
  weeks_left: number | null
  needed_per_week: number | null
  needed_per_day: number | null
  contributions: GoalContribution[]
}

export interface GoalInput {
  name: string
  target_amount: number
  currency: Currency
  target_date?: string | null
}

export interface ContributionInput {
  amount: number
  occurred_on?: string
  note?: string | null
}

// Workspace
export type WorkspaceTemplateId = string

export interface WorkspaceTemplate {
  id: WorkspaceTemplateId
  name: string
  description: string
  block_types: WorkspaceBlockType[]
}

export interface WorkspacePageSummary {
  id: string
  title: string
  template_id: WorkspaceTemplateId | null
  block_count: number
  position: number
  updated_at: string | null
}

export interface ChecklistItem {
  text: string
  done: boolean
}

export interface SharedCostItem {
  label: string
  amount: number
  paid_by: string
  split_between: string[]
}

interface BlockBase {
  title?: string | null
}

export type WorkspaceBlockConfig =
  | (BlockBase & { type: 'payment_list'; category?: Category | null; payment_ids?: string[] | null })
  | (BlockBase & { type: 'transaction_log'; kind?: string | null; category?: Category | null; range?: string | null })
  | (BlockBase & { type: 'budget'; categories?: Category[] | null })
  | (BlockBase & { type: 'goal_progress'; goal_ids?: string[] | null })
  | (BlockBase & { type: 'upcoming_payments'; days?: number })
  | (BlockBase & { type: 'spending_trend'; months?: number; category?: Category | null })
  | (BlockBase & { type: 'checklist'; items: ChecklistItem[] })
  | (BlockBase & { type: 'shared_costs'; people: string[]; items: SharedCostItem[]; currency?: Currency | null })
  | (BlockBase & { type: 'notes'; text: string })

export type WorkspaceBlockType = WorkspaceBlockConfig['type']

export interface WorkspacePage {
  id: string
  title: string
  template_id: WorkspaceTemplateId | null
  blocks: WorkspaceBlockConfig[]
  position: number
  created_at: string | null
  updated_at: string | null
}

export interface WorkspacePageInput {
  title: string
  template_id: WorkspaceTemplateId
}

export interface WorkspacePageUpdate {
  title?: string
  blocks?: WorkspaceBlockConfig[]
}

export interface PaymentListRow {
  id: string
  name: string
  category: Category
  amount: number
  currency: Currency
  cadence_label: string
  next_due: string | null
  monthly_in_base: number | null
}

export interface PaymentListData {
  payments: PaymentListRow[]
  monthly_total_in_base: number
  unconverted_count: number
  missing_count: number
  inactive_count: number
}

export interface TransactionLogEntry {
  id: string
  kind: 'income' | 'expense'
  name: string
  category: Category
  amount: number
  currency: Currency
  occurred_on: string
  amount_in_base: number | null
}

export interface TransactionLogData {
  range: string
  base_currency: Currency
  entries: TransactionLogEntry[]
  entry_count: number
  income: number
  expenses: number
  unconverted_count: number
}

export interface UpcomingChargeRow {
  id: string
  name: string
  category: Category
  amount: number
  currency: Currency
  due_at: string
  days_until_due: number
  charge_amount_in_base: number | null
  charge_amount_is_estimate: boolean
}

export interface UpcomingPaymentsData {
  days: number
  charges: UpcomingChargeRow[]
  total_in_base: number
  unconverted_count: number
}

export interface SpendingTrendMonth {
  month: string
  logged_expenses: number
  tracked_payments: number
  has_unconverted: boolean
}

export interface SpendingTrendData {
  base_currency: Currency
  category: Category | null
  months: SpendingTrendMonth[]
}

export interface SharedCostsPerson {
  name: string
  paid: number
  share: number
  net: number
  status: 'is_owed' | 'owes' | 'settled'
}

export interface SharedCostsData {
  currency: Currency
  total: number
  people: SharedCostsPerson[]
}

export type WorkspaceBlockData =
  | { type: 'payment_list'; data: PaymentListData }
  | { type: 'transaction_log'; data: TransactionLogData }
  | { type: 'budget'; data: Omit<BudgetOverview, 'month'> & { month?: string } }
  | { type: 'goal_progress'; data: { goals: Goal[]; missing_count: number } }
  | { type: 'upcoming_payments'; data: UpcomingPaymentsData }
  | { type: 'spending_trend'; data: SpendingTrendData }
  | { type: 'checklist'; data: { items: ChecklistItem[] } }
  | { type: 'shared_costs'; data: SharedCostsData }
  | { type: 'notes'; data: { text: string } }

export type WorkspaceBlockResult =
  | (WorkspaceBlockData & { title: string | null; error?: undefined })
  | { type: string | null; title: string | null; error: string; data?: undefined }

export interface WorkspacePageData {
  id: string
  title: string
  blocks: WorkspaceBlockResult[]
}
