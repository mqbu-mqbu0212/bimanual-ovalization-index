# bimanual-ellipticity-index — OI Calculator for Bimanual Coordination Research
[日本語版はこちら](README_ja.md)

A Python pipeline for computing the Ellipticity Index (OI) from bimanual coordination task data recorded on a pen tablet.

## Background

In bimanual coordination research, participants are asked to simultaneously draw an ellipse with one hand and a straight line with the other. The degree of coordination between the two hands is quantified by how circular the "ellipse" hand's trajectory becomes — a phenomenon known as the **bimanual coupling effect**.

The standard metric for this is the **Ellipticity Index (OI = sd_minor / sd_major)**, where a higher value (closer to 1.0) indicates a more circular trajectory and stronger coupling.

### Motivation

Despite OI being a widely used metric, **no standardised method exists for computing it**. Most published studies measure only the straight-line trajectory (because the coupling effect is more visible there), and those that do compute OI tend to use inconsistent approaches. This makes cross-study comparison difficult.

During my own research on how the sense of body ownership (manipulated via VR) affects bimanual coordination, I found that:

- The existing OI computation code I had written was fragmented, inconsistently configured, and partially manual
- Rotation correction was applied by forcibly converting landscape-oriented ellipses to portrait orientation — an approach that is inherently arbitrary
- Analysis of the **ellipse hand** is just as important as the straight-line hand for understanding the full picture of bimanual coupling, and arguably more relevant when studying coordination quality

This tool is a ground-up rewrite that addresses those issues. It is released publicly with the hope that it helps **standardise OI computation across the field**, making results more comparable between studies and supporting further development of bimanual coordination research — including HCI applications involving body ownership, haptics, and motor control.

## Method

OI is computed via **PCA** on each detected cycle's trajectory:

- `sd_major` = standard deviation along the first principal component
- `sd_minor` = standard deviation along the second principal component
- `OI = sd_minor / sd_major`

PCA is rotation-invariant, so no axis-alignment correction is needed. For near-circular cycles (flatness ≥ 0.85), axis ambiguity is resolved by computing the midpoint of the start and end points, then determining which principal axis it aligns with more closely.

Cycles are automatically detected, quality-filtered (ellipse fitting residual, closure check), and aggregated per participant per condition.

## Installation

```bash
pip install -r requirements.txt
```

Dependencies: `numpy`, `pandas`, `matplotlib`, `scipy`, `lmfit`, `openpyxl`

## Usage

```bash
python main.py --input <input_path> --output <output_dir>
```

- `input_path`: path to a single CSV file, or a folder of CSV files
- `output_dir`: directory where all output folders and files will be created

### Input format

CSV files with 3 columns: `time, y, x` (no header). `START`/`END` marker rows are automatically removed. Missing samples (pen-off, recorded as `0,0`) are handled via interpolation.

Filename format: `<subject_id>_<condition>.csv` (e.g. `A_CDL.csv`)

### Output

```
output/
├── 02_cycles/       per-cycle plots
├── 03_filtered/     kept / removed / before_trim subfolders
├── 04_results/      OI_results.xlsx, cycle_log.csv, error_log.txt
├── 05_all_removed/  all removed cycles in one flat folder
├── 06_all_trimmed/  before/after trim pairs
└── 07_all_cycles/   all cycles in one flat folder
```

`OI_results.xlsx` contains two sheets: `OI` (mean OI per subject × condition) and `valid_cycles` (number of valid cycles used).

## Parameters

Key parameters in `main.py`. Values below are defaults tuned for a 24-subject dataset; recalibrate for your own data.

| Parameter | Default | Description |
|---|---|---|
| `missing_threshold` | 6 | Remove cycle if ≥ N consecutive missing samples |
| `outofrange_threshold` | 6 | Remove cycle if ≥ N out-of-range points |
| `residual_threshold` | 0.172 | Ellipse fitting RMS residual cutoff (dimensionless; IQR×1.5 fence of dataset) |
| `closure_radius` | 0.697 | Start-circle radius as fraction of sd_major (IQR×1.5 fence of L-hand data) |
| `closure_tail_ratio` | 0.5 | Fraction of cycle treated as "tail" for closure check |
| `near_circle_threshold` | 0.85 | Flatness threshold for Q-vector method |
| `clip_oi_to_one` | True | Clip OI > 1.0 to 1.0 |
| `x_min/x_max/y_min/y_max` | -30/1048/185/1737 | Tablet active area bounds (device-specific) |

> **Note**: `closure_radius` and `residual_threshold` were derived from the original dataset. When applying to new data, recalculate these from your own distribution.

## Known Limitations

- Coordinate bounds (`x_min` etc.) are hardcoded for a specific tablet — generalisation requires reconfiguration
- Participants who naturally draw landscape-oriented ellipses (major axis horizontal) will show attenuated OI values under the PCA-based method; a y-axis-based OI option is planned for a future version

## Research Context

This pipeline was developed as part of a study on how **visually-induced sense of body ownership affects bimanual coordination** (n=24, within-subjects design, 4 VR conditions). Key results:

- Disownership score correlated significantly with OI change (r = 0.43, p = 0.03)
- Bimanual coupling was observed in both hands across all conditions (p < 0.01 vs. unimanual baseline)

## License

MIT
