"""Tests for Region arithmetic + perceptual hash (no display required)."""

from __future__ import annotations

from PIL import Image

from window_translation.capture.screen import (
    Region,
    hamming_distance,
    perceptual_hash,
)


def test_region_normalized_handles_negative_dimensions() -> None:
    r = Region(100, 100, -40, -20).normalized()
    assert r == Region(60, 80, 40, 20)


def test_region_is_valid() -> None:
    assert Region(0, 0, 10, 10).is_valid()
    assert not Region(0, 0, 1, 1).is_valid()


def test_region_right_bottom() -> None:
    r = Region(5, 7, 10, 20)
    assert r.right == 15
    assert r.bottom == 27


def test_perceptual_hash_identical_images() -> None:
    img = Image.new("RGB", (32, 32), (128, 64, 200))
    h1 = perceptual_hash(img)
    h2 = perceptual_hash(img.copy())
    assert h1 == h2
    assert hamming_distance(h1, h2) == 0


def test_perceptual_hash_differs_for_different_images() -> None:
    a = Image.new("RGB", (32, 32), (0, 0, 0))
    # Draw a bright square into half of `b` so it is not uniform (aHash
    # cannot distinguish two uniform images by construction).
    b = Image.new("RGB", (32, 32), (0, 0, 0))
    for x in range(16):
        for y in range(32):
            b.putpixel((x, y), (255, 255, 255))
    assert perceptual_hash(a) != perceptual_hash(b)
