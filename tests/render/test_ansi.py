"""Markdown rendered from a stream of fragments, which is the hard part.

Pure, like everything under `render/`: fragments in, lines out, no process and no terminal. The
fragment sizes below are deliberately absurd — one and two characters — because a real delta
splits `**bo` from `ld**` and the failure only shows up at a boundary.
"""

from __future__ import annotations

from taskops.render.ansi import BOLD, BULLET, CODE, RESET, TITLE, Ink


def _rendered(markdown: str, *, colour: bool = True, size: int = 3) -> list[str]:
    """The markdown fed in `size`-character bites, as a real narration arrives."""
    ink = Ink(colour=colour)
    out: list[str] = []
    for i in range(0, len(markdown), size):
        out += ink.feed(markdown[i:i + size])
    return out + ink.flush()


def test_nothing_is_emitted_until_a_line_is_complete() -> None:
    """A delta is not a line. Styling a half-line emits an opening escape whose partner is
    still in the next fragment, and a `**` that never closes."""
    ink = Ink(colour=True)
    assert ink.feed("some prose that has ") == []
    assert ink.feed("not ended yet") == []
    assert ink.feed("\nand more") == ["some prose that has not ended yet"]


def test_bold_split_across_the_boundary_still_renders_once() -> None:
    assert _rendered("a **bold** word\n", size=2) == [f"a {BOLD}bold{RESET} word"]


def test_a_code_span_is_coloured() -> None:
    assert _rendered("run `taskops next`\n") == [f"run {CODE}taskops next{RESET}"]


def test_headings_get_the_titles_own_weight() -> None:
    """`#` is the narration's own title and gets bold+underline; everything deeper is a
    section inside it and gets plain bold."""
    assert _rendered("# The day\n## What closed\n") == [f"{TITLE}The day{RESET}",
                                                        f"{BOLD}What closed{RESET}"]


def test_a_bullet_uses_the_packages_own_glyph() -> None:
    """Borrowed from the board's register rather than invented here — two vocabularies for
    the same idea is how a terminal ends up with a different bullet per command."""
    assert _rendered("- one\n  * two\n") == [f"{BULLET} one", f"  {BULLET} two"]


def test_a_fence_suppresses_styling_until_it_closes() -> None:
    """`**` in a shell snippet is a glob and `#` is a comment, not a heading."""
    lines = _rendered("```sh\n# not a heading\nls **/*.py\n```\n**after**\n")
    assert lines == ["```sh", "# not a heading", "ls **/*.py", "```",
                     f"{BOLD}after{RESET}"]


def test_the_tail_is_flushed() -> None:
    """A last line with no trailing newline is still a line, and dropping it loses the final
    sentence of every narration that does not end in one."""
    ink = Ink(colour=False)
    ink.feed("the end, unterminated")
    assert ink.flush() == ["the end, unterminated"]
    assert ink.flush() == [], "and only once"


def test_without_colour_the_markdown_comes_back_byte_for_byte() -> None:
    """The plain path costs nothing: a pipe, a file or a CI log gets exactly what this command
    emitted before it ever streamed."""
    markdown = "# Title\n\n- a **bold** point with `code`\n\n```py\nx = 1\n```\ntail"
    assert "\n".join(_rendered(markdown, colour=False)) == markdown


def test_no_escape_survives_the_plain_path() -> None:
    for line in _rendered("# T\n- **b** `c`\n", colour=False):
        assert "\033" not in line
