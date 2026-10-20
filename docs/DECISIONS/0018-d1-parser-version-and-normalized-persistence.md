# 0018 — D1 parser version and normalized persistence (Phase 4 S3)

## Status

Implemented on `phase-4/normalized-persistence-s3` (risk class H, `slice_kind: tooling`,
`declared_gate: final`), base `b0bb33ac6c471fed759f33555dc4b681876a8927` (`Q` of the
Phase 4 S2c merge). Not merged.

The contract is the implementer's consolidated S3 proposal as amended by Sol Medium's
single consolidated proposal review (binding amendments A1–A6) and the user's
implementation clarifications. This ADR changes nothing in ADR 0011, 0013, 0014, 0015,
or 0017.

## Context

ADR 0011 left two binding preconditions on the first persisted Phase 3 classifier result:
D1 (a deterministic parser-version identifier bound to every implementation, taxonomy,
and configuration input, with missing or unresolvable evidence preventing the write) and
D2 (executable realistic-output protection). ADR 0014 satisfied D2 at the pure
`normalize_posting` boundary; ADR 0015 mapped Greenhouse fields into `PostingInputs`;
ADR 0017 ran the bounded live canary. Before S3, nothing called the composition at
runtime, nothing wrote `jobs.field_provenance` or `raw_job_ingestions.parser_version`, and
no normalized `jobs` column had a writer.

## Decision

### 1. Scope

S3 persists exactly three normalized values, the components ADR 0014's D2 covers, and
their provenance:

| `NormalizedPosting` component | `jobs` column |
|---|---|
| `employment_type` | `employment_type` |
| `seniority` | `seniority` |
| `location.country` | `country` |

Excluded: `normalized_title`/`job_family` (title is smoke-only evidence), `remote_type`,
`years_experience_min`/`max`, `city`/`state`/`postal_code` (unproven or zero coverage),
skills (no `job_skills` table; would need a migration), and every salary and compensation
column (no reviewed input exists). No schema change and no migration.

Normalization is **opt-in**: `pipeline.run(..., normalization=None)` keeps Phase 2's
behavior exactly. Only jobs whose `provider` and `source` are both `greenhouse`, from a
verified `GreenhouseJobBoardProvider`, are normalized; every other job is raw-only.
Nothing in the application builds a context, registers a provider, or schedules a run.

### 2. D1 manifest and parser version (A2)

`app/ingestion/normalization_version.py` builds a canonical manifest (schema
`jgnorm-v1`); the parser version is `jgnorm-v1:sha256:<hex>`, the SHA-256 of the
manifest's canonical JSON (sorted keys, compact separators, ASCII escapes, no NaN).

- **Application closure.** Every `app.*` module reachable by import from the roots
  `app.ingestion.normalized_fields`, `app.providers.greenhouse`, and
  `app.providers.greenhouse_record`, found from each module's syntax tree (all import
  statements, including function bodies), plus parent package `__init__.py` files. At
  the base it is 24 modules: the seven composed parsers, `taxonomy`, `types`, and
  `posting`; the whole Greenhouse adapter, the content converter, the bridge, and the
  record semantics; `discovered_job`, `identifiers`, and `provider` schemas; the two S3
  modules; and five package initializers. Each is identified by the SHA-256 of its UTF-8 bytes with CRLF and lone CR
  normalized to LF -- not a Git blob or commit hash, so unrelated repository changes and
  checkout line endings never alter it. A relative import, a dynamic import
  (`importlib`, `__import__`), an unparsable file, or an unresolvable `app.*` module fails
  closed.
- **Standard library.** Bound collectively through the interpreter implementation and
  complete version, not hashed per module.
- **Third-party.** Every other top-level import in the closure must be declared, and its
  exact installed version is recorded: `yaml` (plus the exact loader class hierarchy the
  taxonomy loader uses), `pydantic`, `pydantic_core`, and `httpx` (reached through the
  adapter). An undeclared dependency fails closed.
- **Taxonomy.** The canonical *parsed* content the parsers consume: every
  `(lookup key, canonical_id, display_name)` triple of the loaded index, sorted. Comment
  or formatting edits do not rotate the version; any change to what a parser can match
  does. The file is re-read after loading and must be unchanged, and every file in
  `app/taxonomy/` must be declared.
- **Runtime.** Python implementation, complete version including micro, and the Unicode
  database version.
- **Configuration.** The provider and its board -> content-mode snapshot (§4).
- **Staleness.** The first real-disk identity of each closure file is pinned per process;
  a later build that sees different bytes fails closed.

Excluded from the closure, so their edits never rotate the version: the persistence and
pipeline code, `salary.py`, `url.py`, models, and the API.

