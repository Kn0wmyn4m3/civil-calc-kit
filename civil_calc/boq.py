"""Import contractor quantities and audit category rates and costs."""

import csv
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from statistics import median

import pandas as pd


HEADER_ALIASES = {
    "Item": ("item", "itemdescription", "description", "workdescription", "particulars"),
    "Category": ("category", "tradecategory", "trade", "workcategory", "worksection", "division"),
    "Unit": ("unit", "uom", "unitofmeasure", "measure"),
    "Qty": ("qty", "quantity", "estimatedquantity", "takeoffquantity"),
    "Unit Rate": ("unitrate", "rate", "unitprice", "priceperunit", "unitcost"),
}
CATEGORY_ALIASES = {
    "Concrete": ("concreteworks", "concretework", "castinplaceconcrete"),
    "Rebar": ("reinforcement", "reinforcingsteel", "steelreinforcement", "rebarworks", "rebarsteel"),
    "Formwork": ("formworkworks", "shuttering", "forms", "concreteforms"),
    "Earthworks": ("earthwork", "earthworksandgrading", "excavation", "sitegrading"),
    "Finishes": ("finish", "finishing", "architecturalfinishes", "interiorfinishes"),
    "MEP": ("mepservices", "buildingservices", "mechanical", "electrical", "plumbing"),
    "Masonry": ("masonryworks", "blockwork", "brickwork"),
    "Structural Steel": ("structuralsteelwork", "structuralsteelworks", "steelwork"),
    "Waterproofing": ("waterproofingworks", "dampproofing"),
}
TOTAL_LABELS = {"total", "subtotal", "grandtotal", "totalcarriedforward", "carriedforward"}
DECIMAL_NUMBER = re.compile(
    r"[+-]?(?:\d{1,3}(?:,\d{3})+(?:\.\d*)?|\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
)
CENT = Decimal("0.01")
ZERO = Decimal("0")
ANOMALY_THRESHOLD = Decimal("0.25")


@dataclass(frozen=True, slots=True)
class BOQItem:
    item: str
    category: str
    unit: str
    quantity: Decimal
    unit_rate: Decimal
    source_row: int


@dataclass(frozen=True, slots=True)
class BOQLine:
    entry: BOQItem
    total: Decimal
    category_median: Decimal
    rate_deviation: Decimal | None
    flagged: bool


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    category: str
    items: int
    subtotal: Decimal


@dataclass(frozen=True, slots=True)
class BOQResult:
    lines: tuple[BOQLine, ...]
    categories: tuple[CategoryTotal, ...]
    subtotal: Decimal
    contingency_pct: Decimal
    contingency: Decimal
    tax_pct: Decimal
    tax: Decimal
    grand_total: Decimal

    @property
    def anomalies(self) -> tuple[BOQLine, ...]:
        return tuple(line for line in self.lines if line.flagged)


def _text(value: object) -> str:
    return "" if value is None else " ".join(str(value).split())


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


CANONICAL_CATEGORIES = {
    alias: category
    for category, aliases in CATEGORY_ALIASES.items()
    for alias in (_key(category), *aliases)
}


def _header_key(value: str) -> str:
    return _key(re.sub(r"\s*\([A-Z]{3}\)\s*$", "", value, flags=re.IGNORECASE))


def _number(value: str, field: str, row: int) -> Decimal:
    number = value.replace("−", "-")
    if number.startswith("(") and number.endswith(")"):
        number = "-" + number[1:-1].strip()
    number = re.sub(r"^([+-]?)\s*[$€£¥]\s*", r"\1", number)
    if not DECIMAL_NUMBER.fullmatch(number):
        raise ValueError(f"Row {row}, {field}: expected a number, got {value!r}.")
    return Decimal(number.replace(",", ""))


