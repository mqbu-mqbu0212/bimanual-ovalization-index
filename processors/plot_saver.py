import os
import matplotlib.pyplot as plt


class PlotSaver:
    """
    Handles all plot generation and file saving for the pipeline.

    Each public method corresponds to one output folder stage.

    Color conventions:
        blue    ('b-')      = kept cycles (normal or trimmed)
        magenta ('#CC00CC') = before-trim version of trimmed cycles
        red     ('r-')      = removed cycles
    """

    def __init__(self, reason_to_label_fn):
        """
        Args:
            reason_to_label_fn: callable(removal_reason: str) → short label str.
        """
        self._reason_to_label = reason_to_label_fn

    # -------------------------------------------------------------------------
    # Low-level helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _save_fig(ax, path, title):
        """Apply common formatting and save the figure."""
        ax.set_aspect('equal')
        ax.set_title(title)
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        ax.get_figure().tight_layout()
        ax.get_figure().savefig(path)
        plt.close(ax.get_figure())

    @staticmethod
    def _make_fig():
        """Create a new figure and axis."""
        fig, ax = plt.subplots()
        return fig, ax

    def _save_cycle(self, group, color, label, title, path):
        """Draw one cycle and save to path."""
        _, ax = self._make_fig()
        ax.plot(group['x'], group['y'], color=color, linewidth=1, label=label)
        self._save_fig(ax, path, title)

    def _get_trimmed_set(self, df_trimmed_before):
        """Return set of trimmed cycle numbers."""
        if df_trimmed_before is not None and not df_trimmed_before.empty:
            return set(int(c) for c in df_trimmed_before['cycle'].unique())
        return set()

    def _get_reason(self, group):
        """Extract and label removal reason from group."""
        if 'removal_reason' in group.columns:
            return self._reason_to_label(str(group['removal_reason'].iloc[0]))
        return 'unknown'

    def _save_kept_cycles(self, df_kept, df_trimmed_before, save_dir, id_name, condition_name, prefix='cycle'):
        """Save all kept cycles (blue); also save before-trim in magenta for trimmed ones."""
        if df_kept is None or df_kept.empty:
            return
        trimmed = self._get_trimmed_set(df_trimmed_before)
        for cycle_num, group in df_kept.groupby('cycle'):
            cn = int(cycle_num)
            base = f"{prefix}_{cn}"
            if cn in trimmed:
                # Before-trim version in magenta
                before = df_trimmed_before[df_trimmed_before['cycle'] == cycle_num]
                self._save_cycle(
                    before, '#CC00CC', 'Before trim',
                    f"{id_name}_{condition_name}_cycle{cn} [closure_trimmed_before]",
                    os.path.join(save_dir, f"{base}_closure_trimmed_before.png")
                )
                # After-trim version in blue
                self._save_cycle(
                    group, 'b', 'Trimmed',
                    f"{id_name}_{condition_name}_cycle{cn} [trimmed]",
                    os.path.join(save_dir, f"{base}_trimmed.png")
                )
            else:
                self._save_cycle(
                    group, 'b', 'Data',
                    f"{id_name}_{condition_name}_cycle{cn}",
                    os.path.join(save_dir, f"{base}.png")
                )

    def _save_removed_cycles(self, df_removed, save_dir, id_name, condition_name, prefix='cycle'):
        """Save all removed cycles (red) with reason in filename."""
        if df_removed is None or df_removed.empty:
            return
        for cycle_num, group in df_removed.groupby('cycle'):
            cn = int(cycle_num)
            reason = self._get_reason(group)
            self._save_cycle(
                group, 'r', 'Data',
                f"{id_name}_{condition_name}_cycle{cn} [{reason}]",
                os.path.join(save_dir, f"{prefix}_{cn}_{reason}.png")
            )

    # -------------------------------------------------------------------------
    # Stage output methods
    # -------------------------------------------------------------------------

    def _save_cycle_plots(self, df_kept, df_removed, df_trimmed_before,
                          output_path, stage, id_name, condition_name):
        """02_cycles/: per-cycle plots for all kept and removed cycles."""
        save_dir = os.path.join(output_path, stage, id_name, condition_name)
        os.makedirs(save_dir, exist_ok=True)
        self._save_kept_cycles(df_kept, df_trimmed_before, save_dir, id_name, condition_name)
        self._save_removed_cycles(df_removed, save_dir, id_name, condition_name)

    def _save_filtered_plots(self, df_kept, df_removed, df_trimmed_before,
                             output_path, stage, id_name, condition_name):
        """03_filtered/: kept/, removed/, before_trim/ subfolders."""
        base = os.path.join(output_path, stage)

        kept_dir   = os.path.join(base, 'kept',        id_name, condition_name)
        removed_dir = os.path.join(base, 'removed',    id_name, condition_name)
        before_dir  = os.path.join(base, 'before_trim', id_name, condition_name)
        for d in [kept_dir, removed_dir, before_dir]:
            os.makedirs(d, exist_ok=True)

        trimmed = self._get_trimmed_set(df_trimmed_before)

        # kept/
        if df_kept is not None and not df_kept.empty:
            for cycle_num, group in df_kept.groupby('cycle'):
                cn = int(cycle_num)
                label = 'Trimmed' if cn in trimmed else 'Data'
                self._save_cycle(
                    group, 'b', label,
                    f"{id_name}_{condition_name}_cycle{cn}",
                    os.path.join(kept_dir, f"cycle_{cn}.png")
                )

        # removed/
        self._save_removed_cycles(df_removed, removed_dir, id_name, condition_name)

        # before_trim/
        if df_trimmed_before is not None and not df_trimmed_before.empty:
            for cycle_num, group in df_trimmed_before.groupby('cycle'):
                cn = int(cycle_num)
                self._save_cycle(
                    group, '#CC00CC', 'Before trim',
                    f"{id_name}_{condition_name}_cycle{cn} [before_trim]",
                    os.path.join(before_dir, f"cycle_{cn}_before_trim.png")
                )

    def _save_all_removed_plots(self, df_removed, output_path, id_name, condition_name):
        """05_all_removed/: all removed cycles in one flat folder."""
        if df_removed is None or df_removed.empty:
            return
        save_dir = os.path.join(output_path, "05_all_removed")
        os.makedirs(save_dir, exist_ok=True)
        for cycle_num, group in df_removed.groupby('cycle'):
            cn = int(cycle_num)
            reason = self._get_reason(group)
            self._save_cycle(
                group, 'r', 'Data',
                f"{id_name}_{condition_name}_cycle{cn} [{reason}]",
                os.path.join(save_dir, f"{id_name}_{condition_name}_cycle_{cn}_{reason}.png")
            )

    def _save_all_cycles_plots(self, df_kept, df_removed, output_path,
                               id_name, condition_name, df_trimmed_before=None):
        """07_all_cycles/: all cycles flat (kept, removed, trim pairs)."""
        save_dir = os.path.join(output_path, "07_all_cycles")
        os.makedirs(save_dir, exist_ok=True)
        trimmed = self._get_trimmed_set(df_trimmed_before)

        # Before-trim versions in magenta
        if df_trimmed_before is not None and not df_trimmed_before.empty:
            for cycle_num, group in df_trimmed_before.groupby('cycle'):
                cn = int(cycle_num)
                self._save_cycle(
                    group, '#CC00CC', 'Before trim',
                    f"{id_name}_{condition_name}_cycle{cn} [before_trim]",
                    os.path.join(save_dir, f"{id_name}_{condition_name}_cycle_{cn}_before_trim.png")
                )

        # Kept cycles in blue
        if df_kept is not None and not df_kept.empty:
            for cycle_num, group in df_kept.groupby('cycle'):
                cn = int(cycle_num)
                label = 'Trimmed' if cn in trimmed else 'Data'
                self._save_cycle(
                    group, 'b', label,
                    f"{id_name}_{condition_name}_cycle{cn}",
                    os.path.join(save_dir, f"{id_name}_{condition_name}_cycle_{cn}.png")
                )

        # Removed cycles in red
        if df_removed is not None and not df_removed.empty:
            for cycle_num, group in df_removed.groupby('cycle'):
                cn = int(cycle_num)
                reason = self._get_reason(group)
                self._save_cycle(
                    group, 'r', 'Data',
                    f"{id_name}_{condition_name}_cycle{cn} [{reason}]",
                    os.path.join(save_dir, f"{id_name}_{condition_name}_cycle_{cn}_{reason}.png")
                )

    def _save_all_trimmed_plots(self, df_trimmed_before, df_kept,
                                output_path, id_name, condition_name):
        """06_all_trimmed/: before/after trim pairs."""
        if df_trimmed_before is None or df_trimmed_before.empty:
            return
        save_dir = os.path.join(output_path, "06_all_trimmed")
        os.makedirs(save_dir, exist_ok=True)

        for cycle_num, before_group in df_trimmed_before.groupby('cycle'):
            cn = int(cycle_num)
            # Before trim: magenta
            self._save_cycle(
                before_group, '#CC00CC', 'Before trim',
                f"{id_name}_{condition_name}_cycle{cn} [before_trim]",
                os.path.join(save_dir, f"{id_name}_{condition_name}_cycle_{cn}_before_trim.png")
            )
            # After trim: blue
            if df_kept is not None and not df_kept.empty:
                after_group = df_kept[df_kept['cycle'] == cycle_num]
                if not after_group.empty:
                    self._save_cycle(
                        after_group, 'b', 'Trimmed',
                        f"{id_name}_{condition_name}_cycle{cn} [trimmed]",
                        os.path.join(save_dir, f"{id_name}_{condition_name}_cycle_{cn}_trimmed.png")
                    )
