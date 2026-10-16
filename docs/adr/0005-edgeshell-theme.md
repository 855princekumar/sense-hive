# 0005: EdgeShell's theme, light by default

- **Status:** Accepted (1.4)
- **Date:** 2026-10-16

## Context

Admins move between EdgeShell and SenseHive (EdgeShell links to it and shows
its heartbeat data). SenseHive had its own look: dark by default, purple
accents, a gradient sign-in page, a different heartbeats page style. Switching
felt like changing products.

## Decision

- Use EdgeShell's palette through `tailwind.config.js`: primary `#1a56db`,
  accent `#0ea5e9`, success `#059669`, warning `#d97706`, danger `#dc2626`,
  Tailwind grays, Inter font.
- **Light by default**, like EdgeShell; dark stays available and is remembered
  per browser, and the heartbeats page follows the same choice.
- The sign-in page uses EdgeShell's sign-in card (white card, logo tile,
  primary button) and shows no default credentials.
- The top bar uses EdgeShell's logo tile and button styles and wraps cleanly on
  small screens.

## Consequences

- One look across the fleet tools; screenshots and docs match.
- Users who preferred the old dark default choose dark once per browser.
- Palette changes in EdgeShell need the same change in `tailwind.config.js`.
