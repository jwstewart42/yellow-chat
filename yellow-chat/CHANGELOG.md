# Changelog

## 1.0.0 — 2026-11-08

- Initial release.
- Stdlib-only Python chat server: web UI via HA ingress + key-authenticated
  JSON API for agents (host port 8735).
- Append-only message log at `/data/messages.jsonl`; per-agent keys generated
  on first run into `/data/keys.json` and printed to the add-on log.
