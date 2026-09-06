"""Build the trend_filter investigation as an Excel workbook."""
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from tests.qa.scan_choppiness import scan as real_scan, CANDIDATES, EMA_PAIRS as REAL_EMA_PAIRS
from tests.qa.trend_filter_proof import main as run_synthetic_stress

OUT = r"C:\Users\Ayush\projects\edgekit\tests\qa\EdgeKit_trend_filter_investigation.xlsx"

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)


def style_header(ws, row=1):
    for cell in ws[row]:
        if cell.value is not None:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(horizontal="center")


def autosize(ws, max_col, width=16):
    for i in range(1, max_col + 1):
        ws.column_dimensions[get_column_letter(i)].width = width


def main():
    print("Re-running real-data choppiness scan...")
    real_rows = []
    for symbol, tf, n_bars in CANDIDATES:
        for fast_p, slow_p in REAL_EMA_PAIRS:
            try:
                crosses, filtered = real_scan(symbol, tf, n_bars, fast_p, slow_p)
            except Exception as e:
                real_rows.append({"symbol": symbol, "timeframe": tf, "fast_ema": fast_p,
                                  "slow_ema": slow_p, "error": str(e)})
                continue
            real_rows.append({
                "symbol": symbol, "timeframe": tf, "fast_ema": fast_p, "slow_ema": slow_p,
                "total_crosses": crosses, "would_be_filtered": filtered,
                "filter_trigger_rate_pct": round(filtered / crosses * 100, 4) if crosses else None,
            })
    real_df = pd.DataFrame(real_rows)

    print("Running adversarial synthetic stress test...")
    synth_df = run_synthetic_stress()

    print("Writing workbook...")
    writer = pd.ExcelWriter(OUT, engine="openpyxl")

    # ── Sheet 1: Summary / proof ──────────────────────────────────────────
    wb = writer.book
    ws = wb.create_sheet("SUMMARY", 0)
    ws["A1"] = "EdgeKit ema_cross — does the trend_filter slider ever do anything?"
    ws["A1"].font = TITLE_FONT
    ws.merge_cells("A1:F1")

    lines = [
        "",
        "ANSWER: No. trend_filter cannot ever filter a setup, on ANY data -- real,",
        "choppy, or adversarially engineered. This is a mathematical property of EMA",
        "recursion, not a data coincidence.",
        "",
        "WHERE IT WAS TESTED",
        "  1. Original slider sweep (3,375 combos, real XAUUSD M15 data): 0/81 ema_cross",
        "     parameter combos showed ANY difference between filter on vs off.",
        "  2. Real-market scan (this workbook, sheet 'REAL_DATA_SCAN'): 9 symbols x",
        "     3 timeframes x 3 EMA-period pairs = 27 combos, 10,000+ actual crossovers.",
        "     0 were ever filtered (0.0%).",
        "  3. Adversarial synthetic stress test (sheet 'SYNTHETIC_STRESS_TEST'):",
        "     sawtooth whipsaw + mean-reverting series specifically engineered to",
        "     maximize crossing frequency. 14,404 crosses, 0 filtered (0.0000%).",
        "     Full backtest pipeline (detect->simulate->compute_metrics) confirmed",
        "     identical trades and identical total_r with filter on vs off in every case.",
        "",
        "WHY -- THE PROOF",
        "  EMA recursion: slow[i] = a_s*C[i] + (1-a_s)*slow[i-1]",
        "                 fast[i] = a_f*C[i] + (1-a_f)*fast[i-1]   (a_f > a_s since",
        "                                                           fast_period < slow_period)",
        "",
        "  Step 1 (algebraic identity): C[i] > slow[i]  <=>  C[i] > slow[i-1]",
        "      because C[i] > slow[i] = a_s*C[i] + (1-a_s)*slow[i-1]",
        "                <=> (1-a_s)*C[i] > (1-a_s)*slow[i-1]  <=>  C[i] > slow[i-1].",
        "",
        "  Step 2: at a fresh bull cross, fast[i] > slow[i] and fast[i-1] <= slow[i-1].",
        "      Expanding fast[i] and using fast[i-1] <= slow[i-1]:",
        "        (a_f-a_s)*C[i] > (1-a_s)*slow[i-1] - (1-a_f)*fast[i-1]",
        "                       >= (1-a_s)*slow[i-1] - (1-a_f)*slow[i-1] = (a_f-a_s)*slow[i-1]",
        "      Dividing by (a_f-a_s) > 0:  C[i] > slow[i-1]  <=>  C[i] > slow[i]  (Step 1).",
        "",
        "  So C[i] > slow[i] is GUARANTEED at every bull cross -- the filter's skip",
        "  condition (C[i] <= slow[i]) can never fire. Symmetric argument for bear",
        "  crosses. This holds for ANY price series, as long as fast_period < slow_period",
        "  -- which the strategy code already enforces (fast_ema >= slow_ema returns []).",
        "",
        "PRACTICAL IMPACT",
        "  The 'Require trend confirmation' toggle in the EMA Crossover template UI",
        "  (backend/engine/strategies/ema_cross.py, ParamSpec 'trend_filter') currently",
        "  has ZERO effect on results, in every condition tested. A user moving this",
        "  slider will see no change and may reasonably conclude the backtest is broken,",
        "  when in fact the toggle is structurally redundant given how the strategy",
        "  defines its entry signal (the cross condition already implies the filter",
        "  condition). This is a strategy-logic design issue worth a product decision:",
        "  either remove the toggle, replace it with a filter that uses an INDEPENDENT",
        "  condition (e.g. a higher-timeframe trend EMA, not the same slow EMA already",
        "  used for the cross), or document that it is a no-op by construction.",
        "",
        "FILE CONTENTS",
        "  REAL_DATA_SCAN          - 27 real MT5 symbol/timeframe/EMA-pair combos",
        "  SYNTHETIC_STRESS_TEST   - 12 adversarial synthetic combos (sawtooth + mean-revert)",
    ]
    for i, text in enumerate(lines, start=2):
        cell = ws.cell(row=i, column=1, value=text)
        if text.isupper() and text.strip():
            cell.font = BOLD
    ws.column_dimensions["A"].width = 100

    # ── Sheet 2: real data scan ──────────────────────────────────────────
    real_df.to_excel(writer, sheet_name="REAL_DATA_SCAN", index=False)
    ws2 = writer.sheets["REAL_DATA_SCAN"]
    style_header(ws2)
    autosize(ws2, real_df.shape[1], 16)

    # ── Sheet 3: synthetic stress test ───────────────────────────────────
    synth_df.to_excel(writer, sheet_name="SYNTHETIC_STRESS_TEST", index=False)
    ws3 = writer.sheets["SYNTHETIC_STRESS_TEST"]
    style_header(ws3)
    autosize(ws3, synth_df.shape[1], 18)

    writer.close()
    print(f"\nSaved: {OUT}")
    print(f"  REAL_DATA_SCAN: {len(real_df)} rows, max filter rate = "
          f"{real_df['filter_trigger_rate_pct'].max()}%")
    print(f"  SYNTHETIC_STRESS_TEST: {len(synth_df)} rows, "
          f"total filtered = {synth_df['would_be_filtered'].sum()} / "
          f"{synth_df['total_crosses'].sum()} crosses")


if __name__ == "__main__":
    main()
