# 0006: A browser UI test on every screen size and zoom in CI

- **Status:** Accepted (1.4)
- **Date:** 2026-10-16

## Context

Layout problems (top bar buttons pushed off screen on phones, long topics and
payloads widening cards, dialogs too wide at high zoom) were found by users,
not by tests: the pytest suites never render a page.

## Decision

- `tools/ui_test.py` drives Chromium (Playwright) against SenseHive on a seeded
  temporary database: phone, tablet, laptop and desktop; 67 to 200 % zoom;
  light and dark; the sign-in page, dashboard, heartbeats page and dialogs.
- The same layout rules as EdgeShell's UI test: no sideways scroll, nothing
  sticking out of cards, dialogs or bars, no text spilling out of its box, no
  short word broken over lines, no JavaScript error or CSP violation.
- Interaction checks on desktop and phone: sign-in (and refusal), filter, sort,
  group, theme memory, adding a topic, heartbeats page, sign-out.
- CI runs it on every pull request with a minimum check count, so a suite that
  silently shrinks fails too; screenshots of failures are uploaded.
- README screenshots are generated from the same seeded data
  (`tools/screenshots.py`), so they always show the current UI and no real data.

## Consequences

- Layout and zoom regressions are caught before merge.
- CI takes a few minutes longer (Chromium download and about 145 checks).
- New UI needs the test hooks (`.sh-card`, `.sh-nav`, `.sh-bar`, `.sh-modal`)
  to be covered.
