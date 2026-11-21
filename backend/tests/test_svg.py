"""The SVG cleaner (app/svg.py) against files made to break it or to reach outside:
sizes no page has, values that load from elsewhere in ways the allowlist missed, and
parts that draw each other without end. Its everyday cleaning is tested with
templates' images (test_template_assets.py)."""

from __future__ import annotations

import pytest

from app.svg import MAX_SIDE, SvgRejected, clean_svg

VIEW = 'viewBox="0 0 10 10"'


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


@pytest.mark.parametrize("attribute", [
    # CSS reads u\72l( as url(.
    'fill="u\\72l(https://evil.example/x.svg#a)"',
    'style="fill:u\\72l(https://evil.example/x.svg#a)"',
    # These take an address as plain text, with no url() around it.
    "mask=\"image-set('https://evil.example/m.png' 1x)\"",
    "mask=\"image('https://evil.example/m.png')\"",
    'mask="-webkit-image-set(url(#m) 1x)"',
    'stroke="cross-fade(url(#a), url(#b))"',
    # A url( left open still loads.
    'fill="url(https://evil.example/x.svg#a"',
    'fill="url(#a) url(https://evil.example/x.svg#a"',
    'fill="expression(alert(1))"',
])
def test_a_value_that_could_load_from_elsewhere_is_dropped(attribute: str) -> None:
    clean = clean_svg(svg(VIEW, f'<rect width="1" height="1" {attribute}/>')).data.decode()
    assert '<rect width="1" height="1" />' in clean


def test_the_values_drawing_needs_are_kept() -> None:
    clean = clean_svg(svg(VIEW, (
        '<g transform="translate(1,2),rotate(45) scale (2)" clip-path="url( \'#c\' )">'
        '<rect width="1" height="1" fill="URL(#g)" stroke="rgb(10%, 20%, 30%)" '
        'style="stop-color:hsla(120, 50%, 50%, .5)"/></g>'))).data.decode()
    for kept in ('transform="translate(1,2),rotate(45) scale (2)"', "clip-path=\"url( '#c' )\"",
                 'fill="URL(#g)"', 'stroke="rgb(10%, 20%, 30%)"',
                 'stop-color="hsla(120, 50%, 50%, .5)"'):
        assert kept in clean


def test_parts_that_unfold_into_too_many_are_refused() -> None:
    """Ten shapes drawn ten times, those drawn ten times, and so on eight deep: under
    2 KB that draws a billion shapes, though it holds 91 elements."""
    groups = ['<g id="l0">' + '<rect width="1" height="1"/>' * 10 + "</g>"]
    for level in range(1, 9):
        groups.append(f'<g id="l{level}">' + f'<use href="#l{level - 1}"/>' * 10 + "</g>")
    bomb = svg(VIEW, "<defs>" + "".join(groups[:-1]) + "</defs>" + groups[-1])
    assert len(bomb) < 2048
    with pytest.raises(SvgRejected, match="too complex"):
        clean_svg(bomb)
    # The same through fills: each pattern's shapes are filled with the one before.
    patterns = ['<pattern id="p0" width="1" height="1"><rect width="1" height="1"/></pattern>']
    for level in range(1, 9):
        patterns.append(f'<pattern id="p{level}" width="1" height="1">'
                        + f'<rect width="1" height="1" fill="url(#p{level - 1})"/>' * 10
                        + "</pattern>")
    with pytest.raises(SvgRejected, match="too complex"):
        clean_svg(svg(VIEW, "<defs>" + "".join(patterns) + "</defs>"
                      '<rect width="10" height="10" fill="url(#p8)"/>'))
    # A long chain is worked out without running out of stack.
    chain = "".join(f'<g id="c{i}"><use href="#c{i + 1}"/></g>' for i in range(9000))
    with pytest.raises(SvgRejected, match="too complex"):
        clean_svg(svg(VIEW, chain))


@pytest.mark.parametrize("loop", [
    '<g id="a"><use href="#a"/></g>',
    '<g id="a"><use href="#b"/></g><g id="b"><use href="#a"/></g>',
    '<pattern id="p" width="1" height="1"><rect width="1" height="1" fill="url(#p)"/></pattern>',
])
def test_a_part_that_draws_itself_is_refused(loop: str) -> None:
    with pytest.raises(SvgRejected, match="draws itself"):
        clean_svg(svg(VIEW, loop))


def test_a_picture_that_reuses_its_parts_is_kept() -> None:
    """As a converted PDF does: every letter is a <use> of its glyph."""
    glyphs = "".join(f'<symbol id="glyph-{i}"><path d="M0 0L1 1"/></symbol>' for i in range(60))
    letters = "".join(f'<use href="#glyph-{i % 60}" x="{i}" y="0"/>' for i in range(5000))
    gradients = ('<linearGradient id="base"><stop offset="0" stop-color="#2B5D8A"/>'
                 '</linearGradient><linearGradient id="tilted" href="#base" '
                 'gradientTransform="rotate(45)"/>')
    clipped = ('<g clip-path="url(#clip)"><clipPath id="clip"><rect width="5" height="5"/>'
               '</clipPath><rect width="10" height="10" fill="url(#tilted)"/></g>')
    clean = clean_svg(svg(VIEW, f"<defs>{glyphs}{gradients}</defs>{letters}{clipped}"))
    assert clean.data.count(b"<use ") == 5000
    assert b'fill="url(#tilted)"' in clean.data and b'href="#base"' in clean.data
