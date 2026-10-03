# 0013 — Direct Greenhouse Job Board provider

## Status

Accepted with Phase 4 Slice 1 (`phase-4/greenhouse-provider-s1`, risk class H,
`slice_kind: tooling`, `gate: final`), base `2a72471b95c61b7a1a3e2ae1f944ed40036671b8`.
Its contract is the implementer's consolidated S1 proposal as amended by Sol Medium's
binding proposal review (amendments A1–A15 and explicit rulings), integrated into one
frozen contract. This is the first of the three product-oriented slices under the
Workflow Throughput Protocol pilot ([ADR 0012](0012-workflow-throughput-protocol-pilot.md)).

This ADR records a departure from the roadmap. It does not start S2–S5, wire the provider
into any runtime path, or authorize any network contact, persistence, or normalization.

## Context

[ROADMAP.md](../ROADMAP.md)'s Phase 4 header and
[PHASE_RISK_CHECKLIST.md](../PHASE_RISK_CHECKLIST.md)'s Phase 4 section assumed an
`AtsScrapersProvider` wrapping the `ats-scrapers` library.
[ARCHITECTURE.md](../ARCHITECTURE.md) §10 drew Greenhouse access through that library.
The repository evidence at the base points the other way:

- `ats-scrapers` was never added as a dependency. The Phase 4 prework (the Greenhouse
  live canary and the live-to-disposable-database proof), the Phase 3 realistic corpus
  capture, and every existing Greenhouse script call the official public Job Board API
  directly with `httpx`.
- `ats-scrapers`' `Job` model pre-normalizes salary, remote status, and location. Each
  of those values would need its own provenance classification, or would risk reaching
  storage looking like explicit-source facts.
- It carries its own retry layer and an optional browser-impersonation escalation path.
  The first would double up with the adapter's own bounded retries; the second is
  unwanted.
- Its review in [SOURCE_CONNECTORS.md](../SOURCE_CONNECTORS.md) dates from 2026-08-23.
  The checklist requires a current review.
- SOURCE_CONNECTORS already recommends a thin in-house typed client for Greenhouse's and
  Lever's public Job Board APIs.

## Decision

### 1. Direct adapter

Phase 4 uses `GreenhouseJobBoardProvider` (`backend/app/providers/greenhouse.py`),
which calls `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
directly. `ats-scrapers` is not adopted. It may be reconsidered for other ATSs only after
a fresh review.

This supersedes:

- the ROADMAP Phase 4 description of `AtsScrapersProvider` wrapping `ats-scrapers`, for
  Greenhouse;
- the checklist rule "Pin the dependency and import it only inside
  `AtsScrapersProvider`";
- ARCHITECTURE §10's Greenhouse path through `ats_scrapers`.

The checklist's intent carries over unchanged: `httpx` and every Greenhouse payload shape
stay inside `app/providers/greenhouse.py`, and external types never leak. An AST test
enforces that no other module in `app/` imports `httpx`.

### 2. Labels and identity

The provider label is `provider="greenhouse"` and the source label is
`source="greenhouse"`. `provider` is part of the natural key
(`app/ingestion/natural_key.py`), so the label is identity-bearing from the first
persistent write onward. The two labels must never be mixed for the same postings in any
persistent database.

The prework scripts (`scripts/canary_greenhouse.py`,
`scripts/live_proof_greenhouse_ingestion.py`) keep `provider="ats_scrapers"` as a
historical, non-provider record. Their data went only to disposable databases. No
non-disposable database was inspected for this decision, and S1 writes nothing.

### 3. Adapter contract (summary)

- Board tokens are lowercase slugs (`^[a-z0-9][a-z0-9_-]{0,99}$`); `company` comes only
  from configuration, never from the payload's `company_name`.
- Each board is a usable success, a partial success, or a failure. The source is
  `completed` iff at least one board is usable or partial, and `incomplete_results` iff
  it is completed and any board failed, was partial, or had failed completeness
  evidence. A nonempty response whose records are all rejected is a failure, never a
  successful empty result.
- Records with an unusable `id`, a URL outside the HTTPS boundary, or a present value of
  the wrong type are skipped. Records whose `str(id).strip(" \t\n\r")` collides within a
  board are all skipped.
- `health()` makes no network call. It stays healthy while at least one board produced a
  usable outcome, and turns unhealthy only when none did.
- One fresh transport and one client per `discover()` call, `trust_env=False`,
  `follow_redirects=False`, sequential boards, a closed timeout and retry taxonomy
  (only 429/502/503/504, timeouts, and connect errors are retried), bounded
  `Retry-After`, and a streamed response-size cap. The conservative default bound is 225
  seconds per board; it is not a tight timing guarantee.
- The provider is not registered or reachable from any runtime entry point.

### 4. Raw payloads and logging

`DiscoveredJob.raw` is a deep copy of the whole parsed record, including unknown fields
and the HTML `content`. Byte identity is impossible once JSON is parsed; the guarantee is
structural equality and an equal `canonical_json_hash`. The adapter has no logger, and
every error detail, warning, and raised message is a fixed categorical template that
never contains a response body, record field, exception text, or URL query. `httpx`'s own
INFO request line records the request URL, which contains only a public board token and
`content=true`.

HTML content may contain recruiter contact details. In S1 it exists only in memory.
Storage policy belongs to later, separately authorized slices.

### 5. Salary

Salary is excluded. The adapter reads, composes, infers, and claims nothing about salary,
`compensation_text` is always `None`, and `pay_transparency` is never requested. ADR
0011's limitation L4 stays explicitly unproven.

### 6. Runtime dependency evidence

- **Normative pinned direct dependency:** `httpx==0.28.1` (BSD-3-Clause), moved from the
  `dev` extra to runtime dependencies in `backend/pyproject.toml` with the same pin.
- **Observed resolved transitive closure.** Derived from installed `Requires-Dist`
  metadata in the project virtualenv (CPython 3.12.13, win32, environment markers
  evaluated), not from a manually assumed list:

  | Package | Observed version | Declared license | Required by |
  |---|---|---|---|
  | httpcore | 1.0.9 | BSD-3-Clause | httpx (`httpcore==1.*`) |
  | anyio | 4.14.2 | MIT | httpx |
  | h11 | 0.16.0 | MIT | httpcore (`h11>=0.16`) |
  | idna | 3.19 | BSD-3-Clause | httpx, anyio (already a pinned runtime dependency) |
  | certifi | 2026.7.22 | MPL-2.0 | httpx, httpcore |
  | typing-extensions | 4.16.0 | PSF-2.0 | anyio (`python_version < "3.13"`) |

  `exceptiongroup` is excluded by its `python_version < "3.11"` marker, and every
  optional extra is excluded.
- **Transitive versions are not project-pinned.** The project has no lockfile, so the
  versions above are what was observed, not what is guaranteed.
- **Licensing.** certifi declares MPL-2.0 and is used unmodified. Applicable license,
  notice, and distribution obligations for the covered package must be preserved; this
  record is an engineering inventory, not legal advice.
- **Online advisory review.** Separately authorized by the user before the S1 advisory
  candidate. On 2026-10-03 (UTC), one read-only query per exact PyPI package and version
  was sent to OSV (`https://api.osv.dev/v1/query`), with no credentials. `pypi.org` was
  not queried. Result: **zero advisories** for all seven packages (httpx plus the six
  above). The evidence is a gitignored runtime file,
  `.claude/runtime/phase4-s1-dependency-advisory-evidence.json`, SHA-256
  `527cdae0f0f244eb6869842b81041d8d2dfd4ffa837dfedf1eb2b951056830e0`. It is a
  point-in-time check, not a continuing guarantee.
