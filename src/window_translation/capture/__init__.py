"""Screen capture and region-selection helpers."""

from .screen import Region, capture_region, perceptual_hash


def __getattr__(name: str):
    # Lazily import the Qt-dependent selector so that modules which only
    # need the capture primitives (e.g. unit tests) don't force a PySide6
    # import.
    if name == "RegionSelector":
        from .selector import RegionSelector  # noqa: WPS433 — lazy import
        return RegionSelector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Region", "capture_region", "perceptual_hash", "RegionSelector"]
