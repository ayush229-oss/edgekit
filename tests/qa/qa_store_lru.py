"""QA check for FINDING-4: the in-memory store cache must be LRU-bounded."""
import pandas as pd
from backend.api import store


def tiny():
    return pd.DataFrame({
        "time": pd.date_range("2025-01-01", periods=5, freq="15min"),
        "O": [1.0] * 5, "H": [1.0] * 5, "L": [1.0] * 5, "C": [1.0] * 5, "V": [1] * 5,
    })


def main():
    ids = [store.put(tiny()) for _ in range(105)]
    mem_after_puts = len(store._MEM)
    print("MAX_MEM_ITEMS       :", store.MAX_MEM_ITEMS)
    print("after 105 puts, _MEM:", mem_after_puts, "(expect <= 100)")
    print("oldest id in _MEM?  :", ids[0] in store._MEM, "(expect False - evicted)")
    print("newest id in _MEM?  :", ids[-1] in store._MEM, "(expect True)")
    # Disk-reload path: clear the mem cache, then fetch an id still on disk.
    # (ids[0] is gone from BOTH caps — disk is also capped at 100 — which is
    # correct; use a recent id that disk still retains.)
    store._MEM.clear()
    df = store.get(ids[-1])
    print("get() reload from disk:", df is not None, "(expect True)")
    print("reload warmed cache   :", ids[-1] in store._MEM, "(expect True)")
    print("bounded after reload  :", len(store._MEM) <= store.MAX_MEM_ITEMS, "(expect True)")

    ok = (mem_after_puts <= store.MAX_MEM_ITEMS
          and ids[0] not in store._MEM
          and df is not None
          and ids[-1] in store._MEM
          and len(store._MEM) <= store.MAX_MEM_ITEMS)
    print("\nLRU CHECK:", "PASS" if ok else "FAIL")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
