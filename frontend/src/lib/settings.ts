const SETTINGS_KEY = "edgekit.settings.v1";

export type UserSettings = {
  risk_pct:        number;
  max_risk_usd:    number;
  default_symbol:  string;
  default_tf:      string;
  spread_pips:     number;
  commission:      number;
  slippage_pips:   number;
  swap_long_pips:  number;
  swap_short_pips: number;
  default_bars:    number;
  max_concurrent:  number;
};

export const SETTINGS_DEFAULTS: UserSettings = {
  risk_pct:        0.01,
  max_risk_usd:    600,
  default_symbol:  "XAUUSD",
  default_tf:      "M15",
  spread_pips:     0,
  commission:      0,
  slippage_pips:   0,
  swap_long_pips:  0,
  swap_short_pips: 0,
  default_bars:    5000,
  max_concurrent:  1,
};

export function loadSettings(): UserSettings {
  if (typeof window === "undefined") return SETTINGS_DEFAULTS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...SETTINGS_DEFAULTS, ...JSON.parse(raw) } : SETTINGS_DEFAULTS;
  } catch { return SETTINGS_DEFAULTS; }
}

export function saveSettings(s: UserSettings) {
  window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(s));
}
