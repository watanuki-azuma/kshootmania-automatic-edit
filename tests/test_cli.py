from pathlib import Path

from ksmauto.cli import main
from ksmauto.kson import load_kson


GRAM = Path(__file__).parent / "fixtures" / "libkson" / "Gram_ex.ksh"


def test_convert_validate_info(tmp_path, capsys):
    output = tmp_path / "gram.kson"
    assert main(["convert", str(GRAM), "-o", str(output)]) == 0
    assert load_kson(output)["meta"]["title"] == "Gram"
    assert main(["validate", str(output), str(GRAM)]) == 0
    assert main(["info", str(output), str(GRAM)]) == 0
    text = capsys.readouterr().out
    assert "Gram / Blast Smith" in text and "Level: 16" in text
    assert "BPM: 191" in text and "Duration:" in text
    assert "Laser: 89 sections, 145 slams" in text


def test_default_convert_output(tmp_path):
    path = tmp_path / "chart.ksh"
    path.write_text("title=Test\nt=120\n--\n0000|00|--\n--\n")
    assert main(["convert", str(path)]) == 0
    assert path.with_suffix(".kson").exists()


def test_validate_errors_and_missing_file(tmp_path, capsys):
    path = tmp_path / "broken.kson"
    path.write_text('{"format_version":1}')
    assert main(["validate", str(path)]) == 1
    assert "error: $.meta" in capsys.readouterr().out
    assert main(["info", str(path)]) == 1
    assert main(["convert", str(tmp_path / "missing.ksh")]) == 1
    assert main(["validate", str(tmp_path / "missing.kson")]) == 1
