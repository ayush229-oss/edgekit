"""Core engine modules — data, indicators, simulation, metrics."""
from .simulator   import simulate
from .metrics     import compute_metrics
from .data_loader import load_csv, load_mt5, pip_size, infer_pip_from_df, validate_ohlcv
from .            import indicators

__all__ = [
    "simulate", "compute_metrics",
    "load_csv", "load_mt5", "pip_size", "infer_pip_from_df", "validate_ohlcv",
    "indicators",
]
