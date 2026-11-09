"""Ready-made workspace pages, each a starting layout built from the fixed blocks."""

from dataclasses import dataclass
from typing import Literal

TemplateId = Literal[
    "monthly_budget",
    "savings_goal",
    "moving_house",
    "bill_price_check",
    "cutting_subscriptions",
    "shared_household_bills",
    "trip_budget",
    "debt_payoff",
]


@dataclass(frozen=True)
class Template:
    id: TemplateId
    name: str
    description: str
    blocks: tuple[dict, ...]


TEMPLATES: dict[str, Template] = {
    template.id: template
    for template in (
        Template(
            "monthly_budget",
            "Monthly budget",
            "See this month's spending against your category budgets.",
            (
                {"type": "budget"},
                {"type": "transaction_log", "range": "this_month"},
                {"type": "upcoming_payments", "days": 30},
                {"type": "spending_trend", "months": 6},
            ),
        ),
        Template(
            "savings_goal",
            "Savings goal",
            "Track progress towards a goal and what you spend along the way.",
            (
                {"type": "goal_progress"},
                {"type": "spending_trend", "months": 6},
                {"type": "notes", "title": "Plan"},
            ),
        ),
        Template(
            "moving_house",
            "Moving house",
            "Keep the move's costs, bills to switch over and to-dos in one place.",
            (
                {
                    "type": "checklist",
                    "title": "Moving checklist",
                    "items": [
                        {"text": "Update address on bills and subscriptions"},
                        {"text": "Set up electricity, gas and internet"},
                        {"text": "Book removalists"},
                    ],
                },
                {"type": "payment_list", "title": "Bills to move", "category": "utilities"},
                {"type": "transaction_log", "title": "Moving costs", "range": "last_3_months"},
                {"type": "notes"},
            ),
        ),
        Template(
            "bill_price_check",
            "Bill price check",
            "List your bills next to notes on cheaper options you have found.",
            (
                {"type": "payment_list", "title": "Utilities", "category": "utilities"},
                {"type": "payment_list", "title": "Phone and internet", "category": "phone_internet"},
                {"type": "payment_list", "title": "Insurance", "category": "insurance"},
                {"type": "notes", "title": "Quotes and options"},
            ),
        ),
        Template(
            "cutting_subscriptions",
            "Cutting subscriptions",
            "Review your subscriptions and tick off the ones you cancel.",
            (
                {"type": "payment_list", "title": "Streaming", "category": "streaming"},
                {"type": "payment_list", "title": "Software", "category": "software"},
                {"type": "upcoming_payments", "days": 30},
                {"type": "checklist", "title": "To cancel"},
            ),
        ),
        Template(
            "shared_household_bills",
            "Shared household bills",
            "Split household costs and see who owes whom.",
            (
                {"type": "shared_costs"},
                {"type": "payment_list", "title": "Household bills", "category": "utilities"},
                {"type": "upcoming_payments", "days": 30},
            ),
        ),
        Template(
            "trip_budget",
            "Trip budget",
            "Save for a trip, track travel spending and share costs with others.",
            (
                {"type": "goal_progress"},
                {"type": "transaction_log", "title": "Travel spending", "category": "travel"},
                {"type": "shared_costs"},
                {"type": "checklist", "title": "Before you go"},
            ),
        ),
        Template(
            "debt_payoff",
            "Debt payoff",
            "Track your own debt repayments and the steps you have planned.",
            (
                {"type": "payment_list", "title": "Repayments", "category": "debt"},
                {"type": "transaction_log", "title": "Payments made", "category": "debt", "range": "last_3_months"},
                {"type": "checklist", "title": "Steps"},
                {"type": "notes"},
            ),
        ),
    )
}
