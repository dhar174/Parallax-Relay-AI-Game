"""Accounting conservation and diagnostic-only engine instrumentation."""
import json
import unittest

from parallax_relay.budget import Budget
from parallax_relay.config import MatchSettings, Rates
from parallax_relay.engine import resolve_turn
from parallax_relay.protocol import AgentRequest, Observation, Usage, ROLES
from parallax_relay.state import Action, initial_world


class AccountingTests(unittest.TestCase):
    def test_all_diagnostic_codes_clear_stale_keys_and_keep_caller_actions(self):
        from copy import deepcopy
        cases=[('wait','SPECTRA',Action('WAIT'),{}),
               ('applied','SPECTRA',Action('MOVE',-1,1),{}),
               ('invalid_parameters','SPECTRA',Action('MOVE',0,3),{}),
               ('outer_wall','SPECTRA',Action('MOVE',-1,2),{'x':0}),
               ('unbridged_gap','SPECTRA',Action('MOVE',1,1),{'x':4}),
               ('role_or_range','SPECTRA',Action('VENT'),{}),
               ('insufficient_resource','PYRA',Action('VENT'),{'coolant':0}),
               ('already_done','FLUX',Action('REROUTE'),{'bridge_extended':True}),
               ('overload','FLUX',Action('REROUTE'),{'motor_heat':4}),
               ('nothing_to_collect','SPECTRA',Action('COLLECT'),{}),
               ('unknown_action','SPECTRA',Action('UNKNOWN'),{})]
        for code,role,action,changes in cases:
            with self.subTest(code=code):
                world=initial_world()
                for key,value in changes.items():
                    if key=='x':world.robots[role].x=value
                    else:setattr(world,key,value)
                actions={r:Action('WAIT') for r in ROLES};actions[role]=action
                before=deepcopy(actions);diagnostics={'STALE':'SECRET_SENTINEL'}
                observed=resolve_turn(world,actions,diagnostics=diagnostics)
                self.assertEqual(diagnostics[role],code);self.assertEqual(set(diagnostics),set(ROLES))
                self.assertEqual(actions,before)
                self.assertEqual(observed.snapshot(),resolve_turn(world,actions).snapshot())

    def test_partial_pricing_has_explicit_coverage_and_unknown_overall_total(self):
        rates={'SPECTRA':Rates(input_per_million=1,output_per_million=1)}
        budget=Budget(MatchSettings(max_attempts=1),rates)
        ticket=budget.reserve_phase({'SPECTRA':AgentRequest(Observation('SPECTRA',0,'{}',b''),'commit')})['SPECTRA']
        ticket.start();receipt=ticket.settle(Usage(10,2));ticket.release()
        summary=budget.summary()
        self.assertEqual(summary['priced_roles'],['SPECTRA']);self.assertEqual(summary['unpriced_roles'],['PYRA','FLUX'])
        self.assertEqual(summary['priced_role_estimated_usd'],receipt['settled_amount_usd'])
        self.assertIsNone(summary['estimated_cost_usd']);self.assertIsNone(summary['known_usage_estimated_usd'])

    def test_malformed_outcome_and_usage_are_rejected_or_allowlisted(self):
        from parallax_relay.campaign_analysis import _valid_summary, _project_usage
        self.assertFalse(_valid_summary({'win':False,'loss':False,'completed':False,'turns':0,
                                        'stop_reason':[], 'scores':None,'budget':{}}))
        projected = _project_usage({'input_tokens':10,'output_tokens':'SECRET_SENTINEL',
                                    'source_usage':{'unknown.path':{'state':'count','value':'SECRET_SENTINEL'}}})
        self.assertEqual(projected['input_tokens'],10)
        self.assertIsNone(projected['output_tokens'])
        self.assertNotIn('SECRET_SENTINEL',json.dumps(projected))

    def test_partial_unknown_and_complete_settlements_reconcile_without_repricing_partial_usage(self):
        rates = {r: Rates(input_per_million=1, output_per_million=2) for r in ROLES}
        budget = Budget(MatchSettings(), rates)
        requests = {r: AgentRequest(Observation(r, 0, '{}', b''), 'commit') for r in ROLES}
        tickets = budget.reserve_phase(requests)
        usage = {'SPECTRA': Usage(100, 20), 'PYRA': Usage(None, 15), 'FLUX': None}
        receipts = []
        for role, ticket in tickets.items():
            ticket.start()
            receipts.append(ticket.settle(usage[role]))
            ticket.release()
        summary = budget.summary()
        self.assertAlmostEqual(summary['estimated_cost_usd'], sum(r['settled_amount_usd'] for r in receipts))
        self.assertAlmostEqual(summary['known_usage_estimated_usd'] + summary['retained_estimate_usd'], summary['estimated_cost_usd'])
        self.assertEqual(summary['reported_input_tokens'], 100)
        self.assertEqual(summary['reported_output_tokens'], 35)
        self.assertEqual(summary['input_usage_calls'], 1)
        self.assertEqual(summary['output_usage_calls'], 2)
        self.assertEqual(summary['unknown_usage_calls'], 2)
        self.assertEqual(summary['calls_reserved_total'] - summary['calls_released'], summary['calls_started'])
        self.assertEqual(summary['reserved_calls'], 0)
        self.assertEqual(summary['reserved_estimated_usd'], 0)
        self.assertEqual(receipts[1]['settled_amount_usd'], receipts[1]['reservation_quote_usd'])

    def test_unpriced_settlement_is_null_even_for_known_zero_usage(self):
        budget = Budget(MatchSettings(), {})
        ticket = budget.reserve_phase({'SPECTRA': AgentRequest(Observation('SPECTRA', 0, '{}', b''), 'commit')})['SPECTRA']
        ticket.start()
        receipt = ticket.settle(Usage(0, 0))
        ticket.release()
        self.assertEqual(receipt['settlement_basis'], 'complete_usage')
        self.assertIsNone(receipt['settled_amount_usd'])
        self.assertIsNone(budget.summary()['known_usage_estimated_usd'])

    def test_engine_diagnostics_do_not_change_world_or_expose_legality_to_policies(self):
        world = initial_world()
        cases = [
            ({'SPECTRA': Action('MOVE', -1, 2), 'PYRA': Action('VENT'), 'FLUX': Action('REROUTE')},
             {'SPECTRA': 'applied', 'PYRA': 'applied', 'FLUX': 'applied'}),
            ({'SPECTRA': Action('MOVE', -1, 3), 'PYRA': Action('WAIT', 1), 'FLUX': Action('UNLOCK')},
             {'SPECTRA': 'invalid_parameters', 'PYRA': 'invalid_parameters', 'FLUX': 'role_or_range'}),
        ]
        for actions, expected in cases:
            diagnostics = {}
            observed = resolve_turn(world, actions, diagnostics=diagnostics)
            self.assertEqual(observed.snapshot(), resolve_turn(world, actions).snapshot())
            self.assertEqual(diagnostics, expected)
            self.assertNotIn('action_outcomes', observed.snapshot())
