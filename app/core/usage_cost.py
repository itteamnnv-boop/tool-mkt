"""Standard USD list-price estimates for the token history, not billing balances.

Rates checked 2026-09-23 against the model pages at
https://developers.openai.com/api/docs/models/ and
https://platform.claude.com/docs/en/about-claude/pricing and
https://docs.x.ai/developers/models/grok-4.7 .
Historical usage is repriced at this snapshot; cache discounts, tax, credits,
tools, video, and requests without recorded token usage are not included.
"""
from dataclasses import dataclass
from decimal import Decimal

PRICE_DATE = "23/09/2026"
OPENAI_PRICING = "https://developers.openai.com/api/docs/pricing"
CLAUDE_PRICING = "https://platform.claude.com/docs/en/about-claude/pricing"
GROK_PRICING = "https://docs.x.ai/developers/models/grok-4.7"

# Per million tokens: minimum input, maximum input, output.
# Image inputs have different text/image prices; old history lacks the split.
RATES = {
    ("grok", "grok-4.7"): ("2", "2", "6"),
    ("openai", "gpt-5.4"): ("2.5", "2.5", "15"),
    ("openai", "gpt-5.4-2026-03-05"): ("2.5", "2.5", "15"),
    ("openai", "gpt-4o-mini"): ("0.15", "0.15", "0.60"),
    ("openai", "gpt-4o-mini-2024-07-18"): ("0.15", "0.15", "0.60"),
    ("openai", "gpt-image-1"): ("5", "10", "40"),
    ("openai", "gpt-image-1-mini"): ("2", "2.5", "8"),
    ("openai", "gpt-image-1.5"): ("5", "8", "32"),
    ("claude", "claude-sonnet-5"): ("2", "2", "10"),
    ("claude", "claude-sonnet-4-6"): ("3", "3", "15"),
    ("claude", "claude-sonnet-4-5"): ("3", "3", "15"),
    ("claude", "claude-sonnet-4-5-20250929"): ("3", "3", "15"),
    ("claude", "claude-haiku-4-5"): ("1", "1", "5"),
    ("claude", "claude-haiku-4-5-20251001"): ("1", "1", "5"),
}


@dataclass(frozen=True)
class CostEstimate:
    low: Decimal
    high: Decimal

    def display(self):
        def amount(value):
            return "< $0.0001" if 0 < value < Decimal("0.0001") else f"${value:,.4f}"
        low, high = amount(self.low), amount(self.high)
        return low if low == high else f"{low} – {high}"


def estimate_cost(provider, model, input_tokens, output_tokens):
    provider = provider.strip().lower()
    if provider == "anthropic":
        provider = "claude"
    rate = RATES.get((provider, model.strip().lower()))
    if rate is None:
        return None  # Never price an unknown model using a similar model's rate.
    inputs, outputs = max(0, int(input_tokens or 0)), max(0, int(output_tokens or 0))
    if not inputs and not outputs:
        return None
    low, high, output = map(Decimal, rate)
    million = Decimal(1_000_000)
    return CostEstimate((inputs * low + outputs * output) / million,
                        (inputs * high + outputs * output) / million)


def summarize_costs(providers):
    rows = [estimate_cost(provider, model, inputs, outputs) for provider, model, inputs, outputs, _ in providers]
    total = CostEstimate(sum((row.low for row in rows if row), Decimal(0)),
                         sum((row.high for row in rows if row), Decimal(0)))
    missing = sum(int(provider[4]) for provider, estimate in zip(providers, rows) if estimate is None)
    return rows, total, missing
