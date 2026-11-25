"""Write styled Excel reports with native, cell-linked charts."""

from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import wrap

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.data_source import AxDataSource, StrRef
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .beam import BeamResult, BeamStation
from .boq import BOQLine, BOQResult


NAVY = "183047"
SLATE = "4A6377"
BLUE = "276A96"
TEAL = "127A74"
PALE_BLUE = "EFF5F9"
AMBER = "FCEAC8"
OCHRE = "71430C"
RULE = "CBDAE5"
WHITE = "FFFFFF"
FONT = "Arial"
DECIMALS = "#,##0.00;[Red](#,##0.00)"
DETAIL = "#,##0.0000;[Red](#,##0.0000)"
RATE = "#,##0.00####;[Red](#,##0.00####)"
PERCENT = "0.0##%"
DEVIATION = "+0.0##%;-0.0##%;0.0%"
HEADER_ROW = 5
DATA_ROW = HEADER_ROW + 1

type CellValue = str | float | int | Decimal | None


def _table(
    ws: Worksheet,
    title: str,
    context: str,
    headers: tuple[str, ...],
    widths: tuple[int, ...],
    rows: Iterable[tuple[CellValue, ...]],
    *,
    formats: dict[int, str] | None = None,
    filtered: bool = False,
    wrap_column: int | None = None,
) -> None:
    ws.sheet_view.showGridLines = False
    ws.sheet_format.defaultRowHeight = 18
    ws.row_dimensions[1].height = 9
    ws.row_dimensions[2].height = 26
    ws.row_dimensions[3].height = 19
    ws.row_dimensions[4].height = 8
    ws.row_dimensions[HEADER_ROW].height = 23
    ws["A2"] = title
    ws["A2"].font = Font(name=FONT, size=16, bold=True, color=NAVY)
    ws["A3"] = context
    ws["A3"].font = Font(name=FONT, size=10, italic=True, color=SLATE)

    for index, (header, width) in enumerate(zip(headers, widths, strict=True), start=1):
        ws.column_dimensions[get_column_letter(index)].width = width
        ws.cell(2, index).border = Border(bottom=Side(style="thin", color=RULE))
        cell = ws.cell(HEADER_ROW, index, header)
        cell.font = Font(name=FONT, size=10, bold=True, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.border = Border(right=Side(style="thin", color=WHITE))
        cell.alignment = Alignment(horizontal="center", vertical="center")

    data_formats = formats or {}
    for row_number, values in enumerate(rows, start=DATA_ROW):
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row_number, col, value)
            if isinstance(value, str):
                cell.data_type = "s"
            cell.font = Font(name=FONT, size=10, color=NAVY)
            if row_number % 2 == 0:
                cell.fill = PatternFill("solid", fgColor=PALE_BLUE)
            cell.alignment = Alignment(
                horizontal="left" if isinstance(value, str) else "right",
                vertical="center",
                indent=1,
                wrap_text=col == wrap_column,
            )
            if col in data_formats:
                cell.number_format = data_formats[col]
        if wrap_column is not None and len(values) >= wrap_column:
            line_count = len(wrap(str(values[wrap_column - 1]), widths[wrap_column - 1] - 6))
            if line_count > 1:
                ws.row_dimensions[row_number].height = min(408, 14 * line_count + 4)

    if filtered:
        ws.freeze_panes = f"A{DATA_ROW}"
        if ws.max_row >= DATA_ROW:
            ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(headers))}{ws.max_row}"

    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = f"1:{HEADER_ROW}"
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.25
    ws.page_margins.top = ws.page_margins.bottom = 0.35


def _highlight(ws: Worksheet, row: int, *, alert: bool = False) -> None:
    for cell in ws[row]:
        cell.font = Font(name=FONT, size=10, bold=True, color=OCHRE if alert else NAVY)
        cell.fill = PatternFill("solid", fgColor=AMBER if alert else "D7EAE8")


def _summary_layout(ws: Worksheet, last_row: int) -> None:
    ws.sheet_properties.tabColor = NAVY
    ws.column_dimensions["D"].width = 3
    for col in "EFGHIJKLM":
        ws.column_dimensions[col].width = 10
    ws.print_area = f"A1:M{last_row}"
    ws.page_setup.fitToHeight = 1


def _save(workbook: Workbook, output: str | Path) -> Path:
    path = Path(output)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Report output must have an .xlsx extension.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".civil-calc-", dir=path.parent) as folder:
        temporary = Path(folder) / "report.xlsx"
        workbook.save(temporary)
        temporary.replace(path)
    return path


