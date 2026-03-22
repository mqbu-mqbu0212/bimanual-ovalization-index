import numpy as np
import pandas as pd
import matplotlib.transforms as transforms
from lmfit import Parameters, minimize


def _reason_label(reason):
    """Convert internal reason code to a human-readable label for console output."""
    if reason == "too_few_points":
        return "too few points"
    if reason.startswith("residual_"):
        val = reason.replace("residual_", "")
        return f"ellipse residual too large ({val})"
    if reason == "fit_error":
        return "ellipse fitting error"
    if reason == "closure_no_entry":
        return "trajectory did not reach start circle"
    if reason == "closure_escape":
        return "trajectory escaped from front half"
    return reason


class CycleFilter:
    """
    Ellipse-fitting based cycle filtering.

    Responsibilities:
    - Filter out cycles with poor ellipse fit (residual threshold)
    - Apply closure check: verify that the trajectory returns near its start point

    Note: rotation correction (aligning major axis to y-axis) is NOT applied here,
    because OI is computed via PCA which is rotation-invariant.
    The ellipse fit is used only for quality filtering (residual check).
    """

    def __init__(self, config):
        self.residual_threshold  = config.get("residual_threshold", 0.172)   # dimensionless RMS residual (IQR×1.5 fence)
        self.rotation_range      = config.get("rotation_range", (-45, 45))
        self.line_oi_threshold   = config.get("line_oi_threshold", 0.3)    # flatness below this → treat as line
        self.closure_radius      = config.get("closure_radius", 0.697)     # start-circle radius as fraction of sd_major (L-hand IQR×1.5)
        self.closure_tail_ratio  = config.get("closure_tail_ratio", 0.5)   # fraction of cycle treated as "tail" for closure check
        self.closure_escape_n    = config.get("closure_escape_n", 5)       # consecutive escape points to trigger removal

    # -------------------------------------------------------------------------
    # Cycle filtering
    # -------------------------------------------------------------------------

    def filter_cycles(self, df: pd.DataFrame, condition_name: str):
        """
        Filter cycles based on:
        1. Ellipse fitting residual (dimensionless RMS > threshold → remove)
        2. Closure check (trajectory must return near start point)

        Returns:
            df_kept:          DataFrame of kept cycles.
            df_removed:       DataFrame of removed cycles with 'removal_reason'.
            df_trimmed_before: DataFrame of pre-trim versions of trimmed cycles.
            closure_log:      List of dicts with per-cycle closure metrics.
        """
        kept_indices = []
        removed_parts = []
        trimmed_before_parts = []  # pre-trim versions of trimmed cycles
        self._closure_log = []

        for cycle_num, group in df.groupby('cycle'):
            if self._is_line(group):
                trimmed, closure_reason = self._closure_trim(group, cycle_num)
                if closure_reason:
                    print(f"  Cycle {int(cycle_num)} removed: {_reason_label(closure_reason)}")
                    g = group.copy()
                    g['removal_reason'] = closure_reason
                    removed_parts.append(g)
                else:
                    if len(trimmed) < len(group):
                        trimmed_before_parts.append(group.copy())
                    kept_indices.extend(trimmed.index.tolist())
                continue

            reason, rms = self._should_remove(group, cycle_num)
            if reason:
                print(f"  Cycle {int(cycle_num)} removed: {_reason_label(reason)}")
                g = group.copy()
                g['removal_reason'] = reason
                removed_parts.append(g)
                # Also log residual-removed cycles in closure_log (rms recorded, closure fields are None)
                self._closure_log.append({
                    "cycle": int(cycle_num),
                    "scale": None,
                    "r": None,
                    "nearest_dist_ratio": None,
                    "entry_count": None,
                    "rms": round(rms, 4) if rms is not None else None,
                    "result": None,
                })
            else:
                trimmed, closure_reason = self._closure_trim(group, cycle_num)
                # Write rms into the most recent closure_log entry for this cycle
                if self._closure_log and self._closure_log[-1]['cycle'] == int(cycle_num):
                    self._closure_log[-1]['rms'] = round(rms, 4) if rms is not None else None
                if closure_reason:
                    print(f"  Cycle {int(cycle_num)} removed: {_reason_label(closure_reason)}")
                    g = group.copy()
                    g['removal_reason'] = closure_reason
                    removed_parts.append(g)
                else:
                    if len(trimmed) < len(group):
                        trimmed_before_parts.append(group.copy())
                    kept_indices.extend(trimmed.index.tolist())

        df_kept = df.loc[kept_indices].copy() if kept_indices else pd.DataFrame(columns=df.columns)
        df_removed = pd.concat(removed_parts) if removed_parts else pd.DataFrame(columns=df.columns)
        df_trimmed_before = pd.concat(trimmed_before_parts) if trimmed_before_parts else pd.DataFrame(columns=df.columns)

        # Attach condition name to each log entry
        for row in self._closure_log:
            row["condition"] = condition_name

        return df_kept, df_removed, df_trimmed_before, self._closure_log


    def _closure_trim(self, group: pd.DataFrame, cycle_num=None):
        """
        Check whether the trajectory closes back near its start point,
        and trim any excess tail if needed.

        Algorithm:
        1. Examine the last (tail_ratio * 100)% of the trajectory.
        2. If it never enters the start circle (radius = closure_radius * sd_major) → remove (closure_no_entry).
        3. If it enters the circle but then escapes far from the front half → remove (closure_escape).
        4. Otherwise → trim at the point in the tail closest to the start, return trimmed cycle.

        Returns:
            (trimmed_group, reason): reason is None if the cycle passes (use trimmed_group).
        """
        coords = group[['x', 'y']].to_numpy()
        n = len(coords)
        if n < 10:
            return group, None

        # Ellipse scale from PCA (sd_major of the cycle)
        center = coords.mean(axis=0)
        cov = np.cov((coords - center).T)
        ev = np.linalg.eigh(cov)[0]
        sd_major = np.sqrt(max(ev[1], 0))
        scale = sd_major if sd_major > 0 else 1.0

        # Start point and threshold radius in coordinate units
        start = coords[0]
        r = self.closure_radius * scale

        # Index where the "tail" (latter portion) begins
        tail_start = int(n * (1.0 - self.closure_tail_ratio))
        tail_coords = coords[tail_start:]
        tail_indices = list(group.index[tail_start:])

        # Distance from each tail point to the start point
        dists_from_start = np.linalg.norm(tail_coords - start, axis=1)

        # Whether each tail point is inside the start circle
        inside = dists_from_start <= r
        entry_count = 0
        first_entry_idx = None
        for i in range(len(inside)):
            if inside[i]:
                if first_entry_idx is None:
                    first_entry_idx = i
                if i == 0 or not inside[i-1]:
                    entry_count += 1

        cn_str = f"cycle{int(cycle_num)}" if cycle_num is not None else "cycle?"
        start_end_dist = np.linalg.norm(coords[-1] - coords[0])
        sed_ratio = start_end_dist / scale
        # Nearest distance to start in tail, normalised by sd_major
        nearest_dist = float(np.min(dists_from_start))
        nearest_dist_ratio = nearest_dist / scale

        self._closure_log.append({
            "cycle": int(cycle_num) if cycle_num is not None else -1,
            "scale": round(scale, 2),
            "r": round(r, 2),
            "nearest_dist_ratio": round(nearest_dist_ratio, 3),
            "entry_count": entry_count,
            "rms": None,  # filled in filter_cycles after _should_remove
            "result": None,
        })

        # No entry into start circle → remove
        if entry_count == 0:
            self._closure_log[-1]["result"] = "no_entry"
            return group, "closure_no_entry"

        # Collect tail indices that are outside the circle after first entry
        # Scan from first entry onward; record indices that exit the circle
        escaped_in_tail = []
        entered = False
        for i in range(len(inside)):
            if inside[i]:
                entered = True
            elif entered:
                escaped_in_tail.append(i)

        if not escaped_in_tail:
            # Trajectory stayed inside circle → keep full cycle (no trimming needed)
            self._closure_log[-1]["result"] = "pass"
            return group, None

        # Front-half trajectory (before tail_start)
        front_coords = coords[:tail_start]

        # Escape check: if escaped points are far from the front half for N consecutive points → remove
        consecutive = 0
        for i in escaped_in_tail:
            pt = tail_coords[i]
            if len(front_coords) > 0:
                min_dist = np.min(np.linalg.norm(front_coords - pt, axis=1))
            else:
                min_dist = np.linalg.norm(pt - start)
            if min_dist >= r:
                consecutive += 1
                if consecutive >= self.closure_escape_n:
                    self._closure_log[-1]["result"] = "escape"
                    return group, "closure_escape"
            else:
                consecutive = 0

        # No escape → trim at the point in the tail closest to the start
        nearest_in_tail = int(np.argmin(dists_from_start))
        cut_pos = tail_start + nearest_in_tail

        if cut_pos < n - 1:
            print(f"    [closure] {cn_str} trimmed at {cut_pos}/{n}")
            trimmed = group.iloc[:cut_pos + 1]
            self._closure_log[-1]["result"] = "trimmed"
        else:
            trimmed = group
            self._closure_log[-1]["result"] = "pass"

        return trimmed, None

    def _is_line(self, group: pd.DataFrame) -> bool:
        """Return True if the cycle is line-like (flatness < line_oi_threshold)."""
        coords = group[['x', 'y']].to_numpy()
        if len(coords) < 5:
            return False
        center = coords.mean(axis=0)
        centered = coords - center
        cov = np.cov(centered.T)
        eigenvalues, _ = np.linalg.eigh(cov)
        sd_major = np.sqrt(max(eigenvalues))
        sd_minor = np.sqrt(min(eigenvalues))
        if sd_major == 0:
            return False
        oi = sd_minor / sd_major
        return oi < self.line_oi_threshold

    def _should_remove(self, group: pd.DataFrame, cycle_num=None):
        """Check ellipse fitting residual. Returns (reason, rms); reason is None if the cycle passes."""
        coords = group[['y', 'x']].to_numpy()

        if len(coords) < 5:
            return "too_few_points", None

        # Check ellipse fitting residual
        try:
            params = self._fit_ellipse(coords)
            residuals = self._ellipse_residuals_values(params, coords[:, 1], coords[:, 0])
            rms = float(np.sqrt(np.mean(residuals ** 2)))
            if rms > self.residual_threshold:
                return f"residual_{rms:.3f}", rms
        except Exception as e:
            return "fit_error", None

        return None, rms

    # -------------------------------------------------------------------------
    # Ellipse fitting (lmfit)
    # -------------------------------------------------------------------------

    def _ellipse_residuals(self, params, x, y):
        xc = params['xc'].value
        yc = params['yc'].value
        a = params['a'].value
        b = params['b'].value
        theta = params['theta'].value
        cos_t = np.cos(np.deg2rad(theta))
        sin_t = np.sin(np.deg2rad(theta))
        x_rot = (x - xc) * cos_t + (y - yc) * sin_t
        y_rot = (y - yc) * cos_t - (x - xc) * sin_t
        return ((x_rot / a) ** 2 + (y_rot / b) ** 2) - 1.0

    def _ellipse_residuals_values(self, params, x, y):
        return self._ellipse_residuals(params, x, y)

    def _fit_ellipse(self, data: np.ndarray) -> Parameters:
        params = Parameters()
        params.add('xc', value=np.mean(data[:, 1]))
        params.add('yc', value=np.mean(data[:, 0]))
        params.add('a', value=np.std(data[:, 1]), min=1e-6)
        params.add('b', value=np.std(data[:, 0]), min=1e-6)
        params.add('theta', value=0)

        result = minimize(self._ellipse_residuals, params, args=(data[:, 1], data[:, 0]))
        p = result.params

        # Ensure b >= a (b = major axis)
        if p['b'].value < p['a'].value:
            a_val = p['a'].value
            p['a'].value = p['b'].value
            p['b'].value = a_val
            p['theta'].value += 90

        # Normalise theta to [-90, 90]
        theta = p['theta'].value
        if abs(theta) > 90:
            p['theta'].value += 180 * round(-theta / 180)

        return p

    def _rotate_and_translate(self, data: np.ndarray, params: Parameters):
        xc = params['xc'].value
        yc = params['yc'].value
        a = params['a'].value
        b = params['b'].value
        theta = params['theta'].value

        # Translate to origin
        translated = data - [yc, xc]

        # Determine rotation angle from ellipse fit
        if theta > 80:
            rotate_by = theta - 90
            params['theta'].value = 90
        elif theta < -80:
            rotate_by = theta + 90
            params['theta'].value = 90
        else:
            rotate_by = theta
            params['theta'].value = 0

        params['xc'].value = 0
        params['yc'].value = b

        # Apply rotation matrix
        rad = np.deg2rad(-rotate_by)
        rot_matrix = np.array([
            [np.cos(rad), -np.sin(rad)],
            [np.sin(rad),  np.cos(rad)]
        ])

        rotated = np.dot(translated, rot_matrix)
        rotated += [b, 0]

        return rotated, params
