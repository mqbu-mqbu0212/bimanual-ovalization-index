import pandas as pd
import numpy as np


class CycleDetector:
    """
    Cycle detection and missing data handling.

    Processing steps:
    1. Record missing sample indices (zero or NaN coordinates)
    2. Interpolate all missing samples for velocity calculation
    3. Compute y-axis velocity (used for peak detection)
    4. Re-insert NaN at missing positions; interpolate short gaps only
    5. Remove leading stationary points
    6. Detect cycles via PCA projection peaks
    7. Remove cycles with too many consecutive missing samples
    8. Remove cycles with too many out-of-range points
    9. Remove first and last (potentially incomplete) cycles
    """

    def __init__(self, config):
        self.config               = config
        self.interp_method        = config.get("interpolation_method", "linear")
        self.interp_limit_long    = config.get("interpolation_limit_long", None)   # None = no limit (fill all)
        self.interp_limit_short   = config.get("interpolation_limit_short", 5)     # max gap to fill in kept cycles
        self.flag_threshold       = config.get("cycle_flag_threshold", 100)        # min distance between peaks
        self.missing_threshold    = config.get("missing_threshold", 6)             # consecutive missing → remove cycle
        self.outofrange_threshold = config.get("outofrange_threshold", 6)          # out-of-range points → remove cycle

    def process(self, df: pd.DataFrame):
        """
        Run the full cycle detection pipeline.

        Returns:
            df_kept:   DataFrame of valid cycles with column 'cycle' added.
            all_removed: DataFrame of removed cycles with column 'removal_reason'.
        """
        df = df.reset_index(drop=True)

        # --- Step 1: Record indices of missing samples (zero or NaN) ---
        # Both (0,0) and NaN are treated as missing (pen lifted off tablet).
        missing_idx = df.index[
            ((df['y'] == 0) & (df['x'] == 0)) |
            (df['y'].isna() | df['x'].isna())
        ]
        missing_time = df.loc[missing_idx, 'time'].values

        # --- Step 2: Full interpolation for velocity calculation ---
        # We need a continuous signal to compute velocity; fill everything temporarily.
        df = self._interpolate(df, self.interp_limit_long, missing_idx)

        # --- Step 3: Compute y-axis velocity ---
        df = self._calc_velocity(df)

        # --- Step 4: Restore NaN at missing positions ---
        # Put NaN back so short gaps can be filled conservatively below.
        df.loc[missing_idx, 'y'] = np.nan
        df.loc[missing_idx, 'x'] = np.nan
        # Fill only short consecutive gaps (≤ interp_limit_short)
        df['y'] = df['y'].interpolate(
            method=self.interp_method,
            limit=self.interp_limit_short,
            limit_direction='forward'
        )
        df['x'] = df['x'].interpolate(
            method=self.interp_method,
            limit=self.interp_limit_short,
            limit_direction='forward'
        )

        # --- Step 5: Remove leading stationary points ---
        df = self._remove_leading_zeros(df)

        # --- Step 6: Detect cycles via PCA projection sign changes ---
        pca_axis = self._calc_pca_axis(df)
        df = self._detect_cycles(df, pca_axis)

        # --- Step 6b: Re-map missing_idx after reset_index inside _detect_cycles ---
        missing_idx = df.index[df['time'].isin(missing_time)]

        # --- Step 7: Remove cycles with too many consecutive missing samples ---
        df, removed_missing = self._remove_missing_cycles(df, missing_idx)

        # --- Step 8: Remove cycles with too many out-of-range points ---
        x_min = self.config.get("x_min", float('-inf'))
        x_max = self.config.get("x_max", float('inf'))
        y_min = self.config.get("y_min", float('-inf'))
        y_max = self.config.get("y_max", float('inf'))
        df, removed_range = self._remove_outofrange_cycles(df, x_min, x_max, y_min, y_max)

        # --- Step 9: Remove first and last cycles (likely incomplete) ---
        df = self._remove_incomplete_cycles(df)

        # Combine all removed cycles
        all_removed_parts = [r for r in [removed_missing, removed_range]
                             if r is not None and not r.empty]
        all_removed = pd.concat(all_removed_parts) if all_removed_parts else pd.DataFrame(columns=df.columns)

        return df, all_removed

    # -------------------------------------------------------------------------
    # PCA axis calculation
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # PCA axis calculation
    # -------------------------------------------------------------------------

    def _calc_pca_axis(self, df):
        """
        Compute the first principal component direction of the entire trajectory.
        NaN points are excluded. Returns a unit vector used for projection.
        """
        coords = df[['x', 'y']].to_numpy()
        valid = coords[~(np.isnan(coords[:, 0]) | np.isnan(coords[:, 1]))]
        if len(valid) < 2:
            return np.array([0.0, 1.0])  # fallback: y-axis direction
        centered = valid - valid.mean(axis=0)
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)
        return eigenvectors[:, np.argmax(eigenvalues)]

    # -------------------------------------------------------------------------
    # Cycle detection via PCA projection sign changes
    # -------------------------------------------------------------------------

    def _detect_cycles(self, df, pca_axis):
        """
        Assign a cycle number to each row by detecting turnaround points
        in the PCA-projected trajectory.

        Algorithm:
        1. Project all (x, y) coordinates onto pca_axis.
        2. Compute velocity of projection (diff), smoothed with rolling mean (window=5).
        3. Flag sign changes in smoothed velocity as turnaround points (is_peak).
        4. Remove peaks too close together (projection difference < flag_threshold).
        5. Remove first peak if it is not near the global maximum.
        6. Assign cycle numbers as (cumsum of is_peak + 1) // 2.
        """
        df = df.copy()
        coords = df[['x', 'y']].to_numpy()
        projection = coords @ pca_axis  # project onto PCA major axis

        df['_proj'] = projection

        # Smooth projection velocity to reduce noise
        proj_velocity = pd.Series(projection).diff().fillna(0)
        proj_velocity_smooth = proj_velocity.rolling(window=5, center=True, min_periods=1).mean()

        df['is_peak'] = False
        for i in range(1, len(df) - 1):
            if pd.isna(df.at[df.index[i], 'x']) or pd.isna(df.at[df.index[i], 'y']):
                continue
            prev_v = proj_velocity_smooth.iloc[i - 1]
            curr_v = proj_velocity_smooth.iloc[i]
            if (prev_v > 0 and curr_v <= 0) or (prev_v < 0 and curr_v >= 0):
                df.at[df.index[i], 'is_peak'] = True

        flag_idx = df[df['is_peak']].index

        # Remove peaks that are too close together (projection distance < flag_threshold)
        for i in range(1, len(flag_idx)):
            curr = flag_idx[i]
            prev = flag_idx[i - 1]
            if abs(df.loc[prev, '_proj'] - df.loc[curr, '_proj']) < self.flag_threshold:
                df.at[prev, 'is_peak'] = False

        flag_idx = df[df['is_peak']].index

        # Remove first peak if it is not near the global maximum projection
        if len(flag_idx) > 0:
            first_proj = df.loc[flag_idx[0], '_proj']
            global_max_proj = df['_proj'].max()
            if first_proj < global_max_proj * 0.9:
                df.at[flag_idx[0], 'is_peak'] = False

        df['cycle'] = (df['is_peak'].cumsum() + 1) // 2
        df = df.drop(columns=['_proj'])
        return df.reset_index(drop=True)

    # -------------------------------------------------------------------------
    # Interpolation helper
    # -------------------------------------------------------------------------

    def _interpolate(self, df, limit, missing_idx):
        """
        Replace missing positions with NaN, then linearly interpolate up to `limit` points.
        If limit is None, all gaps are filled.
        """
        df = df.copy()
        df.loc[missing_idx, ['y', 'x']] = np.nan
        df['y'] = df['y'].interpolate(
            method=self.interp_method, limit=limit, limit_direction='forward'
        )
        df['x'] = df['x'].interpolate(
            method=self.interp_method, limit=limit, limit_direction='forward'
        )
        return df

    # -------------------------------------------------------------------------
    # Velocity calculation
    # -------------------------------------------------------------------------

    def _calc_velocity(self, df, rows_per_group=5):
        """
        Compute smoothed y-axis velocity by grouping rows into blocks of 5
        and taking the mean finite-difference within each block.
        The result is stored in the 'velocity' column.
        """
        df = df.copy()
        groups = df.index // rows_per_group
        df['velocity'] = (
            df.groupby(groups)['y'].diff() /
            df.groupby(groups)['time'].diff()
        )
        df['velocity'] = df.groupby(groups)['velocity'].transform('mean')
        df.loc[df.index % rows_per_group != 2, 'velocity'] = np.nan
        df['velocity'] = df['velocity'].interpolate(
            limit_area='inside', limit_direction='both'
        )
        df['velocity'] = df['velocity'].fillna(0)
        return df

    # -------------------------------------------------------------------------
    # Remove leading stationary points
    # -------------------------------------------------------------------------

    def _remove_leading_zeros(self, df):
        """
        Drop rows at the start of the recording where the pen has not yet moved
        (velocity == 0 after initial pen-down).
        """
        for i in range(2, len(df)):
            v = df['velocity'].iloc[i]
            if pd.notna(v) and v != 0:
                if i == 2:
                    break
                df = df.iloc[i:-1, :]
                break
        return df.reset_index(drop=True)

    # -------------------------------------------------------------------------
    # Remove first and last (incomplete) cycles
    # -------------------------------------------------------------------------

    def _remove_incomplete_cycles(self, df):
        """
        Remove the first and last cycle unconditionally.
        These cycles often start or end mid-motion and are not complete ellipses.
        """
        groups = df.groupby('cycle')
        keys = list(groups.groups.keys())
        if len(keys) == 0:
            return df

        df = df.drop(groups.get_group(keys[0]).index)

        groups = df.groupby('cycle')
        keys = list(groups.groups.keys())
        if len(keys) == 0:
            return df.reset_index(drop=True)

        df = df.drop(groups.get_group(keys[-1]).index)
        return df.reset_index(drop=True)

    # -------------------------------------------------------------------------
    # Helper: split cycles into kept / removed
    # -------------------------------------------------------------------------

    @staticmethod
    def _split_cycles(df, remove_mask_fn, reason_fn, print_fn=None):
        """
        Generic helper to split cycles into kept and removed DataFrames.

        Args:
            df:            Input DataFrame with 'cycle' column.
            remove_mask_fn: callable(group) → bool; True means remove this cycle.
            reason_fn:     callable(group) → str; removal reason string.
            print_fn:      optional callable(cycle_num, group) for console output.

        Returns:
            (df_kept, df_removed)
        """
        removed_parts = []
        keep_indices = []

        for cycle_num, group in df.groupby('cycle'):
            if remove_mask_fn(group):
                if print_fn:
                    print_fn(cycle_num, group)
                g = group.copy()
                g['removal_reason'] = reason_fn(group)
                removed_parts.append(g)
            else:
                keep_indices.extend(group.index.tolist())

        df_kept = df.loc[keep_indices].reset_index(drop=True)
        df_removed = pd.concat(removed_parts) if removed_parts else pd.DataFrame(columns=df.columns)
        return df_kept, df_removed

    # -------------------------------------------------------------------------
    # Remove cycles with too many missing samples
    # -------------------------------------------------------------------------

    def _remove_missing_cycles(self, df, missing_idx):
        """
        Remove any cycle that contains >= missing_threshold consecutive missing samples.
        After removal, restore NaN at remaining missing positions for clean plotting.
        """
        def max_consecutive_missing(group):
            mask = group.index.isin(missing_idx)
            max_run = current = 0
            for v in mask:
                current = current + 1 if v else 0
                max_run = max(max_run, current)
            return max_run

        def should_remove(group):
            return max_consecutive_missing(group) >= self.missing_threshold

        def reason(group):
            n = max_consecutive_missing(group)
            return f'missing_{n}pts'

        def on_remove(cycle_num, group):
            n = max_consecutive_missing(group)
            print(f"  Cycle {int(cycle_num)} removed: {n} consecutive missing samples (threshold={self.missing_threshold})")

        # For removed cycles, restore NaN at missing positions
        removed_parts = []
        keep_indices = []
        for cycle_num, group in df.groupby('cycle'):
            if should_remove(group):
                on_remove(cycle_num, group)
                g = group.copy()
                g.loc[g.index.isin(missing_idx), ['y', 'x']] = np.nan
                g['removal_reason'] = reason(group)
                removed_parts.append(g)
            else:
                keep_indices.extend(group.index.tolist())

        df_kept = df.loc[keep_indices].copy()
        df_kept.loc[df_kept.index.isin(missing_idx), ['y', 'x']] = np.nan
        df_kept = df_kept.reset_index(drop=True)
        df_removed = pd.concat(removed_parts) if removed_parts else pd.DataFrame(columns=df.columns)
        return df_kept, df_removed

    # -------------------------------------------------------------------------
    # Remove cycles with too many out-of-range points
    # -------------------------------------------------------------------------

    def _remove_outofrange_cycles(self, df, x_min, x_max, y_min, y_max):
        """
        Remove any cycle that contains >= outofrange_threshold points outside
        the specified coordinate bounds (tablet active area).
        """
        def out_count(group):
            return int((
                (group['x'] < x_min) | (group['x'] > x_max) |
                (group['y'] < y_min) | (group['y'] > y_max)
            ).sum())

        return self._split_cycles(
            df,
            remove_mask_fn=lambda g: out_count(g) >= self.outofrange_threshold,
            reason_fn=lambda g: f'outofrange_{out_count(g)}pts',
            print_fn=lambda cn, g: print(f"  Cycle {int(cn)} removed: {out_count(g)} out-of-range points"),
        )
