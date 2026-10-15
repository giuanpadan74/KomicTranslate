"""Parita RS vs Python per hyphen wrap (non-regression)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import random
import komic_core_rs as rs
from modules.rendering.hyphen_textwrap import TextWrapper as PyTW


def _py_wrap(text, width, **kw):
    return PyTW(width=width, **kw).wrap(text)


def test_wrap_matches_python_simple_path():
    rng = random.Random(99)
    words = ['ciao', 'mondo', 'fumetto', 'supercalifragilistico', 'a',
             'testo-con-trattini', 'virgola,', 'tab\there', 'x' * 40]
    for _ in range(30):
        t = ' '.join(rng.choice(words) for _ in range(rng.randint(1, 20)))
        for width in (5, 10, 20, 30):
            assert _py_wrap(t, width, break_on_hyphens=False,
                            break_long_words=False) == rs.hyphen_wrap_rs(
                t, width, break_on_hyphens=False, break_long_words=False)


def test_wrap_matches_python_options():
    t = 'Hello world foo bar baz qux quux corge grault garply'
    opt_sets = [
        dict(break_long_words=True),
        dict(initial_indent='> ', subsequent_indent='  '),
        dict(max_lines=2),
        dict(fix_sentence_endings=True),
        dict(drop_whitespace=False),
    ]
    for opts in opt_sets:
        assert _py_wrap(t, 12, break_on_hyphens=False, **opts) == \
            rs.hyphen_wrap_rs(t, 12, break_on_hyphens=False, **opts)


def test_render_columns_sweep_matches():
    t = 'Non hai alcun diritto su questa ragazza, Barok. So che la difendi.'
    kw = dict(break_on_hyphens=False, break_long_words=False,
              hyphenate_broken_words=True)
    for c in range(1, len(t)):
        assert _py_wrap(t, c, **kw) == rs.hyphen_wrap_rs(t, c, **kw)
