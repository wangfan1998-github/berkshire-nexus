# BerkshireNexus Desktop Design Contract

## Direction

The desktop app is a **daylight observatory logbook**: a calm, local-first operating surface where every automated decision can be traced from research evidence to a paper execution and delayed learning label.

The direction was developed using the public [Impeccable](https://github.com/pbakaus/impeccable) process as a craft and anti-pattern reference. No Impeccable visual asset or brand treatment is copied.

## Product thesis

The interface exists to make the evidence chain visible:

```text
market/fundamental provenance + cited news → deterministic research + optional AI synthesis
                                            → deterministic risk → paper execution → learning feedback
```

Live trading is deliberately rendered as an honest locked state. A disabled-looking control is not enough: selecting it explains the missing authoritative account snapshot, restart recovery, and order reconciliation capabilities.

## Visual system

- **Field:** warm astronomical paper (`#f4f1e8`) instead of a dark crypto dashboard.
- **Navigation rail:** ink green (`#16221b`) with low-contrast astronomical marks.
- **Primary action:** oxidized green (`#31583f` / `#4f7b60`).
- **Caution:** amber (`#a97920`) for fallback or inferred data.
- **Risk:** vermilion (`#ad4538`) for locked capabilities, redlines, and stop controls.
- **Typography:** Manrope for interface language; IBM Plex Mono only for prices, measurements, timestamps, IDs, and machine state.
- **Structure:** continuous ledger rules and asymmetric columns, avoiding equal-sized card grids and nested cards.
- **Icons:** Lucide with one consistent stroke system. No emoji are used as interface controls.

## Interaction principles

1. Every primary control has hover, focus-visible, loading, disabled, success, and error behavior.
2. Browser preview data is always labeled **演示数据**.
3. API secrets are write-only from the webview: the UI receives a configured/not-configured status, never the stored value.
4. Quote time, fundamentals period, provider latency, failure, and fallback fields are visibly separate; “current” never silently means “authoritative.”
5. AI synthesis always names its provider/model and shows evidence IDs. Disabled and degraded states remain useful because data and news are independent.
6. Agent start and stop are visually dominant; a running Agent survives window close through the macOS system tray.
7. Model promotion is visible only when a Challenger exists.
8. Risk settings can only tighten Python's safe defaults and are validated again outside the UI.
9. All animated transitions respect `prefers-reduced-motion`.

## Layout

- Shipping window: `1440 × 920`.
- Supported minimum: `1040 × 720`.
- At narrower desktop widths, the navigation rail collapses to icons while retaining native descriptions and keyboard focus.
- Page content uses one scroll container, so the navigation and current operating mode remain visible.

## Screens

1. **Overview:** portfolio measures, the evidence chain, recent research, operating notes, and executions.
2. **Research:** multi-ticker command bar, source/freshness ledger, cited news, optional AI synthesis, and deterministic memo.
3. **AI Research:** provider/model/base URL, independent AI Keychain credential, connection test, news settings, and the model boundary.
4. **Portfolio:** capital composition, holdings, risk capacity, and append-only paper fills.
5. **Agent:** persistent background process controls and scheduling parameters.
6. **Strategy Learning:** sample readiness, Champion/Challenger evidence, and promotion gate; visually distinct from LLM configuration.
7. **Risk:** deterministic capital limits plus immutable safety rules.
8. **Audit:** cycle index and safe local-record summaries.
9. **Settings:** Binance Keychain credential lifecycle, read-only preflight, and a clear system boundary.

## Rejected patterns

- Generic exchange terminal or crypto card dashboard
- Purple/blue gradients and decorative glass effects
- Decorative performance charts without real historical samples
- Controls that imply live trading is available
- LLM access to broker credentials
- Model-owned risk or execution policy
- Dense monospace typography for prose
- Excessive pills, floating cards, nested cards, or emoji icons
