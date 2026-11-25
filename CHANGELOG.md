# Changelog

All notable engineering and research milestones for **ScholarLens EvoResearch** are documented in this file.

## [v1.0.0-rc.1] — 2026-11-25 (Final Engineering Closure & Release Candidate)

### Engineering & Infrastructure Closure
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
