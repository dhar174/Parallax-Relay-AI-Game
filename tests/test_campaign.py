"""Offline campaign accounting and all-trial reporting; never contacts providers."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dataclasses import replace


def model(provider='openai', name='test-model', key='TEST_KEY'):
    return {'provider': provider, 'model': name, 'api_key_env': key,
            'pricing': {'input_per_million': 1, 'output_per_million': 1}}


def live_spec(**overrides):
    return spec(**{'mode': 'live', 'policies': [], 'roster': [model(), model(), model('gemini', 'another-model')],
                   'match': {'max_turns': 1, 'max_attempts': 1, 'max_estimated_cost_usd': 1},
                   'campaign_max_estimated_cost_usd': 100, **overrides})


def spec(**overrides):
    return {'schema_version': 1, 'stage': 'diagnostic', 'mode': 'offline',
            'policies': ['wait'], 'conditions': ['full', 'reduced', 'disabled', 'withheld', 'no_images'],
            'match': {'max_turns': 1, 'max_attempts': 1}, 'campaign_max_calls': 1000, **overrides}


class CampaignTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_is_offline_and_native_trials_reconcile(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            registration = register(spec(), root)
            self.assertEqual(len(registration['schedule']), 5)
            self.assertFalse((root / 'ledger.jsonl').exists())
            with patch('parallax_relay.campaign.HTTPAgent', side_effect=AssertionError('network forbidden')):
                await run_campaign(root, offline=True)
            report = analyze(root)
            self.assertEqual(report['counts']['planned'], 5)
            self.assertEqual(report['counts']['launched'], 5)
            self.assertEqual(report['counts']['artifact_available'], 5)
            self.assertEqual(report['counts']['known_operational_failures'], 5)
            self.assertEqual(sum(r['calls_started'] for r in report['trials']), 36)
            self.assertEqual(report['counts']['engine_defeat'], 0)
            self.assertEqual(report['campaign_accounting']['calls_accounted'],36)
            self.assertEqual(report['campaign_accounting']['reservation_balance_calls'],0)

    async def test_block_budget_stops_before_any_launch(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(spec(campaign_max_calls=35), root)
            await run_campaign(root, offline=True)
            report = analyze(root)
            self.assertEqual(report['counts']['launched'], 0)
            self.assertEqual(report['counts']['unlaunched'], 5)
            self.assertEqual(report['completion_status'], 'incomplete')
            self.assertEqual(report['cells'][0]['operational_success']['rate'], None)

    async def test_setup_failure_is_known_failure_even_without_recorder(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(spec(), root)
            with patch('parallax_relay.campaign.Recorder', side_effect=OSError('SECRET_SENTINEL')):
                await run_campaign(root, offline=True)
            report = analyze(root)
            self.assertEqual(report['counts']['launched'], 1)
            self.assertEqual(report['counts']['known_operational_failures'], 1)
            self.assertEqual(report['counts']['unknown_operational'], 0)
            self.assertNotIn('SECRET_SENTINEL', (root / 'ledger.jsonl').read_text(encoding='utf-8'))

    async def test_cancellation_drains_inflight_calls_releases_block_and_cannot_restart(self):
        from parallax_relay.campaign import CampaignError, register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        from parallax_relay.policies import WaitAgent
        entered, closed = asyncio.Event(), []
        class Slow(WaitAgent):
            async def respond(self, request):
                entered.set()
                await asyncio.Event().wait()
            async def close(self):
                closed.append(self.role)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(spec(), root)
            with patch('parallax_relay.campaign.make_policy', side_effect=lambda name, role, trial: Slow(role)):
                task = asyncio.create_task(run_campaign(root, offline=True))
                await entered.wait()
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            report = analyze(root)
            self.assertEqual(report['counts']['launched'], 1)
            self.assertEqual(report['counts']['cancelled'], 1)
            self.assertEqual(report['counts']['nonterminal'], 1)
            self.assertEqual(report['campaign_accounting']['reservation_balance_calls'],0)
            self.assertEqual(len(closed), 3)
            events = [json.loads(line) for line in (root/'ledger.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(any(e['event'] == 'block_released' for e in events))
            self.assertFalse((root / '.runner.lock').exists())
            with self.assertRaises(CampaignError):
                await run_campaign(root, offline=True)

    async def test_ledger_failure_before_launch_never_starts_a_trial(self):
        from parallax_relay.campaign import Ledger, register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        original = Ledger.emit
        def fail(ledger, event, **fields):
            if event == 'trial_launched':
                raise OSError('SECRET_SENTINEL')
            return original(ledger, event, **fields)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(spec(), root)
            with patch.object(Ledger, 'emit', fail), patch('parallax_relay.campaign.execute_trial') as execute:
                with self.assertRaises(OSError):
                    await run_campaign(root, offline=True)
                execute.assert_not_called()
            self.assertEqual(analyze(root)['counts']['launched'], 0)

    async def test_missing_receipt_preserves_unknown_success_and_artifacts(self):
        from parallax_relay.campaign import Ledger, register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        original = Ledger.emit
        def fail(ledger, event, **fields):
            if event == 'trial_finished':
                raise OSError('SECRET_SENTINEL')
            return original(ledger, event, **fields)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(spec(policies=['scripted'], conditions=['full'], match={'max_turns': 7}), root)
            with patch.object(Ledger, 'emit', fail):
                with self.assertRaises(OSError):
                    await run_campaign(root, offline=True)
            report = analyze(root)
            self.assertEqual(report['counts']['engine_win'], 1)
            self.assertEqual(report['counts']['unknown_operational'], 1)
            self.assertEqual(report['overall']['operational_success']['launched_bounds'], [0, 1])
            self.assertEqual(report['contrasts'], [])

    async def test_fake_priced_providers_reconcile_quotes_and_usage_without_network(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        from parallax_relay.policies import WaitAgent
        from parallax_relay.protocol import ModelReply, Usage
        class FakeHTTP(WaitAgent):
            def __init__(self, provider, model, key, **kwargs):
                self.provider = provider
            async def respond(self, request):
                self.role = request.role
                reply = await super().respond(request)
                return ModelReply(reply.text, Usage(100, 10))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(live_spec(), root)
            with patch('parallax_relay.campaign.HTTPAgent', FakeHTTP):
                await run_campaign(root, live=True, environ={'TEST_KEY': 'FAKE'})
            report = analyze(root)
            self.assertEqual(report['counts']['planned'], 15)
            self.assertEqual(report['counts']['launched'], 15)
            self.assertEqual(report['counts']['artifact_available'], 15)
            self.assertAlmostEqual(report['overall']['cost']['known_estimated_usd'], .01188)
            self.assertAlmostEqual(report['overall']['cost']['known_usage_estimated_usd'], .01188)
            self.assertEqual(report['overall']['cost']['retained_estimate_usd'], 0)
            self.assertTrue(all(a['settlement_basis'] == 'complete_usage' for a in report['attempts']))

    async def test_dollar_block_guard_rejects_whole_block_without_provider_construction(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(live_spec(campaign_max_estimated_cost_usd=4), root)
            with patch('parallax_relay.campaign.HTTPAgent') as provider:
                await run_campaign(root, live=True, environ={'TEST_KEY':'FAKE'})
                provider.assert_not_called()
            report = analyze(root)
            self.assertEqual(report['counts']['launched'], 0)
            self.assertEqual(report['campaign_stop']['reason'], 'campaign_spend_budget')

    async def test_missing_and_corrupt_artifacts_remain_in_denominator(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze, write_report
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'campaign'
            register(spec(), root)
            await run_campaign(root, offline=True)
            first = next((root/'trials').iterdir())
            (first/'calls.jsonl').write_text('{broken', encoding='utf-8')
            (first/'manifest.json').unlink()
            with (root/'ledger.jsonl').open('a',encoding='utf-8') as handle:
                handle.write('{partial')
            report = analyze(root)
            self.assertEqual(report['counts']['launched'], 5)
            self.assertEqual(report['counts']['artifact_available'], 4)
            self.assertFalse(report['confirmatory_eligible'])
            write_report(report, Path(temp)/'report')
            self.assertEqual(json.loads((Path(temp)/'report/report.json').read_text(encoding='utf-8'))['counts'], report['counts'])

    async def test_complete_native_pilot_then_confirmatory_uniform_pipeline(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        clean = {'status': 'clean', 'revision': 'a'*40, 'reason': None}
        with tempfile.TemporaryDirectory() as temp, \
             patch('parallax_relay.campaign.collect_source', return_value=clean), \
             patch('parallax_relay.provenance.collect_source', return_value=clean), \
             patch('parallax_relay.campaign_analysis.collect_source', return_value=clean):
            pilot, confirmation = Path(temp)/'pilot', Path(temp)/'confirmation'
            value = spec(stage='pilot',policies=['scripted','wait','uniform'],campaign_max_calls=10000)
            register(value,pilot)
            await run_campaign(pilot,offline=True)
            self.assertTrue(analyze(pilot)['cohort_eligible'])
            register({**value,'stage':'confirmatory'},confirmation,pilot=pilot)
            await run_campaign(confirmation,offline=True)
            report = analyze(confirmation)
            self.assertEqual(report['counts']['planned'],160)
            self.assertTrue(report['confirmatory_eligible'])
            self.assertEqual(len(report['contrasts']),4)
            self.assertTrue(all(c['degenerate_interval'] for c in report['contrasts']))
            self.assertEqual(report['contrasts'][0]['resamples'],10000)

    async def test_amount_overrun_stops_launches_without_clamping_accounting(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        from parallax_relay.policies import WaitAgent
        from parallax_relay.protocol import ModelReply, Usage
        class Expensive(WaitAgent):
            def __init__(self,*args,**kwargs): pass
            async def respond(self,request):
                self.role = request.role
                reply = await super().respond(request)
                return ModelReply(reply.text,Usage(10000000,10000000))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign'
            register(live_spec(),root)
            with patch('parallax_relay.campaign.HTTPAgent',Expensive):
                await run_campaign(root,live=True,environ={'TEST_KEY':'FAKE'})
            report=analyze(root)
            self.assertEqual(report['counts']['launched'],1)
            self.assertEqual(report['campaign_stop']['reason'],'accounting_overrun')
            self.assertGreater(report['campaign_stop']['accounted_estimated_usd'],1)

    async def test_cleanup_failure_after_engine_win_is_operational_failure(self):
        from parallax_relay.campaign import register, run_campaign
        from parallax_relay.campaign_analysis import analyze
        from parallax_relay.agents import ScriptedAgent
        class BadClose(ScriptedAgent):
            async def close(self): raise OSError('SECRET_SENTINEL')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'campaign'
            register(spec(policies=['scripted'],conditions=['full'],match={'max_turns':7}),root)
            with patch('parallax_relay.campaign.make_policy',side_effect=lambda name,role,trial:BadClose(role)):
                await run_campaign(root,offline=True)
            report=analyze(root)
            self.assertEqual(report['counts']['engine_win'],1)
            self.assertEqual(report['counts']['operational_successes'],0)
            self.assertEqual(report['trials'][0]['stop_reason'],'local_error')
            self.assertEqual(report['trials'][0]['recording_stop_reason'],'victory')
            self.assertNotIn('SECRET_SENTINEL',json.dumps(report))


class ScheduleTests(unittest.TestCase):
    def test_rotations_deduplicate_requested_provider_model_pairs(self):
        from parallax_relay.campaign_models import CampaignSpec, assignments, schedule
        value = CampaignSpec.model_validate(live_spec())
        self.assertEqual(len(assignments(value)), 3)
        value = CampaignSpec.model_validate(live_spec(roster=[model('openai','same'),model('gemini','same'),model('anthropic','same')]))
        self.assertEqual(len(assignments(value)), 6)
        rows = schedule(value)
        self.assertEqual(len(rows), 30)
        self.assertEqual(len({r['trial_id'] for r in rows}), 30)
        self.assertEqual([(r['assignment_id'],r['condition']) for r in rows],
                         [(r['assignment_id'],r['condition']) for r in schedule(value)])

    def test_protocol_counts_and_theoretical_block_exposure(self):
        from parallax_relay.campaign_models import CampaignSpec, schedule, trial_exposure
        base = {'schema_version':1,'campaign_max_calls': 1000000, 'stage': 'pilot'}
        rows = schedule(CampaignSpec(**base))
        self.assertEqual(len(rows), 35)  # 25 uniform, five WAIT, five oracle.
        self.assertEqual(len(schedule(CampaignSpec(**{**base,'stage':'confirmatory'}))), 160)
        conf = CampaignSpec(schema_version=1,campaign_max_calls=1000000)
        first_block = [t for t in schedule(conf) if t['team'] == 'scripted']
        self.assertEqual(sum(trial_exposure(conf,t)[0] for t in first_block), 864)

    def test_registration_tampering_and_source_drift_fail_closed(self):
        from parallax_relay.campaign import CampaignError, register, read_registration
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'campaign'
            data = register(spec(),root)
            data['schedule'][0]['trial_id'] = '../escape'
            (root/'registration.json').write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaises(CampaignError):
                read_registration(root)
            with self.assertRaises(CampaignError):
                register(spec(stage='confirmatory',policies=['scripted','wait','uniform']),Path(temp)/'confirm')


class StatisticsTests(unittest.TestCase):
    def test_protocol_example_wilson_and_bounds(self):
        from parallax_relay.campaign_analysis import wilson, success_summary
        interval = wilson(5, 10)
        self.assertAlmostEqual(interval[0], .2366, places=3)
        self.assertAlmostEqual(interval[1], .7634, places=3)
        summary = success_summary(5, 10, 12, 0)
        self.assertEqual(summary['all_planned_bounds'], [5 / 12, 7 / 12])
        self.assertEqual(success_summary(0, 0, 5, 0)['rate'], None)

    def test_bootstrap_uses_paired_assignment_weights_and_type7(self):
        from parallax_relay.campaign_analysis import paired_bootstrap, percentile
        self.assertAlmostEqual(percentile([0, 10, 20, 30], .25), 7.5)
        groups = {'a': [(1,0)]*30, 'b': [(0,1)]*30}
        result = paired_bootstrap(groups)
        self.assertEqual(result['difference_percentage_points'], 0)
        self.assertEqual(result['interval_95_percentage_points'], [0,0])
        self.assertTrue(result['degenerate_interval'])
        self.assertEqual(result, paired_bootstrap(groups))
