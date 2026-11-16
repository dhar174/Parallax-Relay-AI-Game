"""Preparation receipts must bound the approved design without running trials."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / 'scripts/prepare_campaign.py'


class CampaignPreparationTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_preparation_counts_approved_assignments_and_every_baseline(self):
        # Dropping deduplication, baselines, an arm, or retries changes exposure.
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'candidate'
            result = self.command('prepare', '--out', bundle)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads((bundle / 'receipt.json').read_text())
            for stage, trials, models, baselines, calls, provider_attempts in (
                ('qualification', 15, 15, 0, 432, 432),
                ('pilot', 330, 225, 105, 57024, 38880),
                ('confirmatory', 3660, 2700, 960, 632448, 466560),
            ):
                row = receipt['stages'][stage]
                self.assertEqual((row['trials'], row['model_trials'], row['baseline_trials'], row['max_calls']),
                                 (trials, models, baselines, calls))
                self.assertEqual(row['max_provider_attempts'], provider_attempts)
                spec = json.loads((bundle / row['spec_file']).read_text())
                self.assertEqual(spec['campaign_max_calls'], calls)
                self.assertEqual(row['assignments'], 3)
                self.assertEqual(spec['campaign_max_estimated_cost_usd'], models * spec['match']['max_estimated_cost_usd'])
            self.assertFalse((bundle / 'registration.json').exists())
            self.assertFalse((bundle / 'ledger.jsonl').exists())

    def test_checker_rejects_tampering_and_existing_destination(self):
        # A matching receipt must never bless an edited candidate specification.
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'candidate'
            self.assertEqual(self.command('prepare', '--out', bundle).returncode, 0)
            self.assertEqual(self.command('check', '--bundle', bundle).returncode, 0)
            self.assertNotEqual(self.command('prepare', '--out', bundle).returncode, 0)
            spec = bundle / 'qualification.json'
            data = json.loads(spec.read_text())
            data['match']['max_attempts'] = 1
            spec.write_text(json.dumps(data))
            result = self.command('check', '--bundle', bundle)
            self.assertNotEqual(result.returncode, 0)

    def test_worksheet_covers_unicode_history_and_complete_retry_phases(self):
        # Forgetting escaping, history, image reserve, or whole-phase retries
        # would understate the maximum retained local reservation exposure.
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'candidate'
            result = self.command('prepare', '--out', bundle)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads((bundle / 'receipt.json').read_text())
            q = receipt['stages']['qualification']['worksheet']
            p = receipt['stages']['pilot']['worksheet']
            self.assertGreater(q['maximum_request_input_quote_tokens'], 50000)
            self.assertGreater(p['maximum_request_input_quote_tokens'], q['maximum_request_input_quote_tokens'])
            self.assertLess(p['maximum_request_input_quote_tokens'], 272000)
            self.assertGreater(p['retained_quote_bound_usd'], q['retained_quote_bound_usd'])
            for row in (q, p):
                self.assertGreaterEqual(row['match_guard_usd'], row['retained_quote_bound_usd'])
                self.assertEqual(row['phase_retry_attempts'], 6)
                self.assertTrue(row['cost_is_estimate_not_billing_guarantee'])

    def test_smoke_profile_cannot_silently_change_approved_common_limits(self):
        # Reusing a later smoke profile must not silently change the Q/P/C plan.
        from scripts import prepare_campaign
        with tempfile.TemporaryDirectory() as temp:
            profile = json.loads((ROOT / 'configs/live_smoke.json').read_text())
            profile['config']['match']['max_attempts'] = 3
            path = Path(temp) / 'profile.json'
            path.write_text(json.dumps(profile))
            with patch.object(prepare_campaign, 'PROFILE', path):
                with self.assertRaisesRegex(ValueError, 'approved common limits'):
                    prepare_campaign.load_inputs()

    def test_frozen_check_rejects_dirty_source_without_spending_authority(self):
        # Merely checking a preview cannot promote dirty development to a frozen review.
        from scripts import prepare_campaign
        with tempfile.TemporaryDirectory() as temp, patch('parallax_relay.campaign.collect_source',
                return_value={'status': 'dirty', 'revision': '0' * 40, 'reason': None}):
            bundle = Path(temp) / 'candidate'
            prepare_campaign.write_bundle(bundle)
            with self.assertRaisesRegex(ValueError, 'Clean source'):
                prepare_campaign.check_bundle(bundle, require_clean=True)

    def test_envelope_dominates_valid_unicode_replies_and_huge_action_integers(self):
        # Small ASCII-only examples must not conceal real accepted reply sizes.
        from dataclasses import asdict
        from scripts import prepare_campaign as prep
        from parallax_relay.budget import Budget
        from parallax_relay.config import MatchSettings, Rates
        from parallax_relay.protocol import AgentRequest, ChatMessage, Observation, ROLES, parse_reply
        from parallax_relay.state import initial_world, public_hud
        message = '\U0010ffff' * 400
        notes = '\U0010ffff' * 1000
        reply = parse_reply(json.dumps({'turn': 11,
            'action': {'kind': 'REROUTE', 'direction': -(10 ** 3999), 'steps': 10 ** 3999},
            'notes': notes}, ensure_ascii=False), 'commit', 11)
        messages = tuple(ChatMessage(r, 11, phase, message)
                         for phase in ('broadcast', 'negotiate') for r in ROLES)
        rates = {r: Rates(input_per_million=0.3, output_per_million=2.5) for r in ROLES}
        settings = MatchSettings(max_output_tokens=4096)
        actual, envelopes = {}, {}
        for role in ROLES:
            hud = public_hud(initial_world(), role)
            history = [{'turn': 10, 'your_observation': hud,
                'public_messages': [asdict(m) for m in messages],
                'your_action': asdict(reply.action.to_engine()), 'events': []}] * 4
            actual[role] = AgentRequest(Observation(role, 11, json.dumps(hud), b''), 'commit',
                messages=messages, history_json=json.dumps(history), private_notes=notes,
                max_output_tokens=4096)
            envelopes[role] = prep.envelope(role, 11, 'commit', 'full', 4)
        actual_tickets = Budget(settings, rates).reserve_phase(actual)
        upper_tickets = Budget(settings, rates).reserve_phase(envelopes)
        for role in ROLES:
            self.assertGreaterEqual(upper_tickets[role].quote, actual_tickets[role].quote)


if __name__ == '__main__':
    unittest.main()