def _items(rows: Iterable[tuple[int, Sequence[object]]]) -> tuple[BOQItem, ...]:
    rows = iter(rows)
    for row_number, row in rows:
        keys = [_header_key(_text(value)) for value in row]
        selected = [
            next((alias for alias in aliases if alias in keys), None)
            for aliases in HEADER_ALIASES.values()
        ]
        if None not in selected:
            if any(keys.count(alias) > 1 for alias in selected):
                raise ValueError(f"Row {row_number}: duplicate BOQ column names.")
            indexes = [keys.index(alias) for alias in selected]
            header_width = len(keys)
            break
    else:
        raise ValueError("No header row found with Item, Category, Unit, Qty and Unit Rate.")

    items: list[BOQItem] = []
    for row_number, row in rows:
        if any(_text(value) for value in row[header_width:]):
            raise ValueError(f"Row {row_number}: extra fields beyond the BOQ header. Check CSV quoting.")
        cells = [_text(row[index]) if index < len(row) else "" for index in indexes]
        item, category, unit, quantity, rate = cells
        if not any(cells) or [_header_key(value) for value in cells] == selected:
            continue
        if not unit and not quantity and _key(item) in TOTAL_LABELS:
            continue
        if not item or not unit:
            raise ValueError(f"Row {row_number}: Item and Unit are required.")
        items.append(
            BOQItem(
                item=item,
                category=CANONICAL_CATEGORIES.get(_key(category), category.title() or "Uncategorized"),
                unit=unit,
                quantity=_number(quantity, "Qty", row_number),
                unit_rate=_number(rate, "Unit Rate", row_number),
                source_row=row_number,
            )
        )
    if not items:
        raise ValueError("The BOQ contains no item rows.")
    return tuple(items)


def read_boq(path: str | Path, *, sheet: str | None = None) -> tuple[BOQItem, ...]:
    """Read a comma-delimited UTF-8 CSV or one Excel worksheet."""
    path = Path(path)
    if path.suffix.lower() == ".csv":
        if sheet is not None:
            raise ValueError("--sheet applies to Excel inputs.")
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)

            def rows() -> Iterable[tuple[int, Sequence[object]]]:
                while True:
                    start = reader.line_num + 1
                    try:
                        row = next(reader)
                    except StopIteration:
                        return
                    yield start, row

            return _items(rows())
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        data = pd.read_excel(
            path, sheet_name=sheet if sheet is not None else 0, header=None,
            dtype=object, keep_default_na=False, engine="openpyxl",
        )
        return _items(enumerate(data.itertuples(index=False, name=None), start=1))
    raise ValueError("Unsupported BOQ input format. Use .csv, .xlsx or .xlsm.")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def analyze_boq(
    items: Iterable[BOQItem],
    *,
    contingency_pct: Decimal = ZERO,
    tax_pct: Decimal = ZERO,
) -> BOQResult:
    """Price each item and compare its rate with the median of its category."""
    for name, value in (("Contingency", contingency_pct), ("Tax", tax_pct)):
        if not value.is_finite() or value < ZERO:
            raise ValueError(f"{name} percentage must be finite and nonnegative.")
    items = tuple(items)
    if not items:
        raise ValueError("The BOQ contains no item rows.")

    rates: dict[str, list[Decimal]] = defaultdict(list)
    for entry in items:
        rates[entry.category].append(entry.unit_rate)
    medians = {category: median(values) for category, values in rates.items()}

    lines: list[BOQLine] = []
    subtotals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for entry in items:
        baseline = medians[entry.category]
        difference = entry.unit_rate - baseline
        total = _money(entry.quantity * entry.unit_rate)
        lines.append(
            BOQLine(
                entry=entry,
                total=total,
                category_median=baseline,
                rate_deviation=difference / abs(baseline) if baseline else None,
                flagged=abs(difference) > abs(baseline) * ANOMALY_THRESHOLD,
            )
        )
        subtotals[entry.category] += total

    categories = tuple(
        CategoryTotal(category, len(rates[category]), total)
        for category, total in sorted(subtotals.items(), key=lambda pair: (-pair[1], pair[0]))
    )
    subtotal = sum(subtotals.values(), ZERO)
    contingency = _money(subtotal * contingency_pct / 100)
    tax = _money((subtotal + contingency) * tax_pct / 100)
    return BOQResult(
        lines=tuple(lines),
        categories=categories,
        subtotal=subtotal,
        contingency_pct=contingency_pct,
        contingency=contingency,
        tax_pct=tax_pct,
        tax=tax,
        grand_total=subtotal + contingency + tax,
    )
