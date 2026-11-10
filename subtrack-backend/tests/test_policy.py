import os
import unittest

os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from app.agent.policy import ADVICE_BOUNDARY, check_user_text  # noqa: E402


class CheckUserTextTests(unittest.TestCase):
    def test_product_advice_wording_is_flagged(self):
        for text, phrase in (
            ("Invest in an index fund each payday", "index fund"),
            ("Invest in shares this year", "Invest in shares"),
            ("Buy shares with what's left over", "Buy shares"),
            ("Put $50 a week into ETFs", "ETFs"),
            ("Move savings into crypto", "crypto"),
            ("Buy some Bitcoin", "Bitcoin"),
            ("Open a term deposit for the bond", "term deposit"),
            ("Find a high-interest savings account", "high-interest savings account"),
            ("Switch your super to a cheaper fund", "Switch your super"),
            ("Pick a super fund with low fees", "super fund"),
            ("Get a credit card with rewards points", "credit card with"),
            ("Apply for a personal loan to cover the bond", "Apply for a personal loan"),
            ("Use Afterpay for the new fridge", "Use Afterpay"),
            ("Refinance the car loan", "Refinance"),
            ("Consolidate your debts into one", "Consolidate your debts"),
        ):
            with self.subTest(text=text):
                self.assertEqual(check_user_text(text), phrase)

    def test_ordinary_page_text_is_not_flagged(self):
        for text in (
            "Save for a trip",
            "Moving checklist",
            "Update address on bills and subscriptions",
            "Investigate cheaper internet plans",
            "Split the internet with Sam and Priya",
            "Sam's share of rent",
            "Get three car insurance quotes",
            "Pay off the credit card",
            "Afterpay repayments",
            "Super Bowl party",
            "Invest in a good mattress",
            "Short-term deposit for the new flat",
            "",
        ):
            with self.subTest(text=text):
                self.assertIsNone(check_user_text(text))


class AdviceBoundaryTests(unittest.TestCase):
    def test_system_rules_use_the_single_advice_boundary(self):
        from app.routers.agent import SYSTEM_RULES

        self.assertIn(ADVICE_BOUNDARY, SYSTEM_RULES)
        self.assertEqual(SYSTEM_RULES.count("does not provide financial-product advice"), 1)

    def test_boundary_names_the_products_it_rules_out(self):
        for product in ("investments", "ETFs", "crypto", "super funds", "credit cards", "buy now pay later"):
            with self.subTest(product=product):
                self.assertIn(product, ADVICE_BOUNDARY)


if __name__ == "__main__":
    unittest.main()
