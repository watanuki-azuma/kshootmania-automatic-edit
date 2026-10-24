from pathlib import Path

import pytest

pytest.importorskip("PIL")
from ksmauto.ksh import load_ksh  # noqa: E402
from ksmauto.render import render, render_pages  # noqa: E402

GRAM = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.ksh"


def test_pages_cover_whole_chart():
    pages = render_pages(load_ksh(GRAM))
    assert len(pages) >= 2
    assert all(p.width > 0 and p.height > 0 for p in pages)


def test_render_range_single_file(tmp_path):
    paths = render(load_ksh(GRAM), tmp_path / "gram.png", start=8, end=24)
    assert paths == [tmp_path / "gram.png"] and paths[0].exists()
