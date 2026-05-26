import type { Config } from "tailwindcss";

/**
 * Edgekit design tokens — Apple-restraint chrome + TradingView candle palette.
 *
 * Token names are kept stable across the refresh so existing components
 * automatically pick up the new look. Add new semantic names alongside as
 * we refine pages.
 *
 *   Bg/surfaces:  paper · surface · surface2
 *   Text:         ink · ink2 · muted
 *   Borders:      border · borderStrong
 *   Brand:        money (single accent, deep green)
 *   Candle:       up · down (TradingView convention)
 *   Highlight:    highlight (warm AI/feature spotlight)
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── New semantic tokens (use these going forward) ───────────────
        paper:        "#FAFAFA",   // page background — near-white, warm
        surface:      "#FFFFFF",   // cards, modals
        surface2:     "#F5F5F7",   // raised surfaces, Apple "fog"
        ink:          "#0A0A0A",   // primary text — true black
        ink2:         "#1D1D1F",   // secondary text — Apple SF black
        muted:        "#86868B",   // tertiary text
        border:       "#E5E5E7",   // hairline divider
        borderStrong: "#D2D2D7",   // emphasized divider
        money:        "#0B6E4F",   // single brand accent — deep money green
        moneyLight:   "#10B981",
        moneyDark:    "#064E3B",
        up:           "#16A34A",   // candle up / Win
        down:         "#DC2626",   // candle down / Loss
        highlight:    "#FEF3C7",   // warm AI / feature spotlight
        highlightInk: "#92400E",

        // ── Legacy aliases — remapped so existing class names refresh ───
        // (cream/sage/terra appear in ~50 files; keep them working but with
        //  the new look. Migrate to semantic names over time.)
        cream:     "#FAFAFA",
        cream2:    "#FFFFFF",
        cream3:    "#F5F5F7",
        sage:      "#0B6E4F",
        sageLight: "#10B981",
        sageMid:   "#16A34A",
        terra:     "#DC2626",
        amber:     "#F59E0B",
      },
      fontFamily: {
        sans:    ['"Inter"', "system-ui", "-apple-system", '"SF Pro Text"', "Segoe UI", "sans-serif"],
        display: ['"Inter"', "system-ui", "-apple-system", '"SF Pro Display"', "sans-serif"],
        mono:    ['"Geist Mono"', '"JetBrains Mono"', '"SF Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        // Apple-scale headlines for hero use
        "display-1": ["72px", { lineHeight: "1.05", letterSpacing: "-0.03em", fontWeight: "700" }],
        "display-2": ["56px", { lineHeight: "1.08", letterSpacing: "-0.025em", fontWeight: "700" }],
        "display-3": ["40px", { lineHeight: "1.1",  letterSpacing: "-0.02em",  fontWeight: "600" }],
      },
      boxShadow: {
        // Apple-style subtle elevation (no heavy drop shadows)
        soft:    "0 1px 2px rgba(0,0,0,0.04), 0 1px 1px rgba(0,0,0,0.03)",
        lift:    "0 4px 12px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.04)",
        float:   "0 12px 32px rgba(0,0,0,0.10), 0 4px 8px rgba(0,0,0,0.05)",
      },
      borderRadius: {
        xl:   "10px",
        "2xl":"14px",
        "3xl":"20px",
      },
    },
  },
  plugins: [],
};
export default config;