- **Removal path.** Remove `httpx` if the Greenhouse adapter is retired, or reimplement
  the adapter on stdlib `urllib` plus `asyncio.to_thread` or another reviewed client.

### 7. ADR 0011 boundary

S1 satisfies neither D1 (parser version) nor D2 (executable realistic-output protection)
of [ADR 0011](0011-phase-3-exit-audit.md) and authorizes no normalized write. Raw
acquisition or storage does not authorize normalized persistence. `title` and
`location.name` are copied verbatim into existing `DiscoveredJob` fields; this is
provider-contract mapping, not parser-input mapping. No parser is called, and HTML
content is not converted (`description` is always `None`).

- D2 must be satisfied before the first provider-to-parser mapping slice.
- D1 must be satisfied before the first normalized persistence slice.

### 8. Live contact

Live Greenhouse contact is deferred to S5. Before it can be enabled:

- an Astra escalation review (live-provider risk);
- a review of Greenhouse's Job Board API terms of use, which has never been done;
- a reviewed real `content=true` response capture as a contract fixture (S1's tests use
  synthetic Python envelopes and one sanitized, allowlisted, derived sample of a single
  real job entry, which is not raw, structure-complete, envelope, or `content=true`
  evidence);
- a kill switch that is off by default.

## Five-slice plan

| Slice | Content | Class / gate |
|---|---|---|
| S1 | offline adapter plus this ADR | H / final |
| S2 | pure `normalize_posting` composition, HTML conversion, D2 protection, no write | H / final |
| S3 | D1 version, normalized/provenance write path, merge rule | H / final |
| S4 | read-only `GET /jobs`, `GET /jobs/{id}` | R / final |
| S5 | live enablement (separate network authorization; Sol plus Astra) | H / final |

Only S1 is authorized. Each later slice needs its own proposal and authorization.

## Consequences

- `httpx` becomes a runtime dependency, confined to one module.
- Greenhouse postings will carry `provider="greenhouse"` once they are persisted.
- The Phase 4 exit gate (a real Greenhouse job through the complete pipeline into
  PostgreSQL) is not met by S1; it is expected at S5.
- `AtsScrapersProvider` remains only a historical design name for Greenhouse. Other ATSs
  have no adapter yet.
