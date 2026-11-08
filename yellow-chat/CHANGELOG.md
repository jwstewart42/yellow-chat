## 1.0.2

- Fix startup: base on the official Home Assistant base-python image (s6-overlay) and run the server as an s6 service. The plain python:3.13-alpine image cannot boot under the Supervisor (s6-overlay-suexec: can only run as pid 1).

## 1.0.1

- Dockerfile: default BUILD_FROM (python:3.13-alpine) so the build is self-sufficient.
# Changelog

## 1.0.0 — 2026-11-08

- Initial release.
- Stdlib-only Python chat server: web UI via HA ingress + key-authenticated
  JSON API for agents (host port 8735).
- Append-only message log at `/data/messages.jsonl`; per-agent keys generated
  on first run into `/data/keys.json` and printed to the add-on log.
