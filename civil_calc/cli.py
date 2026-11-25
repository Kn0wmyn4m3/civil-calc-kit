"""Command-line entry points for beam and BOQ reporting."""

import argparse
import csv
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile

from .beam import AppliedMoment, PointLoad, SectionCapacity, UniformLoad, analyze_beam
from .boq import analyze_boq, read_boq
from .reporter import write_beam_report, write_boq_report


def _positioned(value: str, label: str) -> tuple[float, float]:
    try:
        magnitude, position = value.split("@")
        return float(magnitude), float(position)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Use {label}@POSITION.") from exc


def _point_load(value: str) -> PointLoad:
    return PointLoad(*_positioned(value, "P"))


def _moment(value: str) -> AppliedMoment:
    return AppliedMoment(*_positioned(value, "M"))


def _udl(value: str) -> UniformLoad:
    try:
        intensity, separator, interval = value.partition("@")
        if separator:
            start, end = interval.split(":")
            return UniformLoad(float(intensity), float(start), float(end))
        return UniformLoad(float(intensity))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use W or W@START:END.") from exc


def _percentage(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("Enter a numeric percentage, such as 5.") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m civil_calc", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    beam = commands.add_parser("beam", help="Analyze a simply supported beam.")
    beam.add_argument("--length", type=float, required=True, help="Span in m.")
    beam.add_argument(
        "--udl", type=_udl, action="append", default=[], metavar="W[@START:END]",
        help="Distributed load in kN/m, with an optional span interval. Repeatable.",
    )
    beam.add_argument(
        "--point-load", type=_point_load, action="append", default=[], metavar="P@X",
        help="Point force in kN and position in m. Repeatable.",
    )
    beam.add_argument(
        "--moment", type=_moment, action="append", default=[], metavar="M@X",
        help="Counterclockwise applied moment in kN·m and position in m. Repeatable.",
    )
    beam.add_argument("--samples", type=int, default=101, help="Plot points across the span (default 101).")
    beam.add_argument("--shear-capacity", type=float, help="Available shear capacity in kN.")
    beam.add_argument("--moment-capacity", type=float, help="Available bending capacity in kN·m.")
    beam.add_argument("--output", type=Path, required=True, help="Destination .xlsx report.")

    boq = commands.add_parser("boq", help="Audit a contractor bill of quantities.")
    boq.add_argument("--input", type=Path, required=True, help="Source CSV or Excel file.")
    boq.add_argument("--sheet", help="Excel worksheet name (defaults to first sheet).")
    boq.add_argument("--contingency", type=_percentage, default="0", help="Contingency percentage.")
    boq.add_argument("--tax", type=_percentage, default="0", help="Tax percentage after contingency.")
    boq.add_argument("--output", type=Path, required=True, help="Destination .xlsx report.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "beam":
            result = analyze_beam(
                args.length, point_loads=args.point_load, udls=args.udl, moments=args.moment,
                samples=args.samples, capacity=SectionCapacity(args.shear_capacity, args.moment_capacity),
            )
            output = write_beam_report(result, args.output)
        else:
            if args.input.resolve() == args.output.resolve() or (
                args.input.exists() and args.output.exists() and args.input.samefile(args.output)
            ):
                raise ValueError("Choose a report path separate from the input BOQ.")
            audit = analyze_boq(
                read_boq(args.input, sheet=args.sheet),
                contingency_pct=args.contingency, tax_pct=args.tax,
            )
            output = write_boq_report(audit, args.output)
    except (ArithmeticError, BadZipFile, csv.Error, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Saved {output}")
    return 0
