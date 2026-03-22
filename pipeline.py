import os
import pandas as pd
from processors.preprocessor import Preprocessor
from processors.cycle_detector import CycleDetector
from processors.rotator import CycleFilter
from processors.oi_calculator import OICalculator
from processors.plot_saver import PlotSaver


class Pipeline:
    """
    Main processing pipeline for ellipticity index (OI) calculation.

    Orchestrates the full processing flow for each CSV file:
    preprocessor → cycle_detector → cycle_filter → oi_calculator → output.
    """

    def __init__(self, config):
        self.config = config
        self.preprocessor    = Preprocessor()
        self.cycle_detector  = CycleDetector(config)
        self.cycle_filter    = CycleFilter(config)
        self.oi_calculator   = OICalculator(config)
        self.plot_saver      = PlotSaver(self._reason_to_label)

    def run(self, input_path, output_path):
        csv_files = self._collect_csv_files(input_path)
        if not csv_files:
            print("No CSV files found.")
            return

        results = {}      # {(id_name, condition_name): oi_value}
        cycle_counts = {} # {(id_name, condition_name): valid cycle count}
        all_cycle_logs = []

        for csv_path in csv_files:
            id_name, condition_name = self._extract_id_and_condition(csv_path, input_path)
            print(f"\nProcessing: {id_name} / {condition_name}")

            try:
                # ① Preprocessing
                df = self.preprocessor.process(csv_path)

                # ② Cycle detection and missing/outofrange removal
                df, removed_cycles = self.cycle_detector.process(df)

                # ③ Filter cycles (residual, closure check)
                df, removed_filter, trimmed_before, closure_log = self.cycle_filter.filter_cycles(df, condition_name)

                # ⑤ OI calculation
                oi, df_oi_kept, removed_oi, cycle_log_oi = self.oi_calculator.calculate(df, trimmed_before)

                # Merge closure_log and cycle_log_oi into all_cycle_logs
                cl_dict = {row['cycle']: row for row in closure_log}
                oi_dict = {row['cycle']: row for row in cycle_log_oi}
                all_cycle_nums = set(list(cl_dict.keys()) + list(oi_dict.keys()))
                for cn in sorted(all_cycle_nums):
                    cl = cl_dict.get(cn, {})
                    oi_row = oi_dict.get(cn, {})
                    all_cycle_logs.append({
                        'id': id_name,
                        'condition': condition_name,
                        'cycle': cn,
                        'scale': cl.get('scale'),
                        'r': cl.get('r'),
                        'nearest_dist_ratio': cl.get('nearest_dist_ratio'),
                        'entry_count': cl.get('entry_count'),
                        'closure_result': cl.get('result'),
                        'rms': cl.get('rms'),
                        'oi_before_trim': oi_row.get('oi_before_trim'),
                        'oi_after_trim': oi_row.get('oi_after_trim'),
                        'oi': oi_row.get('oi'),
                        'final_result': oi_row.get('final_result', 'removed') if oi_row else 'removed',
                    })

                # Combine all removed cycles from all stages
                all_removed = pd.concat([r for r in [removed_cycles, removed_filter, removed_oi]
                                         if r is not None and not r.empty]) \
                    if any(r is not None and not r.empty for r in [removed_cycles, removed_filter, removed_oi]) \
                    else pd.DataFrame(columns=df.columns)

                # 02_cycles: kept=blue, before-trim=magenta, trimmed=blue, removed=red
                self.plot_saver._save_cycle_plots(df_oi_kept, all_removed, trimmed_before, output_path, "02_cycles", id_name, condition_name)

                # 03_filtered: kept/, removed/, before_trim/
                self.plot_saver._save_filtered_plots(df_oi_kept, all_removed, trimmed_before, output_path, "03_filtered", id_name, condition_name)

                # 05_all_removed: all removed cycles in one folder
                self.plot_saver._save_all_removed_plots(all_removed, output_path, id_name, condition_name)

                # 06_all_trimmed: before-trim (magenta) and after-trim (blue) pairs
                self.plot_saver._save_all_trimmed_plots(trimmed_before, df_oi_kept, output_path, id_name, condition_name)

                # 07_all_cycles: all cycles in a flat folder
                self.plot_saver._save_all_cycles_plots(df_oi_kept, all_removed, output_path, id_name, condition_name, trimmed_before)

                valid_cycles = df_oi_kept['cycle'].nunique()
                results[(id_name, condition_name)] = oi
                cycle_counts[(id_name, condition_name)] = valid_cycles
                print(f"  OI = {oi:.4f}  valid cycles = {valid_cycles}")

            except Exception as e:
                import traceback
                err_msg = traceback.format_exc()
                print(f"  ERROR: {e}")
                print(err_msg)
                # Save error to log file
                error_log_path = os.path.join(output_path, "04_results", "error_log.txt")
                os.makedirs(os.path.join(output_path, "04_results"), exist_ok=True)
                with open(error_log_path, 'a', encoding='utf-8') as f:
                    f.write(f"[{id_name}/{condition_name}] {e}\n{err_msg}\n")
                results[(id_name, condition_name)] = None
                cycle_counts[(id_name, condition_name)] = 0

        # ⑥ Save results to Excel
        self._save_results(results, cycle_counts, output_path)

        # ⑦ Save cycle_log CSV
        if all_cycle_logs:
            df_cycle_log = pd.DataFrame(all_cycle_logs, columns=["id", "condition", "cycle", "scale", "r", "nearest_dist_ratio", "entry_count", "closure_result", "rms", "oi_before_trim", "oi_after_trim", "oi", "final_result"])
            cycle_log_path = os.path.join(output_path, "04_results", "cycle_log.csv")
            df_cycle_log.to_csv(cycle_log_path, index=False, encoding="utf-8-sig")
            print(f"Saved cycle_log: {cycle_log_path}")

    def _collect_csv_files(self, input_path):
        """Collect CSV file paths from a file or directory."""
        if os.path.isfile(input_path):
            return [input_path] if input_path.lower().endswith('.csv') else []
        
        csv_files = []
        for root, dirs, files in os.walk(input_path):
            for file in files:
                if file.lower().endswith('.csv'):
                    csv_files.append(os.path.join(root, file))
        return csv_files

    def _extract_id_and_condition(self, csv_path, input_path):
        """Extract subject ID and condition name from file path."""
        filename = os.path.splitext(os.path.basename(csv_path))[0]
        
        # Expected filename format: "A_CHL.csv"
        parts = filename.split('_')
        if len(parts) >= 2:
            id_name = parts[0]
            condition_name = '_'.join(parts[1:])
        else:
            id_name = "unknown"
            condition_name = filename
        
        return id_name, condition_name

    def _reason_to_label(self, reason_raw):
        """Convert internal removal_reason string to a short file-name label."""
        if reason_raw.startswith('oi_'):
            return 'oi_over'
        elif reason_raw.startswith('residual_'):
            return 'residual'
        elif reason_raw.startswith('endpoint_dist_'):
            return 'endpoint'
        elif reason_raw.startswith('missing_'):
            return 'missing'
        elif reason_raw.startswith('outofrange_'):
            return 'outofrange'
        elif reason_raw == 'angle_outlier':
            return 'angle_outlier'
        elif reason_raw.startswith('angle_'):
            return 'angle_deg'
        elif reason_raw == 'closure_no_entry':
            return 'closure_no_entry'
        elif reason_raw == 'closure_escape':
            return 'closure_escape'
        else:
            return reason_raw.replace('/', '_').replace(' ', '_').replace(':', '_')

    def _save_results(self, results, cycle_counts, output_path):
        """Save OI values and valid cycle counts to an Excel file."""
        os.makedirs(os.path.join(output_path, "04_results"), exist_ok=True)

        id_names = sorted(set(k[0] for k in results.keys()))
        condition_names = sorted(set(k[1] for k in results.keys()))

        df_oi = pd.DataFrame(index=id_names, columns=condition_names)
        df_cycles = pd.DataFrame(index=id_names, columns=condition_names)

        for (id_name, condition_name), oi in results.items():
            df_oi.loc[id_name, condition_name] = oi
        for (id_name, condition_name), count in cycle_counts.items():
            df_cycles.loc[id_name, condition_name] = count

        excel_path = os.path.join(output_path, "04_results", "OI_results.xlsx")
        with pd.ExcelWriter(excel_path) as writer:
            df_oi.to_excel(writer, sheet_name='OI')
            df_cycles.to_excel(writer, sheet_name='valid_cycles')

        print(f"\nSaved OI results: {excel_path}")
