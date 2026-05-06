# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [0.8.0] - 2026-05-06

### Added
- `CveScan` and `CveResult` SQLAlchemy models (`bmu.models.cve_scan`).
- Alembic migration `0004_cve_tables` creates `cve_scans` and `cve_results`
  tables with appropriate foreign keys and cascade rules.
- Recorder `_record_cve_scan()`: writes one `CveScan` row (with CPE string,
  version found, and scan timestamp) plus one `CveResult` row per CVE entry
  returned by the NVD API.
- `cpe` field added to `JobResult` so the recorder can store the exact CPE
  string used for the NVD query without reconstructing it.

---

## [0.7.0] - 2026-05-06

### Added
- `bmu.cve` package: `CveClient` ABC, `CveEntry` dataclass, and
  `NvdCveClient` implementation querying the NVD REST API v2.0.
- `query_cpe(cpe)` facade in `bmu.cve.__init__` — single entry point called
  by the worker; selects the NVD backend automatically.
- `nvd_api_key` setting (optional, env `BMU_NVD_API_KEY`): raises the NVD
  rate limit from 1 req/s to 5 req/s when provided.
- CVSS v3.1 / v3.0 / v2 score and severity extracted per-CVE; first English
  description used as summary; first reference URL included.

---

## [0.6.0] - 2026-05-06

### Added
- `cve_vendor` and `cve_product` fields on `Profile` for future CVE scanning
  support via the NVD API. Values act as CPE hints (e.g. `cisco` / `ios_xe`).
- Alembic migration `0002_profile_cve_fields` adds the two columns to the
  `profiles` table.
- CVE vendor and product inputs on the profile create/edit form.
- `ROADMAP.md` describing the planned CVE detection feature, including fuzzy
  version matching with operator-visible confidence scores.
- `CVE_SCAN = "cve_scan"` added to the `JobKind` enum.
- Alembic migration `0003_cve_scan_job_kind` adds `'cve_scan'` to the
  `job_kind` Postgres enum via `ALTER TYPE ... ADD VALUE`.
- `cve_vendor` and `cve_product` fields on `JobSpec`; `cve_entries` field on
  `JobResult` for carrying CVE query results through the pipeline.
- `_run_cve_scan()` in the worker: runs CLI commands, parses output (identical
  to `collect`), builds a CPE string from the parsed version + profile vendor/
  product, and delegates to `bmu.cve.query_cpe` (stubbed until Phase 3).
- Scheduler `_spec_for` now populates `cve_vendor` and `cve_product` on the
  emitted `JobSpec`.
- `cve_scan` appears in the Schedule kind dropdown automatically (the form
  iterates `[k.value for k in JobKind]`).

---

## [0.5.0] - 2026-05-06

### Added
- Bulk actions on all resource list pages (Devices, Groups, Profiles,
  Credentials, Schedules).
  - Select-all checkbox in table header; per-row checkboxes.
  - Bulk delete for all five resources.
  - Bulk edit for Devices: Port, Group, Profile, Credential override, and
    Enabled — leaving a field blank skips it for each selected device.
- `POST /resource/bulk` route handler for each resource.
- CSS additions: `form.table-form` resets grid layout for table-wrapping forms;
  `.bulk-edit-panel` provides the grid for the device bulk-edit fields;
  `.toolbar` converted to flexbox for correct alignment.

### Changed
- Per-row delete buttons across all list pages switched from nested `<form>`
  elements to `formaction` attribute overrides on buttons inside the outer
  bulk form (HTML does not allow nested forms).

---

## [0.4.0] - 2026-05-06

### Added
- `scrapli-community` dependency (`>=2025.1.30`), enabling 30+ additional
  network platform drivers (Huawei VRP, Aruba AOS-CX, Fortinet, Nokia, etc.).
- Platform dropdown on the profile form now groups options under **Core** and
  **Community** `<optgroup>` labels. The two sets are mutually exclusive.
- Community platforms discovered automatically by scrapli at runtime — no
  changes to the worker execution path required.

### Fixed
- Worker was passing `asyncssh` as the transport to the synchronous `Scrapli`
  factory, causing a `ScrapliValueError` on every non-telnet CLI connection.
  Changed to `system` (OpenSSH subprocess), which is the correct sync transport.

---

## [0.3.0] - 2026-05-06

### Added
- pytest test suite for the worker (`tests/worker/`): 69 tests, all passing.
  - `TestBuildCliDriver` — driver class selection, all connection kwargs.
  - `TestRunCli` — command sequencing, backup/collect modes, parser integration,
    driver lifecycle, success/failure propagation.
  - `TestRunNetconf` — RPC execution, error handling, parser, result fields.
  - `TestExecute` — dispatcher routing and unknown kind error.
  - `test_parsers` — TextFSM, TTP, and XSLT backends including error cases.
- `pytest`, `pytest-mock`, and `pytest-cov` added as dev dependencies.
- `[tool.pytest.ini_options]` section in `pyproject.toml`.

---

## [0.2.0] - 2026-05-06

### Added
- Full CRUD (edit, update, delete) for all web-managed resources: Devices,
  Profiles, Credentials, Schedules, and Groups.
- Edit and delete actions on all list pages (Actions column with per-row
  edit link and inline delete form with confirmation dialog).
- Dual-mode form templates: fields pre-fill from the existing record when
  editing; form `action` and submit button label adjust accordingly.
- Credential edit form uses `type="password"` for password fields and
  preserves the existing encrypted payload when password inputs are left blank.
- Edit and delete toolbar on the Group detail page.
- CSV bulk import for Devices (`POST /devices/import`) with file upload or
  paste, downloadable template, and per-row result reporting.

### Fixed
- SQLAlchemy enum columns were sending enum names instead of values to
  Postgres (e.g. `CLI` instead of `cli`). Fixed by adding
  `values_callable=lambda e: [m.value for m in e]` to all `SAEnum` usages.

---

## [0.1.0] - 2026-04-29

### Added
- Initial BMU MVP scaffold.
- Five microservices in one Docker image: `web`, `scheduler`, `worker`,
  `recorder`, `migrate`.
- PostgreSQL for state, Redis Streams for job and result queues.
- Core models: `DeviceGroup`, `Device`, `Profile`, `Schedule`, `Credential`,
  `Run`, `ParserTemplate`.
- CLI profiles: scrapli-based execution with support for known platforms and
  `GenericDriver` fallback (custom prompt pattern, pre-commands, paging).
- NETCONF profiles: raw RPC XML execution via scrapli-netconf.
- Parser pipeline: TextFSM, TTP, and XSLT output normalization.
- Credential providers: local (Fernet-encrypted), HashiCorp Vault, Bitwarden.
- Scheduler: cron-based job dispatch with Postgres advisory lock for
  single-leader election.
- Recorder: commits captured configs to a versioned git repository.
- Web UI: Litestar + Jinja2 + HTMX; create forms for all resources; dashboard
  with run history; runs list.
- Alembic migration `0001_initial` for full schema.
