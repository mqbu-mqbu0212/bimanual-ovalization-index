import pandas as pd
import numpy as np


class OICalculator:
    """
    Ellipticity Index (OI) calculator.

    OI is defined as sd_minor / sd_major (PCA-based), ranging from 0 (line) to 1 (circle).

    For near-circular cycles (flatness >= near_circle_threshold), the Q-vector method
    is used to determine the correct numerator/denominator (avoids axis flip issues).

    For elliptical cycles, OI = flatness = sd_minor / sd_major directly.

    If clip_oi_to_one is True, any OI > 1.0 is clipped to 1.0.
    """

    def __init__(self, config=None):
        if config is None:
            config = {}
        self.near_circle_threshold = config.get("near_circle_threshold", 0.85)
        self.line_oi_threshold = config.get("line_oi_threshold", 0.3)
        self.clip_oi_to_one = config.get("clip_oi_to_one", True)

    def calculate(self, df: pd.DataFrame, trimmed_before: pd.DataFrame = None):
        """
        Compute OI for all cycles in df.

        Args:
            df:              DataFrame of kept cycles (after rotation correction).
            trimmed_before:  DataFrame of pre-trim cycles (for oi_before_trim logging).

        Returns:
            oi_value:    Mean OI across all valid cycles (float).
            df_kept:     DataFrame of cycles used in OI calculation.
            df_removed:  DataFrame of cycles excluded at this stage (empty in current version).
            cycle_log:   List of dicts with per-cycle OI metrics.
        """

        cycles = list(df.groupby('cycle'))
        cycle_nums = [int(c) for c, _ in cycles]
        groups = {int(c): g for c, g in cycles}

        # PCA info for pre-trim cycles (for oi_before_trim logging)
        trimmed_before_groups = {}
        if trimmed_before is not None and not trimmed_before.empty:
            for cn, g in trimmed_before.groupby('cycle'):
                trimmed_before_groups[int(cn)] = g

        # Compute PCA descriptors for all cycles
        pca_info = {}
        for cn in cycle_nums:
            info = self._calc_pca(groups[cn])
            if info is not None:
                pca_info[cn] = info

        # Compute OI for each cycle
        oi_list = []
        keep_indices = []
        removed_parts = []
        cycle_log = []

        for cn in cycle_nums:
            group = groups[cn]
            if cn not in pca_info:
                continue

            info = pca_info[cn]
            flatness = info['flatness']

            # Compute OI on pre-trim data if available
            oi_before_trim = None
            if cn in trimmed_before_groups:
                info_before = self._calc_pca(trimmed_before_groups[cn])
                if info_before is not None:
                    oi_before_trim = self._calc_oi_from_info(info_before, trimmed_before_groups[cn])

            # Compute OI for each cycle
            oi = self._calc_oi_from_info(info, group)
            if oi is None:
                continue

            # Clip OI to 1.0 if requested
            if oi > 1.0:
                if self.clip_oi_to_one:
                    oi = 1.0
                else:
                    print(f"  Cycle {cn}: OI={oi:.3f} > 1.0 (clip_oi_to_one=False, keeping as-is)")

            oi_list.append(oi)
            keep_indices.extend(group.index.tolist())

            cycle_log.append({
                'cycle': cn,
                'oi_before_trim': round(oi_before_trim, 4) if oi_before_trim is not None else None,
                'oi_after_trim': round(oi, 4) if cn in trimmed_before_groups else None,
                'oi': round(oi, 4),
                'final_result': 'kept',
            })

        df_kept = df.loc[keep_indices].copy() if keep_indices else pd.DataFrame(columns=df.columns)
        df_removed = pd.concat(removed_parts) if removed_parts else pd.DataFrame(columns=df.columns)
        oi_value = float(np.mean(oi_list)) if oi_list else float('nan')

        return oi_value, df_kept, df_removed, cycle_log

    def _calc_oi_from_info(self, info, group):
        """Compute OI from PCA info and cycle group."""
        flatness = info['flatness']
        if flatness >= self.near_circle_threshold:
            return self._calc_oi_by_q(info, group)
        else:
            return info['flatness']

    def _calc_pca(self, group):
        """Compute PCA-based shape descriptors for a single cycle."""
        coords = group[['x', 'y']].to_numpy()
        if len(coords) < 5:
            return None

        center = coords.mean(axis=0)
        centered = coords - center
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        idx_major = np.argmax(eigenvalues)
        idx_minor = 1 - idx_major

        sd_major = np.sqrt(max(eigenvalues[idx_major], 0))
        sd_minor = np.sqrt(max(eigenvalues[idx_minor], 0))

        if sd_major == 0:
            return None

        pc_major = eigenvectors[:, idx_major]
        angle_rad = np.arctan2(pc_major[0], pc_major[1])
        angle_deg = np.degrees(angle_rad) % 180
        if angle_deg > 90:
            angle_deg -= 180

        flatness = sd_minor / sd_major

        return {
            'sd_major': sd_major,
            'sd_minor': sd_minor,
            'pc_major': pc_major,
            'pc_minor': eigenvectors[:, idx_minor],
            'angle_deg': angle_deg,
            'flatness': flatness,
            'center': center,
            'coords': coords,
        }

    def _calc_oi_by_q(self, info, group):
        """
        Compute OI for near-circular cycles using the Q-vector method.
        Q = midpoint of start/end - center. The axis whose direction aligns
        more with Q is treated as the major axis (determines denominator).
        """
        coords = info['coords']
        center = info['center']
        pc_major = info['pc_major']
        pc_minor = info['pc_minor']
        sd_major = info['sd_major']
        sd_minor = info['sd_minor']

        start = coords[0]
        end = coords[-1]
        Q = ((start + end) / 2) - center

        q_major = abs(np.dot(Q, pc_major))
        q_minor = abs(np.dot(Q, pc_minor))

        if q_minor >= q_major:
            return sd_major / sd_minor
        else:
            return sd_minor / sd_major
