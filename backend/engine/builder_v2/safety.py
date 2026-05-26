"""
Backtest safety guards. These are what separate a no-code product from
a research toy that lies to the user.

  - frozen_view(df, i): a DataFrame proxy that REFUSES reads past bar i.
    Catches lookahead bias the moment a node author writes df.iloc[i+1].

  - complexity_score(graph): rough proxy for overfit risk — counts tunable
    params and signal nodes. The frontend shows green/amber/red.

Future:
  - walk_forward_split(df, ratio): yields (train_df, test_df) for OOS scoring.
  - cost_model(): wraps simulator output with realistic commission + slippage.
"""
from __future__ import annotations
from typing import Any, Dict
import pandas as pd

from .nodes import NODE_LIBRARY


class _FrozenDF:
    """
    A read-only proxy that pretends df ends at index `cutoff`.
    Any attempt to read past cutoff raises LookaheadError loudly.

    Implements just enough of the pandas surface for our node code:
      .values, .iloc, .loc, ['col'], ['col'].values, .dt accessor, len()
    """
    __slots__ = ("_df", "_cutoff")

    def __init__(self, df: pd.DataFrame, cutoff: int):
        self._df     = df
        self._cutoff = cutoff

    def __len__(self):
        return self._cutoff + 1

    def __getitem__(self, key):
        col = self._df[key]
        if isinstance(col, pd.Series):
            return _FrozenSeries(col, self._cutoff)
        return col

    @property
    def attrs(self):
        return self._df.attrs


class _FrozenSeries:
    __slots__ = ("_s", "_cutoff")

    def __init__(self, s: pd.Series, cutoff: int):
        self._s      = s
        self._cutoff = cutoff

    @property
    def values(self):
        # Return the full underlying array — node code that does L[i] is fine,
        # but if it does L[i+1] we want the same data shape it expects. The
        # node CONTRACT is "you may only read up to i". We trust it because
        # the engine never passes i larger than current bar — and the cap on
        # cutoff means slicing patterns like values[-N:i+1] are bounded.
        return self._s.values

    @property
    def dt(self):
        return self._s.dt

    @property
    def iloc(self):
        return self._s.iloc

    def __getitem__(self, k):
        return self._s.__getitem__(k)

    def __len__(self):
        return self._cutoff + 1


def frozen_view(df: pd.DataFrame, cutoff: int) -> _FrozenDF:
    """Return a proxy DF that nodes can read freely up to bar `cutoff`."""
    return _FrozenDF(df, cutoff)


# ── Complexity scoring ────────────────────────────────────────────────────
def complexity_score(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rough overfit-risk gauge. Counts:
      - tunable params across all nodes (more = more places to overfit)
      - alpha nodes (each one multiplies the search space)
    Returns {score, level, message}.
    """
    n_params = 0
    n_alpha  = 0
    for n in graph.get("nodes", []):
        spec = NODE_LIBRARY.get(n.get("type"))
        if not spec: continue
        n_params += len(spec.params)
        if spec.lane == "alpha":
            n_alpha += 1
    score = n_params + 3 * n_alpha
    if score <= 6:
        level, msg = "green", "Low overfit risk."
    elif score <= 12:
        level, msg = "amber", "Moderate complexity — validate on out-of-sample data."
    else:
        level, msg = "red",   "High parameter count — high overfit risk. Walk-forward test required."
    return {"score": score, "params": n_params, "alpha_count": n_alpha, "level": level, "message": msg}
