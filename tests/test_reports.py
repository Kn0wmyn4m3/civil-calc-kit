import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook
from openpyxl.chart import BarChart, LineChart


PROJECT = Path(__file__).resolve().parents[1]


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "civil_calc", *map(str, arguments)],
        cwd=PROJECT, capture_output=True, text=True,
    )


def test_beam_report_cli_exports_two_native_line_charts(tmp_path):
    output = tmp_path / "beam.xlsx"
    completed = run_cli(
        "beam", "--length", "6", "--udl", "12", "--udl", "3@1:4",
        "--point-load", "20@2.5", "--moment=-15@4", "--moment-capacity", "70",
        "--output", output,
    )
    assert completed.returncode == 0, completed.stderr
    report = load_workbook(output)
    assert report.sheetnames == ["Executive Summary", "Applied Loads", "Diagram Data"]
    summary = report["Executive Summary"]
    shear, bending = summary._charts
    for chart, value_column in ((shear, "G"), (bending, "H")):
        assert isinstance(chart, LineChart)
        assert chart.series[0].val.numRef.f == f"'Diagram Data'!${value_column}$6:${value_column}$106"
        assert chart.series[0].cat.numRef.f == "'Diagram Data'!$F$6:$F$106"
        assert chart.visible_cells_only is False
        assert chart.series[0].smooth is False
    assert summary["B7"].value + summary["B8"].value == pytest.approx(101)
    assert summary["B12"].value == pytest.approx(abs(summary["B10"].value) / 70)
    assert report["Applied Loads"].max_row == 9
    report.close()


def test_boq_report_cli_exports_category_chart_and_flags(tmp_path):
    output = tmp_path / "boq.xlsx"
    completed = run_cli(
        "boq", "--input", PROJECT / "sample_data" / "boq_sample.csv",
        "--contingency", "5", "--tax", "8", "--output", output,
    )
    assert completed.returncode == 0, completed.stderr
    report = load_workbook(output)
    assert report.sheetnames == [
        "Executive Summary", "Category Breakdown", "Flagged Anomalies", "Clean BOQ Data",
    ]
    summary = report["Executive Summary"]
    (chart,) = summary._charts
    assert isinstance(chart, BarChart)
    assert chart.series[0].cat.strRef.f == "'Category Breakdown'!$A$6:$A$11"
    assert chart.series[0].val.numRef.f == "'Category Breakdown'!$C$6:$C$11"
    assert summary["B7"].value == 2
    assert summary["B11"].value == pytest.approx(sum(summary[f"B{row}"].value for row in (8, 9, 10)))
    assert report["Flagged Anomalies"].max_row == 7
    assert report["Clean BOQ Data"].max_row == 23
    report.close()


def test_cli_rejects_malformed_span_load(tmp_path):
    output = tmp_path / "beam.xlsx"
    completed = run_cli("beam", "--length", "6", "--udl", "12@1", "--output", output)
    assert completed.returncode == 2
    assert "Use W or W@START:END" in completed.stderr
    assert not output.exists()
