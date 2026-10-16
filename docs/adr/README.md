# Architecture decision records

Short records of decisions that shape SenseHive: the context, the choice, and
what follows from it. A new decision gets the next number; a reversed one is
marked *Superseded* and links to its replacement.

| ADR | Decision | Status |
| --- | -------- | ------ |
| [0001](0001-sqlite-table-per-topic-wal.md) | SQLite, one table per topic, WAL mode | Accepted (1.0, WAL in 1.1) |
| [0002](0002-heartbeat-receiver.md) | Encrypted heartbeat receiver on a public broker | Accepted (1.2) |
| [0003](0003-sign-in-hardening.md) | Sign-in hardening: slow hashes, lockout, fresh sessions, cross-site refusal | Accepted (1.3) |
| [0004](0004-vendored-frontend-and-csp.md) | Browser code built ahead of time, served locally, strict CSP | Accepted (1.4) |
| [0005](0005-edgeshell-theme.md) | EdgeShell's theme, light by default | Accepted (1.4) |
| [0006](0006-browser-ui-test.md) | A browser UI test on every screen size and zoom in CI | Accepted (1.4) |
| [0007](0007-heartbeat-history.md) | Heartbeat history, charts and CSV export | Accepted (1.5) |
| [0008](0008-hostile-input.md) | Treat every input as hostile | Accepted (1.5) |
