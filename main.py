"""
Ellipticity Index (OI) Calculation Pipeline
============================================

Computes the Ellipticity Index (OI = sd_minor / sd_major) from bimanual
coordination task data recorded on a pen tablet.

Usage:
    python main.py --input <input_path> --output <output_dir>

    input_path: path to a single CSV file, or a folder containing CSV files.
    output_dir: directory where all output folders and files will be created.

Output structure:
    02_cycles/       per-cycle plots
    03_filtered/     kept / removed / before_trim subfolders
    04_results/      OI_results.xlsx, cycle_log.csv, error_log.txt
    05_all_removed/  all removed cycles in one flat folder
    06_all_trimmed/  before/after trim pairs
    07_all_cycles/   all cycles in one flat folder
"""

import argparse
from pipeline import Pipeline


# =============================================================================
# Configuration
# Adjust these values for your experimental setup.
# =============================================================================
config = {

    # --- Interpolation ---
    "interpolation_method":    "linear",  # method passed to pandas interpolate()
    "interpolation_limit_long": None,     # max gap to fill for velocity calc (None = no limit)
    "interpolation_limit_short": 5,       # max consecutive samples to fill in kept cycles

    # --- Cycle detection ---
    "cycle_flag_threshold":   100,        # minimum distance between consecutive turnaround peaks
    "missing_threshold":        6,        # remove cycle if >= N consecutive missing samples
    "outofrange_threshold":     6,        # remove cycle if >= N out-of-range points

    # --- Ellipse fitting filter ---
    "residual_threshold":    0.172,       # dimensionless RMS residual (IQR×1.5 fence of dataset)
    "line_oi_threshold":       0.3,       # flatness below this → treat as line (skip residual filter)
    "rotation_range":      (-45, 45),     # allowed tilt range for ellipse major axis (degrees)

    # --- Closure check ---
    # Verifies that each cycle's trajectory returns near its starting point.
    "closure_radius":          0.697,     # start-circle radius as fraction of sd_major (L-hand IQR×1.5)
    "closure_tail_ratio":        0.5,     # fraction of the cycle treated as "tail" for closure check
    "closure_escape_n":            5,     # consecutive escape points needed to trigger removal

    # --- OI calculation ---
    "near_circle_threshold":   0.85,      # flatness >= this → use Q-vector method (near-circular)
    "clip_oi_to_one":          True,      # clip OI values > 1.0 to 1.0 (recommended)

    # --- Coordinate bounds (tablet-specific) ---
    # Remove cycles with >= outofrange_threshold points outside these bounds.
    # Set to float('-inf') / float('inf') to disable.
    "x_min":   -30,
    "x_max":  1048,
    "y_min":   185,
    "y_max":  1737,
}


def main():
    parser = argparse.ArgumentParser(
        description="Ellipticity Index (OI) calculation pipeline for bimanual coordination tasks."
    )
    parser.add_argument("--input",  required=True, help="Input path (CSV file or folder)")
    parser.add_argument("--output", required=True, help="Output folder")
    args = parser.parse_args()

    pipeline = Pipeline(config)
    pipeline.run(args.input, args.output)


if __name__ == "__main__":
    main()