**Conservative adapter binding (correction 2).** `app/providers/greenhouse.py` is bound
whole, transport and retry code included. It still owns the association between a
response, the board it was requested for, and the jobs the provider returns
(`_discover_board`, the token passed to `parse_body`, `_aggregate`, and the snapshot
property), and that association decides which boards, content modes, descriptions, and
records reach persistence. Until a future, separately reviewed boundary can bind that
association independently, any adapter edit -- including a transport-only one --
rotates the combined normalization version. Over-binding is the deliberate trade-off:
it costs unnecessary version changes, never an unbound output-affecting change.

### 3. Unforgeable, verified context (A1)

- `build_normalization_context(content_modes)` builds and validates the manifest and
  returns a `NormalizationContext`. Its constructor rejects any caller without the
  builder's private authority; the object is immutable.
- `pipeline.run` calls `verify_normalization_context(context, provider)` as its first
  action, before any `CollectionRun` row, provider call, or database work. It requires a
  genuine `NormalizationContext`, independently rebuilds the manifest from the current
  repository, runtime, taxonomy, and configuration, and requires the canonical bytes, the
  version, the version-to-manifest hash, the parsed taxonomy content of the context's own
  taxonomy object, and the provider's own snapshot all to match. Any forged, incomplete,
  stale, or mismatched context raises.
- Only verification creates a `VerifiedNormalization` (private authority again).
  `persist_posting` accepts nothing else -- not a context, not a version string.

These guards stop ordinary misuse. They are not a defense against hostile in-process
code, which can bypass any Python-level check.

### 4. Board/content-mode binding (A3)

`GreenhouseJobBoardProvider.board_content_modes` is a read-only snapshot of each
configured board token and its declared content mode. The context binds that snapshot
into the manifest, so a configuration change rotates the version. Only
`declared-double-escaped` is approved for normalization: a snapshot containing any other
mode (including `disabled`) cannot be built. Verification requires the run's provider to
expose a snapshot equal to the context's; a provider named `greenhouse` without one fails
closed. Each job's `source_tenant_id` must be a board in the verified snapshot with an
approved mode, or the projection raises.

Every application semantic that decides a job's values was extracted unchanged from
`greenhouse.py` into `app/providers/greenhouse_record.py` (correction 1 completed the
extraction); correction 2 additionally binds the adapter itself, as above:

- board configuration (`GreenhouseBoard`) and `GreenhouseBoardSet`, the single source of
  both the snapshot verification binds and the board (token, company, content mode) each
  job is built with;
- response decoding and JSON parsing, and extraction of the `jobs` array;
- record validation and duplicate selection;
- the content-mode gate in front of the converter, and `DiscoveredJob` construction.

The adapter passes only a board token and the response body to
`GreenhouseBoardSet.parse_body`, and its snapshot property only returns the board set's.
It reads no content mode, decodes nothing, and constructs no job; a test pins this. It
still owns the network and is still the only importer of `httpx`. Existing importers of
`GreenhouseBoard`, `GreenhouseConfigurationError`, `_validate_record`, and
`_duplicate_identity` from the adapter, including the frozen S2c harness, are served by
explicit re-exports.

### 5. Write path and transaction (A4)

Transaction A (the raw row) is unchanged. `persist_posting` computes the projection from
`job` itself before its transaction opens, holding no lock; a parser or binding exception
propagates, Transaction B never begins, the raw row stays `fetched`, and the run is marked
`failed` and re-raised (accepted decision: any normalization failure aborts the run).
Earlier postings in the run have already committed, as in Phase 2.

On a clean `INSERTED`/`UPDATED`/`ATTACHED` outcome, Transaction B re-selects the
destination `Job` with `SELECT ... FOR UPDATE` and `populate_existing`, merges the
projected fields under that lock, sets `raw.parser_version`, and commits the status,
link, version, values, and provenance together. Lock order is unchanged: resolution
already locks the parent `Job` before touching its occurrences, and the re-select takes
the same row lock again. Both conflict outcomes (`evidence_mismatch`, `ambiguous_match`)
write no normalized value and leave `parser_version` unset, exactly as in Phase 2.

`raw.parser_version` is set whenever normalization ran and its result was applied, even
when every field abstained or the merge kept every existing value.

### 6. Provenance entry and merge rule (A5)

Each written field gets one `field_provenance` entry, replaced whole (never mutated in
place):

```json
{"source": "<provenance>", "provider": "greenhouse", "provider_source": "greenhouse",
 "occurrence_id": "<uuid>", "raw_job_ingestion_id": "<uuid>",
 "parser_version": "jgnorm-v1:sha256:...", "observed_at": "<ISO-8601>"}
```

