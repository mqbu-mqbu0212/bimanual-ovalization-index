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

PCA is rotation-invariant, so no axis-alignment correction is needed. For near-circular cycles (flatness ≥ 0.85), the two principal axes become nearly equal in length, making it difficult to determine which is the major axis. In these cases, axis ambiguity is resolved by computing the midpoint of the start and end points (Q), then assigning the axis that aligns more closely with Q as the major axis. Depending on the axis assignment, this can occasionally result in OI > 1.0. By default (`clip_oi_to_one=True`), these values are clipped to 1.0. Set `clip_oi_to_one=False` to retain them as-is.

For cycle detection, PCA is first applied to the entire trajectory of one trial to determine the principal axis direction. Turnaround points are then identified by detecting sign changes in the projection onto this axis, splitting the trajectory into individual cycles. Each detected cycle is then quality-filtered (ellipse fitting residual check and closure check) before being used in OI calculation. Results are aggregated per participant per condition.

The closure check verifies that the trajectory returns near its starting point. The tail (latter half of the cycle) is examined against a closure circle centred on the start point. The following outcomes are possible:

- **no_entry**: the tail never enters the closure circle → cycle removed
- **escape**: the tail enters the circle, exits, and then stays at a distance ≥ r from the front half of the trajectory for `closure_escape_n` consecutive points → cycle removed
- **trim**: the tail enters the circle, exits, but remains within distance r of the front half trajectory → trimmed at the point in the tail closest to the start
- **pass**: the tail enters the circle and does not exit → kept as-is

Since human-drawn trajectories inevitably drift between cycles, the tail portion often represents this drift rather than the intended ellipse. Because this drift cannot be quantified separately, including it in OI calculation would distort the result. Trimming is therefore a deliberate design choice to extract only the portion of the trajectory that reflects the participant's intended shape. In example data, trim changed OI from 0.7892 to 0.8417.

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
| `clip_oi_to_one` | True | Clip OI > 1.0 to 1.0 (set False to retain values above 1.0) |
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

### Closure trim

Since human-drawn trajectories drift between cycles, the tail often represents unintended overlap rather than the intended ellipse shape. When the tail enters the closure circle, exits, but remains within distance r of the front half trajectory, the cycle is trimmed at the point in the tail closest to the start. The figure below shows a before/after example (OI: 0.7892 → 0.8417).

![Before and after trim](images/fig6_trim.png)

## Known Limitations

- Coordinate bounds (`x_min` etc.) are hardcoded for a specific tablet — generalisation requires reconfiguration
- Participants who naturally draw landscape-oriented ellipses (major axis horizontal) will show attenuated OI values under the PCA-based method; a y-axis-based OI option is planned for a future version
- Overlap that stays within the closure circle is not trimmed (classified as **pass**). Trim accuracy therefore depends on the closure circle size, and may be insufficient as a general quality guarantee
- The escape condition (removal when the tail stays far from the front half for `closure_escape_n` consecutive points) has not triggered in any circle-hand data in the original dataset, and is not meaningful for the line hand. Its practical effect on data quality is uncertain. A configuration option to disable trimming entirely is planned for a future version

## Planned Improvements (v2)

- Additional OI calculation options (PCA-based / y-axis-based / nearest-to-Q axis)
- ML-based cycle quality classification to replace the rule-based ellipse fitting filter (Random Forest / LSTM / CNN)
- Geometry-based trim improvement using PCA major axis intersection
- Configurable trim on/off option
- Configurable x/y column selection

## Research Context

This pipeline was developed and validated using data from a study on how visually-induced sense of body ownership affects bimanual coordination. Key results from that study:

- Bimanual coupling was observed in both hands across all conditions
- A significant correlation between disownership score and bimanual coupling change was observed under one condition

## License

MIT
