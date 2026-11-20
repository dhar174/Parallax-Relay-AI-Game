import time
import unittest
from unittest.mock import patch

import httpx

from parallax_relay.config import Rates
from parallax_relay.protocol import ROLES
from parallax_relay.realtime.coordination import Coordinator
from parallax_relay.realtime.fixture_transport import fixture_agents, historical_delays
from parallax_relay.realtime.observations import observe
from parallax_relay.realtime.physics import initial_world, step
from parallax_relay.realtime.settings import Settings


class FixtureTransportTests(unittest.IsolatedAsyncioTestCase):
    async def run_match(self, delays):
        settings = Settings.offline('test')
        agents = fixture_agents(settings, delays)
        rates = {role: Rates(input_per_million=1.0, output_per_million=2.0) for role in ROLES}
        records = []
        coordinator = Coordinator(agents, settings, rates,
                                  lambda kind, **data: records.append((kind, data)))
        world = initial_world()
        window = 0
        try:
            with patch.object(httpx.AsyncHTTPTransport, 'handle_async_request',
                              side_effect=AssertionError('real network is forbidden')):
                for window in range(1, 5):
                    observations = {role: observe(world, role, window, settings) for role in ROLES}
                    programs, _ = await coordinator.coordinate(observations, window, time.monotonic() + 20)
                    self.assertEqual(coordinator.dispositions, dict.fromkeys(ROLES, 'ok'))
                    for offset in range(settings.window_ticks):
                        step(world, programs, offset)
                        if world.completed:
                            break
                    if world.completed:
                        break
            summary = coordinator.budget.summary()
            self.assertTrue(world.completed)
            self.assertLessEqual(window, 4)
            self.assertEqual(summary['calls_started'], window * 9)
            self.assertEqual(summary['reported_input_tokens'], window * 9 * 256)
            self.assertEqual(summary['reported_output_tokens'], window * 9 * 64)
            self.assertEqual(summary['unknown_usage_calls'], 0)
            self.assertEqual(summary['reserved_calls'], 0)
            self.assertEqual(summary['input_usage_calls'], window * 9)
            self.assertTrue(all(row['status'] == 'ok' for kind, row in records if kind == 'attempt'))
            return window, coordinator.phase_records
        finally:
            await coordinator.close()
            for agent in agents.values():
                await agent.close()
                self.assertTrue(agent._client.is_closed)

    async def test_full_provider_wire_simulation_wins_in_four_windows(self):
        await self.run_match((0.0, 0.0, 0.0))

    async def test_scaled_historical_trace_runs_whole_match(self):
        delays = historical_delays(scale=0.001)
        self.assertEqual(len(delays), 3)
        self.assertTrue(all(len(role) == 3 for role in delays))
        self.assertAlmostEqual(max(max(role) for role in delays), 0.0161724)
        _, phases = await self.run_match(delays)
        self.assertEqual([phase['phase'] for phase in phases[:3]], ['broadcast', 'negotiate', 'commit'])
        self.assertTrue(all(phase['elapsed_seconds'] > 0 for phase in phases))


if __name__ == '__main__':
    unittest.main()
