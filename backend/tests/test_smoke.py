"""Smoke tests — fast, no MT5/DB required (EDGEKIT_TEST=1 set by CI)."""
import os
import pytest

os.environ.setdefault("EDGEKIT_TEST", "1")


def test_engine_imports():
    from backend.engine.core.simulator import simulate
    from backend.engine.core.metrics import compute_metrics
    from backend.engine.core.indicators import ema, atr
    assert callable(simulate)
    assert callable(compute_metrics)
    assert callable(ema) and callable(atr)


def test_graph_validate_rejects_empty():
    from backend.engine.builder_v2.validate import validate_graph
    with pytest.raises(ValueError, match="non-empty"):
        validate_graph({"name": "t", "nodes": [], "edges": []})


def test_backtest_request_accepts_date_range():
    """start_date / end_date are optional fields — must parse without error."""
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from backend.api.routes_graph_v2 import GraphBacktestV2Request
    req = GraphBacktestV2Request(
        graph={"name": "t", "nodes": [], "edges": []},
        start_date="2024-01-01",
        end_date="2024-06-30",
    )
    assert req.start_date == "2024-01-01"
    assert req.end_date == "2024-06-30"
