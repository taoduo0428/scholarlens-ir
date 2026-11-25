# Changelog

All notable engineering and research milestones for **ScholarLens EvoResearch** are documented in this file.

## [v1.0.0] — 2026-11-25 (Final Engineering Closure & Draft Release)

### Final Release Checks (PR #48 on top of PR #47)
- **Compose Strategy Control Fix (`infra/product.compose.yml`)**: Passed `SCHOLARLENS_PRA_ARM: ${SCHOLARLENS_PRA_ARM:-A}` to `services.api.environment` (strictly keeping `A` as default) and added unit + live Docker Compose **`A -> G -> R -> A` switch & rollback** acceptance (`backend/tests/research/test_pra_arm_compose_config.py`, `.github/workflows/agent-ci.yml`).
- **Elasticsearch `8.19.26` Guava CVE Compatibility Audit**: Verified against `docker.elastic.co` that `8.19.26` is the newest official `8.19.x`/`8.x` patch release (`9.5.x` is an incompatible major bump); documented `CVE-2026-102554` (`GHSA-xxph-c9ww-hj94`) unreachability and retained explicit Draft Release sign-off status.
- **Version & Evidence Alignment**: Documented explicit version mapping (`Release v1.0.0` Draft, `frontend 1.0.0`, `FastAPI OpenAPI 0.2.1`, `Elasticsearch 8.19.26` / local `8.19.23`, default `SCHOLARLENS_PRA_ARM=A`) across `README.md`, `CHANGELOG.md`, and `docs/release-v1/*`.

### Engineering & Infrastructure Closure (PR #47)
- **ASCII Worktree & Launcher Compatibility (`infra/start-backend1.ps1`)**: Added `.venv/Scripts/python.exe` fallback alongside `backend/.venv/Scripts/python.exe` so isolated ASCII worktree deployments and restart integration tests execute cleanly on Windows without Chinese-path JVM/GBK encoding issues.
- **Elasticsearch 8.19.23 / 8.19.26 Parity**: Updated isolated ES version assertions in backend integration tests to validate pinned patch versions `8.19.23` and `8.19.26` uniformly.
- **CI/CD Verification Expansion (`.github/workflows/agent-ci.yml`)**:
  - Included all 5 V9 regression test suites (`test_v9_*.py`) in the `verify` job.
  - Added dedicated `integration` job running live isolated **Elasticsearch 8.19.26** (859 papers imported from `data/paper_jsonl/papers_final.jsonl`) and **Jaeger all-in-one 1.60** OTLP trace collection, exporting `integration-counts.json`, JUnit XML, and `jaeger-ci-receipt.json`.
  - Extended `image` job (`standard` and `pdf-ocr`) with **Syft v1.57.2** SPDX SBOM generation and live Compose **Standard ↔ PDF OCR upgrade/OCR extraction/rollback** acceptance tests.
  - Added `security` job running **Gitleaks v8.30.1** full git history secret scan, `pip-audit`, and `npm audit`.
- **Operations & Release Governance (`docs/release-v1/`, `infra/.env.example`)**:
  - Documented full backend acceptance, ES 8.19.x acceptance, Docker Compose Standard & PDF OCR acceptance, SQLite backup/restore/rollback drills, per-CVE security triage, live/controlled model verification, Operations Runbook, User Guide, and Release Readiness Gate.
  - Preserved default online retrieval policy `SCHOLARLENS_PRA_ARM=A` (V9 `R` opt-in).

---

## [V9] — 2026-11-24 (Gemini EvoResearch Research Intelligence H1–H5)
- Merged PR #45 & PR #46 into `main`: Question Plan DAG skeleton pinning (`H5`), Research Profile structured extraction & author-vs-prior discourse attribution (`H1`/`H2`), Open Relations & Pairwise cross-paper reasoning (`H3`), Retrieval Budget & Gap Controller (`H4`), and verified `deepseek-v4.1-flash` 9/9 live acceptance (`R`).
- Preserved all 859 formal paper assets (`data/paper_jsonl/*`, `scripts/*`).

## [E11 / PRA / Final Product Delivery] — 2026-11-22
- Merged PR #42–#44: E11 Research Workbench, PRA baseline (`G`), Paper Research Profiles, Evidence Graph, PDF layout/table/chart/legend OCR container (`pdf-ocr`), OTLP/Jaeger trace integration, Evolution Lab governance viewer, and SQLite backup/restore protections.

## [V2 / V2.1] — 2026-10-27 to 2026-11-03
- Delivered 859-paper BM25 + MiniLM ONNX RRF hybrid search, SQLite accounts/workspaces/folders/history, moderated PDF uploads, DOCX conversion, and grounded RAG citation verification.
