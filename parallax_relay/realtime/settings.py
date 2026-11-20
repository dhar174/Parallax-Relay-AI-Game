"""Validated real-time limits and the explicit, offline-readable live proposal."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..config import ConfigError, Rates
from ..protocol import ROLES
from ..providers import HTTPAgent


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, allow_inf_nan=False)

    max_windows: int = Field(default=4, ge=1, le=1000)
    window_ticks: int = Field(default=120, ge=1, le=3600)
    tick_rate: Literal[60] = 60
    action_points: int = Field(default=8, ge=1, le=100)
    max_commands: int = Field(default=4, ge=1, le=4)
    phase_timeout_seconds: float = Field(default=20.0, gt=0, le=600)
    wall_seconds: float = Field(default=240.0, gt=0, le=3600)
    cleanup_seconds: float = Field(default=5.0, gt=0, le=5)
    clock_mode: Literal['freeze', 'continue'] = 'freeze'
    communication_rounds: Literal[0, 1, 2] = 2
    max_calls: int = Field(default=36, ge=1, le=10000)
    max_attempts: int = Field(default=1, ge=1, le=3)
    max_output_tokens: int = Field(default=4096, ge=256, le=16384)
    image_token_reserve: int = Field(default=8192, ge=1, le=1000000)
    max_estimated_cost_usd: float | None = Field(default=1.0, gt=0)
    max_consecutive_failures: int = Field(default=3, ge=1, le=20)
    history_turns: int = Field(default=4, ge=0, le=12)
    retry_delay_seconds: float = Field(default=0.5, ge=0, le=30)

    @property
    def timeout_seconds(self) -> float:
        return self.phase_timeout_seconds

    @classmethod
    def offline(cls, mode: Literal['reactive', 'manual', 'baseline', 'test'] = 'reactive') -> 'Settings':
        if mode not in {'reactive', 'manual', 'baseline', 'test'}:
            raise ValueError('Unknown offline mode')
        return cls(phase_timeout_seconds=120.0 if mode == 'manual' else 5.0,
                   wall_seconds=3600.0 if mode == 'manual' else 240.0,
                   max_estimated_cost_usd=None)


class Player(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    provider: Literal['openai', 'gemini']
    model: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
    api_key_env: Literal['OPENAI_API_KEY', 'GEMINI_API_KEY']
    pricing: Rates
    model_url: str
    pricing_url: str

    @model_validator(mode='after')
    def check_key_name(self):
        if self.api_key_env != {'openai': 'OPENAI_API_KEY', 'gemini': 'GEMINI_API_KEY'}[self.provider]:
            raise ValueError('Provider credential variable mismatch')
        return self


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    name: Literal['dev-bridge-live-v1']
    prices_verified_date: str
    settings: Settings
    players: dict[str, Player]

    @model_validator(mode='after')
    def check_roles_and_caps(self):
        if set(self.players) != set(ROLES):
            raise ValueError('Exactly three active roles are required')
        if self.settings != Settings():
            raise ValueError('Live proposal limits do not match the approved profile')
        expected = {'SPECTRA': ('openai', 'gpt-6-luna'), 'PYRA': ('openai', 'gpt-6-luna'),
                    'FLUX': ('gemini', 'gemini-3.5-flash-lite')}
        if any((self.players[r].provider, self.players[r].model) != expected[r] for r in ROLES):
            raise ValueError('Live proposal roster does not match the approved profile')
        return self

    @property
    def rates(self) -> dict[str, Rates]:
        return {role: player.pricing for role, player in self.players.items()}


_PROFILE_PATH = Path(__file__).resolve().parents[2] / 'configs' / 'realtime_dev_bridge_live_v1.json'


def load_profile(name: str) -> Profile:
    if name != 'dev-bridge-live-v1':
        raise ConfigError('Unknown real-time profile')
    try:
        return Profile.model_validate_json(_PROFILE_PATH.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValidationError, ValueError):
        raise ConfigError('Invalid or unavailable real-time profile') from None


def describe_profile(profile: Profile) -> dict:
    """Describe the proposal without reading credentials or making requests."""
    return {'name': profile.name, 'prices_verified_date': profile.prices_verified_date,
            'prices_require_revalidation': True,
            'settings': profile.settings.model_dump(),
            'players': {role: {'provider': p.provider, 'model': p.model,
                               'pricing': p.pricing.model_dump(), 'model_url': p.model_url,
                               'pricing_url': p.pricing_url} for role, p in profile.players.items()},
            'estimated_cost_is_not_billing_cap': True,
            'live_command': 'python -m parallax_relay.realtime --live --profile dev-bridge-live-v1'}


def make_live_agents(profile: Profile, environ: Mapping[str, str] | None = None) -> dict[str, HTTPAgent]:
    """Construct independent clients only when an explicitly live caller invokes this."""
    env = os.environ if environ is None else environ
    keys = {}
    for player in profile.players.values():
        key = env.get(player.api_key_env, '').strip()
        if not key or '\n' in key or '\r' in key:
            raise ConfigError('Missing or invalid live provider credential')
        keys[player.api_key_env] = key
    return {role: HTTPAgent(p.provider, p.model, keys[p.api_key_env],
                            timeout_seconds=profile.settings.phase_timeout_seconds)
            for role, p in profile.players.items()}
