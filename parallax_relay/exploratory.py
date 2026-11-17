"""Fixed offline description of the under-$20 exploratory study.

These builders do not resolve credentials, create clients, or authorize spending.
"""
from collections.abc import Mapping
from types import MappingProxyType


PROFILE_ID = 'exploratory-under20-v1'

# One Gemini role per room, fixed across the development and held-out splits.
GEMINI_ROLE_BY_ROOM = MappingProxyType({
    'split_span': 'FLUX', 'dev_01': 'SPECTRA', 'dev_02': 'PYRA',
    'ret_01': 'FLUX', 'ret_02': 'SPECTRA', 'ret_03': 'PYRA',
    'relay_01': 'FLUX', 'relay_02': 'SPECTRA', 'relay_03': 'PYRA',
})


def profile_spec(stage: str) -> dict:
    """Return a fresh, complete raw specification for an approved stage."""
    if type(stage) is not str or stage not in ('pilot', 'validation'):
        raise ValueError('Exploratory profile supports only pilot and validation')
    def openai():
        return {'provider': 'openai', 'model': 'gpt-6-luna', 'api_key_env': 'OPENAI_API_KEY',
                'pricing': {'input_per_million': 0.125, 'output_per_million': 0.5}}

    return {
        'schema_version': 2, 'protocol_version': 3, 'stage': stage, 'mode': 'live',
        'policies': ['scripted', 'wait', 'uniform'],
        'roster': [openai(), openai(),
                   {'provider': 'gemini', 'model': 'gemini-3.5-flash-lite', 'api_key_env': 'GEMINI_API_KEY',
                    'pricing': {'input_per_million': 0.3, 'output_per_million': 2.5}}],
        'rooms': (['split_span', 'dev_01', 'dev_02'] if stage == 'pilot' else
                  ['ret_01', 'ret_02', 'ret_03', 'relay_01', 'relay_02', 'relay_03']),
        'conditions': ['full', 'reduced', 'disabled', 'withheld', 'no_images'],
        'repetitions': 1,
        'match': {'room_id': 'split_span', 'communication_rounds': 2, 'condition': None,
                  'max_turns': 12, 'max_calls': 216, 'max_attempts': 2, 'timeout_seconds': 60.0,
                  'max_output_tokens': 4096, 'history_turns': 4, 'retry_delay_seconds': 0.5,
                  'max_consecutive_failures': 3, 'max_estimated_cost_usd': 0.25,
                  'image_token_reserve': 8192},
        'campaign_max_calls': 10368 if stage == 'pilot' else 20736,
        'campaign_max_estimated_cost_usd': 3.75 if stage == 'pilot' else 7.5,
        'scheduler_seed': 0, 'min_trial_interval_seconds': 1.0,
        'rerun_of': None, 'rerun_reason': None,
    }


def profile_analysis() -> dict:
    """Declare a descriptive per-room analysis, without confirmatory inference."""
    return {'version': 3, 'profile_id': PROFILE_ID, 'evidence_class': 'exploratory',
            'method': 'descriptive_per_room', 'bootstrap_resamples': 0, 'seed': 0,
            'percentile': None, 'prng': None, 'concurrency': 1,
            'primary_contrast': ['full', 'disabled']}


def is_exploratory(spec) -> bool:
    """Identify protocol 3 in either a validated spec or its raw mapping."""
    version = spec.get('protocol_version') if isinstance(spec, Mapping) else getattr(spec, 'protocol_version', None)
    return type(version) is int and version == 3