The precedence rule, per field, under the `Job` row lock:

1. `unavailable` never writes, so an abstention never erases.
2. An incoming `explicit_source` or `structured_metadata` tag raises: no composed parser
   can state either.
3. No existing value and no entry: write.
4. A value without an entry, an entry without a value, or an entry that is malformed,
   carries an unknown tag, or comes from another provider: raise and abort, never
   overwrite.
5. Trust order `explicit_source > structured_metadata > parsed_description > derived >
   inferred`: higher trust replaces; lower trust is kept.
6. Equal trust: a strictly later `observed_at` replaces and an earlier one is kept. At
   an equal instant, an identical value is a no-op (a rerun is idempotent) and a
   differing value is refused and aborts the run, whatever the parser versions. A parser
   version is evidence, never an ordering signal: its hash carries no chronology, so it
   never decides which of two equal-time results wins, and the same version producing
   two values at one instant is surfaced rather than masked. A corrected parser result
   replaces an equal-trust value only through a later observation (correction 1).

S3 has exactly one normalized provider. Cross-provider priority is **not** implemented;
entries from any other provider are rejected. Enabling a second normalized provider
requires a separately reviewed provider-priority policy before activation.

### 7. D2 at the write path (A6)

The primary proof runs the 30 reconstructed corpus envelopes through the real
`GreenhouseJobBoardProvider` over `httpx.MockTransport`, the unchanged bridge and
composition, and `pipeline.run`, then reloads PostgreSQL in a fresh session and asserts
that the set of non-null persisted values for each covered component equals ADR 0014's
committed `CORRECT` literal exactly (10, 18, and 5 records), that every other record is
`NULL`, that every unpersisted normalized column stays `NULL`, that provenance equals the
emitted tag (including the three L5 `location.country` exceptions), and that raw payloads
and hashes are exact. A rerun is idempotent, and a legitimately newer version (a real
configuration change through the real builder) is a no-op at the same instant and
replaces only through a later observation, per §6. A covered-output regression fails this
persisted check itself.

## Bounded claim

> S3 satisfies ADR 0011 D1 for the three persisted fields (`employment_type`, `seniority`, `location.country`) on the opt-in, offline, fixture-driven Greenhouse path: every persisted value is traceable to its preserved raw input, a verified parser version bound to the declared code, dependency, taxonomy, runtime, and board-configuration evidence, and its provenance; missing or mismatched evidence prevents the write. Persisted values for the covered components equal ADR 0014's D2 literals for the exposed 30-record corpus through the real offline adapter path. This does not establish accuracy or generalization beyond that corpus, any unproven component, live or scheduled ingestion, a second provider, runtime activation, or production readiness.

## Retained limitations

- Python-level guards stop misuse, not hostile in-process code.
- The manifest identifies on-disk source; the per-process pin detects source changes
  after the first build in a process, not an edit between import and that first build.
- The whole Greenhouse adapter is bound, so transport-only edits (retries, backoff,
  timeouts, diagnostics) also rotate the parser version.
- Third-party binding covers packages the closure imports directly, not their own
  transitive dependencies.
- An abstention never retracts a value: after a parser change, an older value stays
  (still traceable to its own version and raw input) until a replacing write. No backfill
  or re-normalization tool exists.
- An equal-time conflict between equal-trust results is refused and aborts the run; it
  is not resolved automatically. A corrected value needs a later observation.
- The explicit `FOR UPDATE` re-select is defense in depth: resolution already holds the
  same lock, so the concurrency test proves the serialized outcome but cannot isolate the
  re-select.
- `raw_content_hash` is not used to skip re-normalization; every re-ingestion
  re-normalizes deterministically.
- The committed S2c projected record abstains on all three persisted fields, so its
  replay proves the offline adapter-to-database path, not values. Value evidence comes
  only from the exposed, reconstructed synthetic corpus envelopes (ADR 0015).
- A rejected existing entry (rule 4) aborts the run rather than skipping the field.

## Exclusions

No provider contact or new captured data; no registry, composition-root, scheduler, or
runtime activation; no API or UI; no S4 or S5; no additional normalized fields; no
salary; no schema or migration change; no parser, taxonomy, corpus, or D2-module change;
no workflow-tooling change.

## Consequences

- The first normalized write path exists, opt-in and offline, with D1 evidence on every
  write.
- Adding a persisted field, a provider, or a content mode is a reviewed change: a new
  field changes the projection (and the version); a second provider needs a
  provider-priority policy first.
- S4 can read three normalized fields with traceable provenance. S5 must decide when
  production ingestion builds and passes a context.
