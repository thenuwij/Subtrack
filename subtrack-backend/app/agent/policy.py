"""The one written advice boundary every Pocketday AI feature follows.

ADVICE_BOUNDARY is the rule text given to the model. check_user_text screens
text the AI writes into something the user keeps, such as a saved note, so
product advice can't slip in there even if the model ignores the rules.
"""
import re

ADVICE_BOUNDARY = (
    "- Pocketday does not provide financial-product advice. Do not recommend or compare investments, "
    "shares, ETFs, crypto, super funds, insurance, loans, credit cards, buy now pay later services, "
    "or specific bank or savings products, and do not tell the user to buy, sell, switch or hold them.\n"
    "- Do not give tax or debt-restructuring advice specific to the user. If asked for anything outside "
    "this boundary, say plainly that Pocketday can't help with that part, then offer the relevant facts "
    "from the user's own data.\n"
    "- You may track, organise and do the maths on the user's own data. You may give general budgeting "
    "tips, suggest where to cut back based on the user's data, and suggest cheaper alternatives for "
    "everyday goods and services. Label these as suggestions."
)

PRODUCT_ADVICE_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\binvest(?:ing|ment)?s? in (?:the )?(?:shares|stocks|bonds|etfs?|crypto|property|funds?|index|the market|super)\b",
        r"\b(?:buy|sell|hold)(?:ing)? (?:some )?(?:shares|stocks|bonds)\b",
        r"\bshare portfolio\b",
        r"\b(?:index|managed) funds?\b",
        r"\betfs?\b",
        r"\bcrypto(?:currency|currencies)?\b",
        r"\b(?:bitcoin|ethereum)\b",
        r"(?<![-\w])term deposits?\b",
        r"\bhigh[- ]interest (?:savings )?accounts?\b",
        r"\bswitch (?:your |my )?super\b",
        r"\bsuper funds?\b",
        r"\bcredit cards? with\b",
        r"\b(?:get|apply for|open|take out) (?:a |an )?(?:new )?(?:credit card|personal loan|loan|savings account)\b",
        r"\b(?:use|try|sign up for) (?:afterpay|zip pay|bnpl|buy now,? pay later)\b",
        r"\brefinanc(?:e|ing)\b",
        r"\bconsolidate (?:your |my )?debts?\b",
    )
)


def check_user_text(text: str) -> str | None:
    """Return the first product-advice phrase found in AI-written text, or None if it is fine."""
    for pattern in PRODUCT_ADVICE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None
