# Product

<!-- impeccable:product-schema 1 -->

## Platform

macOS-first desktop application, with a cross-platform Tauri shell and an optional browser-only visual preview.

## Stack

Delegated implementation choice: Tauri 2 with React, TypeScript, and Vite for a cross-platform desktop shell, with the existing Python 3.9+ package retained as the research, learning, risk, and execution engine. macOS is the first shipping target.

## Users

Primary user inferred from the repository and current brief: a technically capable individual investor operating a personal US-equity research and automated paper-trading workflow, primarily from a Mac desktop.

## Product Purpose

BerkshireNexus turns current, source-attributed market evidence and explicit multi-framework equity research into an auditable decision and paper-execution loop. Success means the user can distinguish quote time from fundamentals time, open every cited news source, identify the AI provider/model, understand why a position exists, stop the agent instantly, and inspect every decision after the fact.

## Positioning

The product combines Berkshire-style fundamental reasoning, chokepoint analysis, bounded quantitative features, champion/challenger learning, and deterministic risk controls in one traceable pipeline. The learned model can influence conviction but cannot rewrite or bypass execution policy.

## Operating Context

The user reviews a focused US-stock universe, retrieves current Yahoo/Nasdaq evidence and cited news, optionally synthesizes it through a configured OpenAI-compatible, Ollama, or local Codex provider, runs paper cycles, monitors portfolio and risk state, checks Binance Stocks connectivity, and reviews append-only audit records. Binance remains the external broker surface; the desktop app is the operating console.

## Capabilities and Constraints

- Analyze one or many US-equity tickers.
- Route latest-available quote/history and annual fundamentals through independent providers, recording source time, retrieval time, latency, failures, and field-level fallback.
- Retrieve and deduplicate current news with stable evidence IDs and original URLs.
- Configure optional AI synthesis without granting the model score, risk, credential, or execution authority.
- Run a persistent paper portfolio with simulated commissions and slippage.
- Settle delayed forward-return observations and train an auditable linear challenger model.
- Require explicit or paper-only gated model promotion.
- Enforce deterministic position, turnover, order, data-quality, and daily-loss controls.
- Store desktop secrets in the operating system credential store, never in committed files or UI logs.
- Keep live trading visibly locked until authoritative Binance cash/holding snapshots, restart recovery, and order reconciliation are implemented and verified.
- Direct equities only; tokenized stock settlement remains disabled.

## Brand Commitments

- Product name: BerkshireNexus.
- Preserve the repository's direct, anti-hand-waving investment voice.
- Use the public Impeccable project as a binding craft and anti-pattern reference, not as a brand or asset source.
- Avoid generic crypto-dashboard styling and claims that imply guaranteed performance.

## Evidence on Hand

- Existing Python research and trading modules under `src/`.
- Twenty-two passing unit tests under `tests/`.
- Six detailed research examples under `examples/`.
- Persistent paper portfolio, learning registry, and audit JSON formats.
- No verified live-account reconciliation implementation and no performance track record that may be marketed as proof.

## Product Principles

1. Show the chain of evidence, not merely a score.
2. Safety policy stays outside the learned model.
3. Every automated action is reversible, inspectable, and attributable.
4. Dense information should remain calm, legible, and operational.
5. Honest locked states are better than decorative controls that imply unsupported capability.

## Accessibility & Inclusion

Keyboard navigation, visible focus, non-color-only state communication, reduced-motion support, and WCAG AA text contrast are required for the desktop interface.
