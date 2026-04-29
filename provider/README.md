# Provider App (Week 6 — placeholder)

This folder will hold the **provider** application introduced in Week 6 of the
course. The provider sells raw materials (PCBs, extruders, kits, cables,
transformers, etc.) to the manufacturer over a REST API.

The provider is its **own** independent process with its **own** SQLite
database and its **own** simulated-day counter. It exposes:

- a CLI (`provider-cli`) for humans and, later, agents
- a REST API (FastAPI + Swagger) consumed by the manufacturer

The full design (data model, endpoints, lifecycle, scenario) lives in
[`docs/PRD-week6.md`](../docs/PRD-week6.md). The conventions every app in
this repo must follow live in [`CLAUDE.md`](../CLAUDE.md).

No code yet. Implementation starts in Week 6.