def _location(station: BeamStation) -> str:
    location = f"{station.x:.6g} m"
    return f"{location} ({station.side.lower()})" if station.side else location


def write_beam_report(result: BeamResult, output: str | Path) -> Path:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Executive Summary"
    loads = workbook.create_sheet("Applied Loads")
    diagram = workbook.create_sheet("Diagram Data")

    metrics: list[tuple[CellValue, ...]] = [
        ("Span (m)", result.length, None),
        ("Left reaction, Rₐ (kN)", result.reaction_a, None),
        ("Right reaction, Rᵦ (kN)", result.reaction_b, None),
        ("Governing shear, V (kN)", result.max_shear.shear, _location(result.max_shear)),
        ("Governing bending, M (kN·m)", result.max_moment.moment, _location(result.max_moment)),
    ]
    utilization_rows: list[tuple[int, float]] = []
    for label, unit, limit, utilization in (
        ("Shear", "kN", result.capacity.shear, result.shear_utilization),
        ("Bending", "kN·m", result.capacity.moment, result.moment_utilization),
    ):
        if utilization is not None:
            metrics.extend([
                (f"{label} capacity ({unit})", limit, None),
                (f"{label} utilization", utilization, None),
            ])
            utilization_rows.append((HEADER_ROW + len(metrics), utilization))

    _table(
        summary, "Simply Supported Beam", "Governing values are selected by magnitude.",
        ("Metric", "Value", "Peak location"), (36, 16, 22), metrics,
        formats={2: DECIMALS},
    )
    for row in (DATA_ROW + 3, DATA_ROW + 4):
        _highlight(summary, row)
    for row, utilization in utilization_rows:
        summary.cell(row, 2).number_format = PERCENT
        if utilization > 1:
            _highlight(summary, row, alert=True)

    load_rows = [
        *(("Point load", p.force, "kN", p.position, None) for p in result.point_loads),
        *(("Uniform load", w.intensity, "kN/m", w.start, w.end) for w in result.udls),
        *(("Applied moment", m.moment, "kN·m", m.position, None) for m in result.moments),
    ]
    _table(
        loads, "Applied Loads", "Positive forces act downward. Positive couples act counterclockwise.",
        ("Load type", "Magnitude", "Unit", "Start / position (m)", "End (m)"),
        (23, 17, 13, 24, 17),
        load_rows or [("No applied loads", None, None, None, None)],
        formats={2: DETAIL, 4: DETAIL, 5: DETAIL}, filtered=bool(load_rows),
    )
    _table(
        diagram, "Diagram Data", "The left and right limits show jumps. Positive moment is sagging.",
        ("Distance (m)", "Limit", "Shear (kN)", "Bending (kN·m)"), (18, 14, 19, 21),
        ((s.x, s.side, s.shear, s.moment) for s in result.stations),
        formats={1: DETAIL, 3: DETAIL, 4: DETAIL}, filtered=True,
    )
    for col, title in enumerate(("Distance (m)", "Shear (kN)", "Bending (kN·m)"), start=6):
        diagram.cell(HEADER_ROW, col, title)
    for row, station in enumerate(result.chart_stations, start=DATA_ROW):
        diagram.cell(row, 6, station.x).number_format = "0.###"
        diagram.cell(row, 7, station.shear)
        diagram.cell(row, 8, station.moment)
    diagram.column_dimensions.group("F", "H", hidden=True)
    last = HEADER_ROW + len(result.chart_stations)
    distance = Reference(diagram, min_col=6, min_row=DATA_ROW, max_row=last)

    for title, units, column, color, anchor in (
        ("Shear Force Diagram", "V (kN)", 7, BLUE, "E2"),
        ("Bending Moment Diagram", "M (kN·m)", 8, TEAL, "E17"),
    ):
        chart = LineChart()
        chart.title = title
        chart.x_axis.title = "Distance from left support (m)"
        chart.x_axis.tickLblPos = "low"
        chart.x_axis.tickLblSkip = max(1, (len(result.chart_stations) - 1) // 5)
        chart.x_axis.tickMarkSkip = chart.x_axis.tickLblSkip
        chart.y_axis.title = units
        chart.y_axis.numFmt = "0.##"
        chart.y_axis.crossBetween = "midCat"
        chart.legend = None
        chart.smooth = False
        chart.height, chart.width = 8, 16.5
        chart.visible_cells_only = False
        chart.add_data(
            Reference(diagram, min_col=column, min_row=HEADER_ROW, max_row=last),
            titles_from_data=True,
        )
        chart.set_categories(distance)
        chart.series[0].smooth = False
        chart.series[0].graphicalProperties.line.solidFill = color
        chart.series[0].graphicalProperties.line.width = 25400
        summary.add_chart(chart, anchor)

    _summary_layout(summary, 30)
    return _save(workbook, output)


def _audit_row(line: BOQLine) -> tuple[CellValue, ...]:
    entry = line.entry
    return (
        entry.source_row, entry.item, entry.category, entry.unit,
        entry.unit_rate, line.category_median, line.rate_deviation,
    )


def write_boq_report(result: BOQResult, output: str | Path) -> Path:
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Executive Summary"
    categories = workbook.create_sheet("Category Breakdown")
    anomalies = workbook.create_sheet("Flagged Anomalies")
    clean = workbook.create_sheet("Clean BOQ Data")

    metrics = [
        ("BOQ lines", len(result.lines), None),
        ("Flagged unit rates", len(result.anomalies), None),
        ("Base subtotal", result.subtotal, None),
        ("Contingency", result.contingency, result.contingency_pct / 100),
        ("Tax on subtotal + contingency", result.tax, result.tax_pct / 100),
        ("Grand total", result.grand_total, None),
    ]
    _table(
        summary, "Bill of Quantities", "Amounts use the source currency.",
        ("Metric", "Value", "Rate"), (36, 17, 15), metrics, formats={3: PERCENT},
    )
    for row in range(DATA_ROW + 2, DATA_ROW + len(metrics)):
        summary.cell(row, 2).number_format = DECIMALS
    _highlight(summary, DATA_ROW + len(metrics) - 1)
    if result.anomalies:
        _highlight(summary, DATA_ROW + 1, alert=True)

    _table(
        categories, "Cost by Category", "Subtotals before contingency and tax.",
        ("Category", "BOQ lines", "Subtotal"), (31, 17, 20),
        ((c.category, c.items, c.subtotal) for c in result.categories),
        formats={3: DECIMALS}, filtered=True,
    )
    _table(
        anomalies, "Flagged Unit Rates", "Flags indicate a deviation of more than 25% from the category median.",
        ("Source row", "Item", "Category", "Unit", "Unit rate", "Category median", "Deviation"),
        (14, 49, 23, 12, 17, 21, 17),
        [_audit_row(line) for line in result.anomalies]
        or [(None, "No unit rates flagged.", None, None, None, None, None)],
        formats={5: RATE, 6: RATE, 7: DEVIATION}, filtered=bool(result.anomalies), wrap_column=2,
    )
    for row in range(DATA_ROW, DATA_ROW + len(result.anomalies)):
        _highlight(anomalies, row, alert=True)

    _table(
        clean, "Clean BOQ Data", "Source row identifies each line in the input file.",
        ("Source row", "Item", "Category", "Unit", "Qty", "Unit rate", "Line total", "Rate flag"),
        (14, 49, 23, 12, 16, 17, 19, 14),
        (
            (e.source_row, e.item, e.category, e.unit, e.quantity, e.unit_rate, line.total,
             "Review" if line.flagged else None)
            for line in result.lines for e in (line.entry,)
        ),
        formats={5: RATE, 6: RATE, 7: DECIMALS}, filtered=True, wrap_column=2,
    )

    chart = BarChart()
    chart.type = "bar"
    chart.title = "Subtotal by Category"
    chart.y_axis.title = "Cost (source currency)"
    chart.y_axis.numFmt = "#,##0"
    chart.y_axis.crosses = "max"
    chart.x_axis.scaling.orientation = "maxMin"
    chart.x_axis.tickLblPos = "low"
    chart.legend = None
    chart.height = max(8, 3 + 0.62 * len(result.categories))
    chart.width = 16.5
    last = HEADER_ROW + len(result.categories)
    chart.add_data(
        Reference(categories, min_col=3, min_row=HEADER_ROW, max_row=last),
        titles_from_data=True,
    )
    labels = Reference(categories, min_col=1, min_row=DATA_ROW, max_row=last)
    chart.series[0].cat = AxDataSource(strRef=StrRef(f=str(labels)))
    chart.series[0].graphicalProperties.solidFill = TEAL
    chart.series[0].graphicalProperties.line.noFill = True
    summary.add_chart(chart, "E2")
    _summary_layout(summary, max(15, 3 + int(chart.height * 28.35 / 18)))
    return _save(workbook, output)
