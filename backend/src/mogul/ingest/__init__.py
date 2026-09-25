"""Market-data ingestion: source adapters plus a pipeline that archives and upserts."""

from collections.abc import Callable

from mogul.config import Settings

from .base import Source
from .census import AcsSource
from .fred import FredSource
from .hud import TOKEN_HELP as HUD_TOKEN_HELP
from .hud import HudFmrSource
from .zillow import ZillowSource

SOURCES: dict[str, Callable[[Settings], Source]] = {
    "zillow": lambda s: ZillowSource(max_metros=s.zillow_max_metros),
    "fred": lambda s: FredSource(),
    "hud": lambda s: HudFmrSource(s.hud_api_token, years=s.hud_fmr_years),
    "census": lambda s: AcsSource(s.census_api_key, years=s.acs_years),
}

ATTRIBUTIONS = {
    "zillow": ZillowSource.attribution,
    "fred": FredSource.attribution,
    "hud": HudFmrSource.attribution,
    "census": AcsSource.attribution,
}


def missing_config(name: str, settings: Settings) -> str | None:
    """Why a source cannot fetch with these settings, or None if it can."""
    if name == "hud" and not settings.hud_api_token:
        return HUD_TOKEN_HELP
    return None
