# Staging Baseline Snapshot — July 16, 2026

Byte-exact copies of the backend artifacts deployed to staging (staging.vrinspector.com) as of the July 15, 2026 Block 8E + authorization-hardening deployments, taken from the VR Inspector Transfer Package (Dropbox: `Projects_and_Engineering/VR_Inspector/VRInspector_Transfer_Package_20260716/03_Current_Implementation/`).

Purpose: this repo had not been pushed since May 2026 while deployments went server-direct. This snapshot makes Git match staging and serves as the porting spec for the Phase 2 rebuild in `vrinspector/app` (PRD v2.63 / REBUILD_PLAN.md increments 03–05).

| File | Deployed location on staging | SHA-256 | Verified |
|---|---|---|---|
| `staging_drawings_block8e.py` | `/opt/vrinspector/backend/app/routers/drawings.py` | `cba0bd2ed2561dac29690317e33e6d04d21b77c18e511ef82c0179d314641f06` | Matches PRD v2.61 documented deployed checksum (verified 2026-11-06) |
| `block8e_migration.sql` | applied to RDS 2026-07-15 (idempotent) | — | Size matches package manifest (900 B) |
| `test_drawings_authorization.py` | local regression suite (not deployed) | — | Suite re-run 2026-11-06 against the snapshot router: PASS |

Notes:

- `test_drawings_authorization.py` imports `staging_drawings_block8e.py` from its own directory; run `python3 test_drawings_authorization.py` here (requires `fastapi`, `pydantic`).
- These files are a historical record. Do not edit them; rebuild work happens in `vrinspector/app`.
- Rollback files and full deployment evidence: PRD v2.61 and the transfer package (`04_Evidence/`).
