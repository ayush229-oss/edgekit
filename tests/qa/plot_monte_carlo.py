"""Render the EdgeKit /graph/v2/monte-carlo response as a percentile fan chart."""
import json
import matplotlib.pyplot as plt

with open(r"C:\Users\Ayush\projects\edgekit\tests\qa\mc_result.json") as f:
    data = json.load(f)

p = data["percentiles"]
x = list(range(len(p["p50"])))
m = data["base_metrics"]

fig, ax = plt.subplots(figsize=(10, 6))
ax.fill_between(x, p["p5"], p["p95"], color="#4C72B0", alpha=0.15, label="5th-95th pct")
ax.fill_between(x, p["p25"], p["p75"], color="#4C72B0", alpha=0.35, label="25th-75th pct")
ax.plot(x, p["p50"], color="#1F4E78", linewidth=2, label="Median (p50)")
ax.axhline(100, color="gray", linestyle="--", linewidth=1, label="Starting equity")

ax.set_title(
    f"EdgeKit Monte Carlo — EMA cross 20/50 (XAUUSD M15)\n"
    f"{data['n_sims']} simulations × {data['n_trades']} resampled trades — "
    f"base run: WR {m['wr']}%, total R {m['total_r']}, max DD {m['max_dd']}%"
)
ax.set_xlabel("Trade #")
ax.set_ylabel("Equity")
ax.legend(loc="upper left")
ax.grid(alpha=0.3)

out = r"C:\Users\Ayush\projects\edgekit\tests\qa\EdgeKit_MonteCarlo_example.png"
fig.tight_layout()
fig.savefig(out, dpi=150)
print("Saved:", out)
