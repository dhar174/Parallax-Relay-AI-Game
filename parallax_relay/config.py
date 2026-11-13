"""Explicit model selection and environment-only credentials."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import tomllib
from typing import Literal, Mapping
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from .protocol import ROLES


class ConfigError(ValueError):
    pass


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Rates(Settings):
    input_per_million: float = Field(gt=0)
    output_per_million: float = Field(gt=0)


class MatchSettings(Settings):
    communication_rounds: Literal[1, 2] = 2
    max_turns: int = Field(default=12, ge=1, le=12)
    max_calls: int = Field(default=216, ge=1, le=10000)
    max_attempts: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    max_output_tokens: int = Field(default=2048, ge=256, le=16384)
    history_turns: int = Field(default=4, ge=0, le=12)
    retry_delay_seconds: float = Field(default=0.5, ge=0, le=30)
    max_consecutive_failures: int = Field(default=3, ge=1, le=20)
    max_estimated_cost_usd: float | None = Field(default=None, gt=0)
    image_token_reserve: int = Field(default=8192, ge=1, le=1000000)


class PlayerSettings(Settings):
    provider: Literal['openai', 'anthropic', 'gemini']
    model_env: str
    api_key_env: str
    pricing: Rates | None = None

    @model_validator(mode='after')
    def validate_env_names(self):
        for name in (self.model_env, self.api_key_env):
            if not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,127}', name):
                raise ValueError('Use environment variable names, not credentials or model values')
        return self


@dataclass(frozen=True)
class RuntimePlayer:
    provider: str
    model: str
    api_key: str = field(repr=False)
    pricing: Rates | None = None


class GameConfig(Settings):
    match: MatchSettings = MatchSettings()
    players: dict[str, PlayerSettings]

    @model_validator(mode='after')
    def validate_roles(self):
        if set(self.players) != set(ROLES):
            raise ValueError('This slice requires exactly SPECTRA, PYRA and FLUX')
        if self.match.max_estimated_cost_usd is not None and any(p.pricing is None for p in self.players.values()):
            raise ValueError('A spending guard requires explicit pricing for every player')
        return self

    def resolve(self, environ: Mapping[str, str] | None = None) -> dict[str, RuntimePlayer]:
        env = os.environ if environ is None else environ
        missing = sorted({name for player in self.players.values()
                          for name in (player.model_env, player.api_key_env)
                          if not env.get(name, '').strip()})
        if missing:
            raise ConfigError('Missing environment values: ' + ', '.join(missing))
        result = {}
        for role, player in self.players.items():
            model = env[player.model_env].strip()
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', model):
                raise ConfigError(f'Invalid model ID in {player.model_env}; use a bare model ID')
            key = env[player.api_key_env].strip()
            if '\n' in key or '\r' in key:
                raise ConfigError(f'Invalid credential format in {player.api_key_env}')
            result[role] = RuntimePlayer(player.provider, model, key, player.pricing)
        return result


def load_config(path: Path) -> GameConfig:
    try:
        with path.open('rb') as handle:
            return GameConfig.model_validate(tomllib.load(handle))
    except UnicodeDecodeError:
        raise ConfigError('Configuration file must use UTF-8 encoding') from None
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        # ValidationError often embeds original input values. Do not echo them.
        if isinstance(exc, ValidationError):
            fields = ', '.join('.'.join(map(str, e['loc'])) or 'configuration' for e in exc.errors())
            raise ConfigError(f'Invalid configuration fields: {fields}') from None
        raise ConfigError(f'Cannot load configuration: {path.name}') from None
