import unittest
from parallax_relay.budget import Budget, BudgetExceeded
from parallax_relay.config import MatchSettings, Rates
from parallax_relay.protocol import AgentRequest, Usage
from parallax_relay.observations import observe
from parallax_relay.state import initial_world


def requests():
    return {r:AgentRequest(observe(initial_world(),r),'broadcast') for r in initial_world().robots}


class BudgetTests(unittest.TestCase):
    def test_phase_reservation_is_all_or_nothing(self):
        budget=Budget(MatchSettings(max_calls=5),{})
        with self.assertRaises(BudgetExceeded): budget.reserve_phase(requests())
        self.assertEqual(budget.summary()['calls_started'],0)
        self.assertEqual(budget.reserved_calls,0)

    def test_unused_retry_slots_return_to_pool(self):
        budget=Budget(MatchSettings(max_calls=6),{})
        tickets=budget.reserve_phase(requests())
        for ticket in tickets.values():
            ticket.start(); ticket.settle(Usage(100,10)); ticket.release()
        self.assertEqual(budget.summary()['calls_started'],3)
        self.assertEqual(budget.reserved_calls,0)
        self.assertEqual(budget.summary()['reported_input_tokens'],300)

    def test_money_guard_stops_before_calls(self):
        rates={r:Rates(input_per_million=10,output_per_million=20) for r in initial_world().robots}
        budget=Budget(MatchSettings(max_estimated_cost_usd=0.001),rates)
        with self.assertRaises(BudgetExceeded): budget.reserve_phase(requests())
        self.assertEqual(budget.summary()['calls_started'],0)

    def test_unknown_usage_keeps_estimate_not_zero(self):
        rates={r:Rates(input_per_million=1,output_per_million=2) for r in initial_world().robots}
        budget=Budget(MatchSettings(),rates)
        tickets=budget.reserve_phase(requests())
        t=tickets['SPECTRA']; estimate=t.quote
        t.start(); t.settle(None)
        for ticket in tickets.values(): ticket.release()
        self.assertGreater(budget.summary()['estimated_cost_usd'],0)
        self.assertAlmostEqual(budget.summary()['estimated_cost_usd'],float(estimate))
        self.assertEqual(budget.summary()['unknown_usage_calls'],1)

    def test_cost_guard_requires_all_prices(self):
        with self.assertRaises(ValueError): Budget(MatchSettings(max_estimated_cost_usd=1),{})

    def test_partial_usage_retains_estimate_and_releases_reservations(self):
        rates = {r: Rates(input_per_million=1, output_per_million=2) for r in initial_world().robots}
        for usage in (Usage(100, None), Usage(None, 10)):
            with self.subTest(usage=usage):
                budget = Budget(MatchSettings(), rates)
                tickets = budget.reserve_phase(requests())
                ticket = tickets['SPECTRA']
                estimate = ticket.quote
                ticket.start(); ticket.settle(usage)
                for reservation in tickets.values():
                    reservation.release()
                self.assertEqual(budget.spent, estimate)
                self.assertGreater(budget.spent, 0)
                self.assertEqual(budget.summary()['unknown_usage_calls'], 1)
                self.assertEqual(budget.summary()['reported_input_tokens'], usage.input_tokens or 0)
                self.assertEqual(budget.summary()['reported_output_tokens'], usage.output_tokens or 0)
                self.assertEqual(budget.reserved_calls, 0)
                self.assertEqual(budget.reserved_usd, 0)
