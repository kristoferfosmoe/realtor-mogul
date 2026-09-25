"""Market-data ingestion: source adapters plus a pipeline that archives and upserts."""

from collections.abc import Callable

from mogul.config import Settings

from .base import Source
from .demo import DemoSource
from .fred import FredSource
from .zillow import ZillowSource

SOURCES: dict[str, Callable[[Settings], Source]] = {
    "zillow": lambda s: ZillowSource(max_metros=s.zillow_max_metros),
    "fred": lambda s: FredSource(),
}

ATTRIBUTIONS = {
    "zillow": ZillowSource.attribution,
    "fred": FredSource.attribution,
    "demo": DemoSource.attribution,
}
