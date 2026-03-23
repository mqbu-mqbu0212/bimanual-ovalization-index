[日本語版はこちら](README_ja.md)

# bimanual-ellipticity-index — OI Calculator for Bimanual Coordination Research

A Python pipeline for computing the Ellipticity Index (OI) from bimanual coordination task data recorded on a pen tablet.

## Background

In bimanual coordination research, participants are asked to simultaneously draw a circle with one hand and a straight line with the other. Due to the **bimanual coupling effect**, both trajectories become distorted: the circle-drawing hand's trajectory becomes more elliptical (elongated toward a line), and the line-drawing hand's trajectory curves toward an ellipse.

The **Ellipticity Index** (OI) quantifies how elliptical a trajectory is, ranging from 0 (perfect line) to 1 (perfect circle). In bimanual coupling analysis, changes in OI for both hands are used to measure the degree of coupling.

### Motivation

Despite OI being a widely used metric, **no standardised method exists for computing it**. The line-drawing hand tends to show larger OI changes than the circle-drawing hand, and analysis has often focused there as a result. However, since the task is inherently bimanual, looking at only one hand leaves the full picture of interlimb interaction incomplete. Even if the circle hand shows smaller changes, ignoring it risks drawing conclusions from only half the data. The need for a tool that can analyse both hands consistently was one of the motivations behind this project.

During my own research on how the sense of body ownership (manipulated via VR) affects bimanual coordination, I also found that:

- The existing OI computation code I had written was fragmented, inconsistently configured, and partially manual
- Rotation correction was applied by forcibly converting landscape-oriented ellipses to portrait orientation — an approach that is inherently arbitrary

This tool is a ground-up rewrite that addresses those issues. It is released publicly with the hope that it helps **standardise OI computation across the field**, making results more comparable between studies and supporting further development of bimanual coordination research — including HCI applications involving body ownership, haptics, and motor control.

## Method

OI is computed via **PCA** on each detected cycle's trajectory:

- `sd_major` = standard deviation along the first principal component
- `sd_minor` = standard deviation along the second principal component
- `OI = sd_minor / sd_major`

PCA is rotation-invariant, so no axis-alignment correction is needed. For near-circular cycles (flatness ≥ 0.85), axis ambiguity is resolved by computing the midpoint of the start and end points, then determining which principal axis it aligns with more closely.

Cycles are detected by projecting the trajectory onto its PCA major axis and identifying turnaround points. Each detected cycle is then quality-filtered (ellipse fitting residual check and closure check) before being used in OI calculation. Results are aggregated per participant per condition.

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
| `near_circle_threshold` | 0.85 | Flatness threshold above which axis ambiguity is resolved by midpoint-axis alignment |
| `clip_oi_to_one` | True | Clip OI > 1.0 to 1.0 |
| `x_min/x_max/y_min/y_max` | -30/1048/185/1737 | Tablet active area bounds (device-specific) |

> **Note**: `closure_radius` and `residual_threshold` were derived from the original dataset. When applying to new data, recalculate these from your own distribution.

## Examples

The following figures show representative cycles from the pipeline's filtering stages.
Images use anonymised data.

### Kept cycles

| Circle hand | Line hand |
|:-----------:|:---------:|
| ![Circle hand — kept](images/fig1_circle_kept.png) | ![Line hand — kept](images/fig2_line_kept.png) |

### Removed cycles

| Closure failure | Missing samples | High residual |
|:---------------:|:---------------:|:-------------:|
| ![Closure removed](images/fig3_closure_removed.png) | ![Missing removed](images/fig4_missing_removed.png) | ![Residual removed](images/fig5_residual_removed.png) |
| Tail (orange) never entered the closure circle | 10 consecutive missing samples exceeded threshold (6) | Ellipse fit RMS=0.1795 exceeded threshold 0.172 |

## Known Limitations

- Coordinate bounds (`x_min` etc.) are hardcoded for a specific tablet — generalisation requires reconfiguration
- Participants who naturally draw landscape-oriented ellipses (major axis horizontal) will show attenuated OI values under the PCA-based method; a y-axis-based OI option is planned for a future version

## Research Context

This pipeline was developed and validated using data from a study on how visually-induced sense of body ownership affects bimanual coordination. Key results from that study:

- Bimanual coupling was observed in both hands across all conditions
- A significant correlation between disownership score and bimanual coupling change was observed under one condition

## License

MIT
