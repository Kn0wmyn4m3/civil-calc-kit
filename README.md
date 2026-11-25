# CivilCalc Kit

CivilCalc Kit automates two recurring jobs for structural engineering and quantity surveying teams. Calculate reactions and internal forces for a simply supported beam, or turn a contractor’s bill of quantities into a cost summary with unit rates flagged for review. Each command produces a formatted Excel report with native charts and supporting data.

## Get started

From the project root, use Python 3.13 and install the dependencies.

```bash
python3 -m pip install -r requirements.txt
```

### Analyze a beam

```bash
python3 -m civil_calc beam --length 6.0 --udl 12.0 --point-load 20.0@2.5 --output examples/beam_report.xlsx
```

Repeat load options to combine multiple loads. Use `--point-load P@X` for a point force, `--udl W` for a full-span uniform load, `--udl W@START:END` for a partial uniform load, and `--moment M@X` for a concentrated couple. Dimensions use m, kN, kN/m, and kN·m. Forces are positive downward, couples are positive counterclockwise, reactions are positive upward, and bending is positive in sagging. Attach signed values to the option with `=`, for example `--moment=-15@3.2`.

The [beam report](examples/beam_report.xlsx) includes support reactions, signed governing shear and moment with their locations, applied loads, and shear and bending diagrams. The solver checks the limits on both sides of discontinuities and interior stations where shear is zero. The Excel line charts use an evenly spaced grid for a proportional distance axis, so a jump appears between adjacent samples. The **Diagram Data** sheet records both exact limits at the load station. Set `--samples` to change the chart resolution.

Supply `--shear-capacity` in kN or `--moment-capacity` in kN·m to compare the governing demand magnitude with your available capacity.

### Audit a bill of quantities

```bash
python3 -m civil_calc boq --input sample_data/boq_sample.csv --output examples/boq_summary.xlsx
```

Use a UTF-8 comma-delimited CSV or an Excel `.xlsx` or `.xlsm` file. The importer looks for an Item, Category, Unit, Qty, and Unit Rate header row, with aliases such as Description, Trade, UOM, Quantity, and Unit Price. It handles title rows, blanks, repeated headers, common total rows, and trades such as shuttering and reinforcement. Quote CSV numbers that contain commas and use a decimal point. Excel imports the first worksheet by default. Use `--sheet "Trade Detail"` to select another.

The [BOQ report](examples/boq_summary.xlsx) contains an executive summary, category subtotals, flagged rates, and clean data with source row references. Line totals round to two decimal places before rollup. Set `--contingency 5 --tax 8` to add 5% contingency to the base subtotal and apply 8% tax to the subtotal plus contingency. Both rates default to zero.

An item is flagged when the absolute difference from its category median exceeds 25% of the median’s magnitude. A zero median flags nonzero rates and leaves percentage deviation blank. Check that items use comparable units and scopes when interpreting flags. The sample contains 18 items across six trades, with two deliberately unusual rates. Regenerate it with `python3 scripts/generate_sample_boq.py`.

## Analytical verification

```bash
python3 -m pytest -q
```

The tests compare the beam solver with the textbook peaks `PL/4` for a central point load and `wL²/8` for a full-span uniform load. They also check force and moment equilibrium for combined loads, partial UDLs, concentrated-moment jumps, BOQ arithmetic and anomaly thresholds, and the sheets and charts produced by both CLI commands. [University of Illinois Shi Lab beam cases](https://www.shitaoshi.web.illinois.edu/resources/tools/01-simple-beams.html) · [MIT OpenCourseWare bending statics](https://ocw.mit.edu/courses/3-11-mechanics-of-materials-fall-1999/b8e832b3c8bf3c1700c26425a4baddb1_MIT3_11F99_statics.pdf)

## Project structure

| Path | Purpose |
| --- | --- |
| `civil_calc/beam.py` | Reactions, internal forces, peak locations, and utilization |
| `civil_calc/boq.py` | Input cleaning, category normalization, and cost audit |
| `civil_calc/reporter.py` | Styled Excel exports and native charts |
| `civil_calc/cli.py` | Beam and BOQ command-line arguments |
| `scripts/` and `sample_data/` | Repeatable contractor BOQ input |
| `examples/` | Generated Excel reports |
| `tests/` | Analytical, import, and report verification |
| `portfolio.meta.json` | Portfolio integration metadata |

## Contact

For structural calculation automation or BOQ reporting work, contact me at [ytxy0114@gmail.com](mailto:ytxy0114@gmail.com) or on GitHub [Kn0wmyn4m3](https://github.com/Kn0wmyn4m3).
