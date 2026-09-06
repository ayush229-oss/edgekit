"""Introspect each strategy template's slider schema and compute the full
cartesian-product size (every possible parameter combination)."""
from math import prod
from backend.engine.strategies import REGISTRY


def values_for(spec):
    """Discrete values a single slider/control can take."""
    if spec.type in ("int", "float"):
        if spec.min is None or spec.max is None:
            return None  # unbounded — can't enumerate
        step = spec.step or (1 if spec.type == "int" else (spec.max - spec.min) / 10)
        n = int(round((spec.max - spec.min) / step)) + 1
        return max(n, 1)
    if spec.type == "select":
        return len(spec.options or [1])
    if spec.type == "bool":
        return 2
    return 1


def main():
    grand = 0
    print(f"{'template':<16} {'params':>6} {'combos':>18}   per-param breakdown")
    print("-" * 100)
    rows = []
    for sid, cls in REGISTRY.items():
        schema = cls.param_schema or []
        counts = []
        detail = []
        for s in schema:
            n = values_for(s)
            counts.append(n if n else 1)
            detail.append(f"{s.key}({s.type}:{n})")
        combos = prod(counts) if counts else 1
        rows.append((sid, len(schema), combos))
        grand += combos
        print(f"{sid:<16} {len(schema):>6} {combos:>18,}   {', '.join(detail)}")
    print("-" * 100)
    print(f"{'TOTAL':<16} {'':>6} {grand:>18,}")
    print(f"\nAt ~50 ms/backtest, exhaustive = ~{grand * 0.05 / 3600:,.1f} hours of compute.")


if __name__ == "__main__":
    main()
