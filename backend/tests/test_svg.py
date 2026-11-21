"""The SVG cleaner (app/svg.py) against files made to break it or to reach outside:
sizes no page has. Its everyday cleaning is tested with templates' images
(test_template_assets.py)."""

from __future__ import annotations

import pytest

from app.svg import MAX_SIDE, SvgRejected, clean_svg


def svg(attributes: str, inside: str = '<rect width="1" height="1"/>') -> bytes:
    return f'<svg xmlns="http://www.w3.org/2000/svg" {attributes}>{inside}</svg>'.encode()


@pytest.mark.parametrize("size", [
    'viewBox="0 0 inf inf"', 'viewBox="0 0 1e999 1e999"', 'viewBox="0 0 1e30 1e30"',
    'viewBox="0 0 210 Infinity"', 'width="' + "9" * 23 + '" height="10"',
    'viewBox="0 0 10000001 10"',
])
def test_a_size_too_large_to_keep_is_refused(size: str) -> None:
    """Each of these was an OverflowError: rounding infinity, or a width no database
    column holds."""
    with pytest.raises(SvgRejected, match="at most 10,000,000 across"):
        clean_svg(svg(size))


def test_sizes_up_to_the_limit_are_kept() -> None:
    assert MAX_SIDE == 10_000_000
    largest = clean_svg(svg('viewBox="0 0 10000000 1e7"'))
    assert (largest.width, largest.height) == (MAX_SIDE, MAX_SIDE)
    # Not a number at all: sized by the width and height instead, as before.
    fallback = clean_svg(svg('viewBox="0 0 nan nan" width="210" height="297"'))
    assert (fallback.width, fallback.height) == (210, 297)
