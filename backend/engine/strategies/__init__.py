"""
Strategy registry. Strategies self-register so the API can list them dynamically.
"""
from .base          import Strategy, ParamSpec
from .ob_fvg_liq     import OBFVGLiquidity
from .ema_cross      import EMACrossover
from .rsi_mr         import RSIMeanReversion
from .bb_bounce      import BollingerBounce
from .donchian       import DonchianBreakout
from .orb            import OpeningRangeBreakout
from .macd_cross     import MACDCross
from .vwap_pullback  import VWAPPullback
from .supertrend     import SupertrendFlip
from .liq_engulf     import LiquidityGrabEngulfing

REGISTRY: dict[str, type[Strategy]] = {
    "ob_fvg_liq":    OBFVGLiquidity,
    "ema_cross":     EMACrossover,
    "rsi_mr":        RSIMeanReversion,
    "bb_bounce":     BollingerBounce,
    "donchian":      DonchianBreakout,
    "orb":           OpeningRangeBreakout,
    "macd_cross":    MACDCross,
    "vwap_pullback": VWAPPullback,
    "supertrend":    SupertrendFlip,
    "liq_engulf":    LiquidityGrabEngulfing,
}


def get(strategy_id: str) -> type[Strategy]:
    if strategy_id not in REGISTRY:
        raise KeyError(f"Unknown strategy '{strategy_id}'. Available: {list(REGISTRY)}")
    return REGISTRY[strategy_id]


def list_all() -> list[dict]:
    """Return summary of all registered strategies for UI listing."""
    return [
        {
            "id":          sid,
            "name":        cls.name,
            "description": cls.description,
            "params":      [p.__dict__ for p in cls.param_schema],
        }
        for sid, cls in REGISTRY.items()
    ]


__all__ = ["Strategy", "ParamSpec", "REGISTRY", "get", "list_all"]
