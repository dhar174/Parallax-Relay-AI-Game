"""Hard request limits plus an optional conservative LOCAL cost estimate.

A phase reserves every player's retry allowance before starting anyone. Unknown
usage keeps its full estimate. Dollar estimates are not provider billing limits.
"""
from __future__ import annotations

from decimal import Decimal
import json
from .config import MatchSettings, Rates
from .protocol import AgentRequest, Usage, ROLES, response_schema
from .prompts import SYSTEM_RULES


class BudgetExceeded(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _price(usage: Usage, rates: Rates) -> Decimal:
    return (Decimal(usage.input_tokens or 0) * Decimal(str(rates.input_per_million)) +
            Decimal(usage.output_tokens or 0) * Decimal(str(rates.output_per_million))) / Decimal(1000000)


class Budget:
    def __init__(self, settings: MatchSettings, rates: dict[str, Rates | None]):
        self.settings, self.rates = settings, rates
        if settings.max_estimated_cost_usd is not None and any(rates.get(r) is None for r in ROLES):
            raise ValueError('Explicit model pricing is required for a spending guard')
        self.calls_started = 0
        self.reserved_calls = 0
        self.reserved_usd = Decimal(0)
        self.spent = Decimal(0)
        self.known_usage_usd = Decimal(0)
        self.retained_estimate_usd = Decimal(0)
        self.calls_reserved_total = 0
        self.calls_released = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.unknown_usage_calls = 0
        self.input_usage_calls = self.output_usage_calls = 0
        self.cached_input_tokens = self.reasoning_output_tokens = 0
        self.priced = all(rates.get(r) is not None for r in ROLES)

    def reserve_phase(self, requests: dict[str, AgentRequest]) -> dict[str, 'Ticket']:
        count = len(requests) * self.settings.max_attempts
        if self.calls_started + self.reserved_calls + count > self.settings.max_calls:
            raise BudgetExceeded('call_budget')
        quotes = {}
        for role, request in requests.items():
            # Byte count rather than the usual chars/4 heuristic deliberately
            # overestimates text. Image reserve remains model-dependent.
            text = SYSTEM_RULES + request.prompt_text() + json.dumps(response_schema(request.phase))
            tokens = len(text.encode('utf-8')) + (self.settings.image_token_reserve if request.include_image else 0) + 2048
            rates = self.rates.get(role)
            quotes[role] = _price(Usage(tokens, request.max_output_tokens), rates) if rates else Decimal(0)
        total = sum(quotes.values()) * self.settings.max_attempts
        cap = self.settings.max_estimated_cost_usd
        if cap is not None and self.spent + self.reserved_usd + total > Decimal(str(cap)):
            raise BudgetExceeded('spend_budget')
        self.reserved_calls += count
        self.calls_reserved_total += count
        self.reserved_usd += total
        return {r: Ticket(self, r, q, self.settings.max_attempts) for r, q in quotes.items()}

    def summary(self) -> dict:
        return {
            'calls_started': self.calls_started,
            'max_calls': self.settings.max_calls,
            'reported_input_tokens': self.input_tokens,
            'reported_output_tokens': self.output_tokens,
            'unknown_usage_calls': self.unknown_usage_calls,
            'input_usage_calls': self.input_usage_calls,
            'output_usage_calls': self.output_usage_calls,
            'reported_cached_input_tokens': self.cached_input_tokens,
            'reported_reasoning_output_tokens': self.reasoning_output_tokens,
            'calls_reserved_total': self.calls_reserved_total,
            'calls_released': self.calls_released,
            'reserved_calls': self.reserved_calls,
            'reserved_estimated_usd': float(self.reserved_usd) if self.priced else None,
            'known_usage_estimated_usd': float(self.known_usage_usd) if self.priced else None,
            'retained_estimate_usd': float(self.retained_estimate_usd) if self.priced else None,
            'estimated_cost_usd': float(self.spent) if self.priced else None,
            'cost_is_estimate_not_billing_guarantee': True,
        }


class Ticket:
    def __init__(self, budget: Budget, role: str, quote: Decimal, remaining: int):
        self.budget, self.role, self.quote = budget, role, quote
        self.remaining = remaining
        self.active = False

    def start(self) -> None:
        if self.remaining <= 0 or self.active:
            raise RuntimeError('Invalid call reservation')
        self.remaining -= 1
        self.active = True
        self.budget.reserved_calls -= 1
        self.budget.calls_started += 1

    def settle(self, usage: Usage | None) -> dict:
        if not self.active:
            raise RuntimeError('No active call to settle')
        self.active = False
        budget = self.budget
        budget.reserved_usd -= self.quote
        known = usage is not None and usage.input_tokens is not None and usage.output_tokens is not None
        rates = budget.rates.get(self.role)
        settled = _price(usage, rates) if known and rates else self.quote
        budget.spent += settled
        if known:
            budget.known_usage_usd += settled
        else:
            budget.retained_estimate_usd += settled
        if not known:
            budget.unknown_usage_calls += 1
        if usage:
            budget.input_tokens += usage.input_tokens or 0
            budget.output_tokens += usage.output_tokens or 0
            budget.input_usage_calls += int(usage.input_tokens is not None)
            budget.output_usage_calls += int(usage.output_tokens is not None)
            budget.cached_input_tokens += usage.cached_input_tokens
            budget.reasoning_output_tokens += usage.reasoning_output_tokens
        return {'reservation_quote_usd': float(self.quote) if rates else None,
                'settlement_basis': 'complete_usage' if known else 'retained_estimate',
                'settled_amount_usd': float(settled) if rates else None}

    def release(self) -> None:
        if self.active:
            self.settle(None)
        self.budget.reserved_calls -= self.remaining
        self.budget.calls_released += self.remaining
        self.budget.reserved_usd -= self.quote * self.remaining
        self.remaining = 0
