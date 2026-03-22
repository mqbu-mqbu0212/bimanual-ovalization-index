import pandas as pd
import numpy as np


class Preprocessor:
    """
    Raw data preprocessor.

    Responsibilities:
    - Remove non-numeric rows (e.g. START/END markers)
    - Add time index column if not present (2-column input)
    - Remove leading/trailing zero or NaN rows (pen-off periods)
    - Assign standard column names: time, y, x
    """

    def process(self, csv_path: str) -> pd.DataFrame:
        """
        Load and preprocess a raw CSV file.

        Args:
            csv_path: Path to the raw CSV file.

        Returns:
            DataFrame with columns ['time', 'y', 'x'],
            with leading/trailing missing rows removed.
        """
        df = pd.read_csv(csv_path, header=None)

        # If only 2 columns (y, x), prepend a sequential time index
        if df.shape[1] == 2:
            df.insert(0, 'idx', range(1, len(df) + 1))

        # Remove rows where y or x column contains non-numeric values
        # (e.g. 'START', 'END' markers written by the recording software)
        df = df[
            pd.to_numeric(df.iloc[:, 1], errors='coerce').notna() &
            pd.to_numeric(df.iloc[:, 2], errors='coerce').notna()
        ]
        df = df.reset_index(drop=True)

        # Convert all columns to numeric
        df = df.apply(pd.to_numeric, errors='coerce')

        # Remove leading rows where the pen is off (y==0 and x==0, or NaN)
        i = 0
        for i in range(len(df)):
            y, x = df.iloc[i, 1], df.iloc[i, 2]
            if not ((y == 0 and x == 0) or pd.isna(y) or pd.isna(x)):
                break

        # Remove trailing rows where the pen is off
        j = len(df) - 1
        for j in range(len(df) - 1, -1, -1):
            y, x = df.iloc[j, 1], df.iloc[j, 2]
            if not ((y == 0 and x == 0) or pd.isna(y) or pd.isna(x)):
                break

        df = df.iloc[i:j + 1, :3].reset_index(drop=True)
        df.columns = ['time', 'y', 'x']

        return df
