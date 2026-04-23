"""Screen-capture primitives.

Uses :mod:`mss` for fast, multi-monitor, DPI-aware screenshots. The output
is converted to a :class:`PIL.Image.Image` for downstream OCR preprocessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from PIL.Image import Image


@dataclass(frozen=True)
class Region:
    """A rectangular region in virtual-desktop coordinates.

    Coordinates are inclusive of ``left``/``top`` and exclusive of the
    right/bottom edges, matching Python/Pillow conventions. ``left``/``top``
    may be negative on multi-monitor setups.
    """

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def normalized(self) -> "Region":
        """Return a region with non-negative width/height."""
        left = self.left if self.width >= 0 else self.left + self.width
        top = self.top if self.height >= 0 else self.top + self.height
        return Region(left, top, abs(self.width), abs(self.height))

    def is_valid(self, min_size: int = 4) -> bool:
        return self.width >= min_size and self.height >= min_size


def capture_region(region: Region) -> "Image":
    """Capture ``region`` from the screen and return a Pillow image."""
    # Local import so the module can be imported on headless CI where mss
    # might fail to initialise a display connection.
    import mss
    from PIL import Image

    region = region.normalized()
    if not region.is_valid():
        raise ValueError(f"Region too small to capture: {region!r}")

    with mss.mss() as sct:
        shot = sct.grab(
            {
                "left": region.left,
                "top": region.top,
                "width": region.width,
                "height": region.height,
            }
        )
    # ``mss`` returns BGRA; convert to RGB for Pillow / Tesseract.
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    return img


def perceptual_hash(img: "Image", size: int = 8) -> int:
    """Compute a simple perceptual hash (aHash) of ``img``.

    Returns an integer whose Hamming distance to another hash approximates
    image similarity. Used by the region-pin mode to detect when the
    captured area has actually changed, avoiding wasted API calls.
    """
    from PIL import Image as PILImage

    small = img.convert("L").resize((size, size), PILImage.Resampling.BILINEAR)
    pixels = list(small.tobytes())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= avg:
            bits |= 1 << i
    return bits


def hamming_distance(a: int, b: int) -> int:
    """Bit-count of the XOR of two perceptual hashes."""
    return (a ^ b).bit_count()


def list_monitors() -> list[dict]:
    """Return the list of monitors as reported by ``mss`` (for diagnostics)."""
    import mss

    with mss.mss() as sct:
        # ``sct.monitors[0]`` is the virtual screen, [1:] are individual monitors.
        return [dict(m) for m in sct.monitors]


__all__ = [
    "Region",
    "capture_region",
    "perceptual_hash",
    "hamming_distance",
    "list_monitors",
]
