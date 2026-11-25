from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from civil_calc import BOQItem, analyze_boq, read_boq


SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "boq_sample.csv"


def test_sample_normalizes_six_trades_and_flags_two_rates():
    result = analyze_boq(read_boq(SAMPLE))
    assert len(result.lines) == 18
    assert {category.category for category in result.categories} == {
        "Concrete", "Rebar", "Formwork", "Earthworks", "Finishes", "MEP",
    }
    assert [(line.entry.source_row, line.entry.category) for line in result.anomalies] == [
        (9, "Concrete"), (12, "Rebar"),
    ]
    assert result.lines[0].entry.quantity == Decimal(1250)
    assert result.grand_total == sum(category.subtotal for category in result.categories)


def test_aggregation_rounds_lines_before_contingency_and_tax():
    items = [
        BOQItem("Concrete footing", "Concrete", "m³", Decimal("2.335"), Decimal("100.01"), 2),
        BOQItem("Concrete slab", "Concrete", "m³", Decimal(2), Decimal(110), 3),
        BOQItem("Foundation trench", "Earthworks", "m³", Decimal(3), Decimal(19), 4),
    ]
    result = analyze_boq(items, contingency_pct=Decimal(5), tax_pct=Decimal(8))
    assert [line.total for line in result.lines] == [Decimal("233.52"), Decimal("220"), Decimal("57")]
    assert [(c.category, c.items, c.subtotal) for c in result.categories] == [
        ("Concrete", 2, Decimal("453.52")), ("Earthworks", 1, Decimal("57")),
    ]
    assert result.subtotal == Decimal("510.52")
    assert result.contingency == Decimal("25.53")
    assert result.tax == Decimal("42.88")
    assert result.grand_total == Decimal("578.93")
    assert result.anomalies == ()


def test_anomaly_threshold_is_strictly_greater_than_25_percent():
    items = [
        BOQItem(str(rate), "Rebar", "kg", Decimal(1), Decimal(rate), i)
        for i, rate in enumerate(("74.99", "75", "100", "125", "125.01"), start=2)
    ]
    result = analyze_boq(items)
    assert [line.category_median for line in result.lines] == [Decimal(100)] * 5
    assert [line.entry.item for line in result.anomalies] == ["74.99", "125.01"]
    assert result.lines[1].rate_deviation == Decimal("-0.25")
    assert result.lines[3].rate_deviation == Decimal("0.25")


def test_zero_median_flags_nonzero_rates_and_leaves_deviation_blank():
    result = analyze_boq([
        BOQItem(str(rate), "Earthworks", "m³", Decimal(1), Decimal(rate), i)
        for i, rate in enumerate((0, 0, 10), start=2)
    ])
    assert [line.entry.unit_rate for line in result.anomalies] == [Decimal(10)]
    assert result.anomalies[0].rate_deviation is None


def test_csv_accepts_aliases_accounting_negatives_and_repeated_headers(tmp_path):
    path = tmp_path / "contractor.csv"
    header = "UOM, Unit Price (USD), Work Description, quantity, Trade"
    path.write_text(
        f"BOQ Export\n{header}\n"
        'm2,"($1,200.10)",Credit for omitted cladding,2,Facade\n'
        f"{header}\n"
        "ea,$2.50,Doorstop,.5,\n"
        ",,Grand Total,,\n",
        encoding="utf-8-sig",
    )
    credit, doorstop = read_boq(path)
    assert (credit.category, credit.unit_rate, credit.source_row) == ("Facade", Decimal("-1200.10"), 3)
    assert (doorstop.category, doorstop.quantity, doorstop.source_row) == ("Uncategorized", Decimal("0.5"), 5)


def test_excel_sheet_imports_numeric_cells_and_preserves_source_rows(tmp_path):
    workbook = Workbook()
    workbook.active.title = "Cover"
    worksheet = workbook.create_sheet("Pricing")
    worksheet.append(["Bill of quantities"])
    worksheet.append(["Description", "Work Section", "UOM", "Quantity", "Rate"])
    worksheet.append(["Retaining wall", "concrete works", "m³", 10.5, 121.25])
    path = tmp_path / "contractor.xlsx"
    workbook.save(path)
    (line,) = read_boq(path, sheet="Pricing")
    assert line == BOQItem("Retaining wall", "Concrete", "m³", Decimal("10.5"), Decimal("121.25"), 3)


def test_malformed_numeric_input_reports_row_and_field(tmp_path):
    path = tmp_path / "broken.csv"
    path.write_text('Item,Category,Unit,Qty,Rate\nGrading,Earthwork,m3,15,"12,50"\n')
    with pytest.raises(ValueError, match="Row 2, Unit Rate"):
        read_boq(path)


def test_unquoted_csv_thousands_separator_cannot_shift_the_rate(tmp_path):
    path = tmp_path / "unquoted.csv"
    path.write_text("Item,Category,Unit,Qty,Rate\nGrading,Earthwork,m3,1,250,15\n")
    with pytest.raises(ValueError, match="Row 2: extra fields"):
        read_boq(path)


@pytest.mark.parametrize("tax", [Decimal("-1"), Decimal("Infinity")])
def test_invalid_tax_percentages(tax):
    with pytest.raises(ValueError, match="Tax percentage"):
        analyze_boq(read_boq(SAMPLE), tax_pct=tax)
