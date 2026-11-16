# Run provenance

New runs use manifest/result/provenance/request version **3**. Call/phase/turn
records retain their compatible field structure; room snapshots carry room ID/version
and canonical per-controller/bridge/cell state. Provenance is spectator information:
it includes room/objective identities and never belongs in a player request.

## Identity and effective configuration

| Field | Meaning |
|---|---|
| `run_id` | Fresh UUID for this recorder, independent of the output directory name |
| `experiment_id`, `trial_id` | Optional declared UUIDs; null for ordinary runs |
| `source` | Git revision and `clean`, `dirty`, or `unavailable` status with a fixed availability reason |
| `environment` | Fingerprinted Python implementation/version, OS/release/architecture, and sorted distribution names/versions |
| `players` | Per-role declared provider/model, identity availability, implemented API contract, unknown model revision, sampling/seed status |
| `requested_settings` | Declared settings after CLI overrides but before the mock dollar-cap override; populated for both CLI modes, or null when not supplied programmatically |
| `execution` | Fingerprinted configuration supplied by the driver: actual settings/pricing, declared players/mode, effective input conditions |
| `inputs` | Fingerprinted system prompt, request/response/local validation contracts, and room definition/initial state/objectives |
| `lifecycle` | Creation/start/end UTC times, execution duration, stage, original execution stop, and current final stop |

Each fingerprint is `{ "value": <canonical input>, "sha256": <digest> }`. Its
digest covers UTF-8 JSON with sorted object keys, compact separators, ASCII escapes,
and non-finite numbers rejected. It excludes the digest itself. Validated settings
and prices normalize TOML representations before hashing. Configuration comments,
credential values, credential-variable names, and configuration file paths are not
part of effective identity. Requested settings are distinct from effective settings:
a valid priced CLI mock can request a dollar cap but execute with that cap null.
All other limits and prices remain intact.
The legacy top-level `manifest.requested_settings` is still mock-only; the
provenance field also records live requested settings, with its dollar cap intact.

The room fingerprint covers the embedded validated room definition, catalog and
certificate hashes, private objectives and actual initial snapshot. Definitions
include family/split, geometry/resources, scoring version and curated/null generation
metadata. The full catalog is frozen in campaign registrations. Prompt
and schema identity include actual static rules, a synthetic request structure,
`REQUEST_FORMAT_VERSION`, wire schemas, local Pydantic schemas, and reply limits.
Bump the request format version when its meaning changes; record new identities
when prompts, contracts, room rules, or objectives change. Git revision identifies
implementation code; these fingerprints alone do not attest every line of code.

Git is probed at the package checkout root before creating output. An unrelated
parent repository is not used as source identity. Read-only probes have a one-second
timeout each. Missing Git, failed probes, and archives are represented as unavailable;
known revision information is retained when only status collection fails, including
a timeout. Probe environments discard inherited `GIT_*` overrides, restore only
`GIT_OPTIONAL_LOCKS=0`, and disable filesystem-monitor commands. A dirty
run records its base revision and dirty status, not its patch or an exact dirty-code
snapshot. No remote URL, branch name, author, hostname, or absolute local path is
recorded. Installed package metadata contributes only names and versions, never
direct-install URLs, descriptions, or a raw `pip freeze`. Partial inventory has an
explicit `partial`/`unavailable` status. OS images, fonts, and package contents are
not pinned or attested; role PNGs remain the actual saved visual evidence.

## CLI and programmatic use

```bash
python -m parallax_relay.play --mock --out runs/fresh-trial \
  --experiment-id 24c12c08-5c64-4a29-b8ea-3b09cd123964 \
  --trial-id b81b3e0a-61cc-45fd-83c6-f871291c98af
```

Use a fresh destination. IDs label a single match; they neither start a campaign
nor resume a prior match. Invalid UUIDs fail safely with exit 2 before output is
created. `--check` still creates no recorded run.

Existing `Recorder(out, manifest)` and `run_match(...)` calls remain valid. The
driver supplies actual settings, prices, and initial state to built-in Recorder
hooks; stale caller-declared `manifest.settings` is replaced by actual settings.
Arbitrary agents are never inspected for keys, prompts, or implementation identity.
Without an explicit context their provider/model identity remains unknown, even
when a caller labels the legacy manifest `mode` as mock. Declare known identities
through the optional context:

```python
from pathlib import Path
from parallax_relay.provenance import PlayerIdentity, ProvenanceContext
from parallax_relay.recording import Recorder

context = ProvenanceContext(mode="mock", players={
    role: PlayerIdentity(provider="mock", model="scripted-fixture")
    for role in ("SPECTRA", "PYRA", "FLUX")
})
recorder = Recorder(Path("runs/fresh-programmatic"), {}, context=context)
# Pass recorder to run_match with your actual agents/settings/rates.
```

Context fields are explicit and validated; credential fields and arbitrary metadata
are not accepted there. Declarations are trusted caller labels, not proof that an
agent used a model or that a provider accepted the request. Declaring mock mode
does not disable a programmatic dollar guard. A Recorder belongs to one match;
reusing it through `run_match` is rejected before earlier output can be overwritten.
Custom recorders using only the previous call/phase/turn/finish interface still work.

Explicit context also supplies top-level display mode/player labels, overriding
stale legacy labels. Without context, supplied legacy labels remain display-only;
missing labels default to programmatic/unknown without inferring agent identity.
The viewer distinguishes mock, live, programmatic and unknown modes, and displays
unknown provider/model values explicitly instead of an empty roster.

HTTP provenance records requested bare model IDs, fixed endpoint/API namespaces,
and Anthropic's actual version header from shared wire constants. `model_revision`
is null: aliases and remote revisions are not resolved. Sampling is
`provider_default` because temperature/top-p/seed are omitted; mock sampling is
`not_applicable`, and custom-agent sampling is unavailable. Seeds are null rather
than invented. No deterministic provider behavior or live compatibility is implied.

## Lifecycle and recovery

`created_at` is independent of custom output paths. `begin_match` binds configuration
and starts UTC/monotonic timing immediately before gameplay. `end_match` freezes end
time and duration after cooperative attempt draining but before final artifact writes
and owned-client teardown. UTC strings have a `Z` suffix. Monotonic duration remains
valid if the wall clock changes; timestamps are not fabricated to restore ordering.

Stages are `initialized`, `running`, `ended`, and `external_result`. Construction
without a started match leaves execution timestamps null. Calling `finish(result)`
on an unrelated already-computed result records `external_result`, with unknown
execution configuration and no invented start/end/duration. Stage means the last
observed lifecycle hook, not a liveness assertion. Binding publishes execution and
input identities together only after collection succeeds. A begin-hook or collector
failure **before successful provenance binding** leaves `initialized` with null
identities, execution times and lifecycle stop reasons; result/HTML output still
records the local failure. Failures after binding, such as a running-manifest write
error, retain the known identity/start and proceed through end/recovery normally.
The recorder is claimed before the begin hook and cannot be reused after failed setup.

Initialized records have no stop reasons. External results have both stop reasons
but no execution/input identities or execution times. Ordinary running records
have no stop reasons. If an end hook fails, recovery may leave stage `running`
with unknown end/duration/original execution stop, while final `stop_reason` is
`local_error`, `internal_error` or `cancelled`. This narrow exception preserves the
actual interruption without fabricating a successful end hook. Ended records
require complete end metadata and both stop reasons.

Finalization independently attempts eight atomic artifacts: manifest, three JSONL
snapshots, result, final state, final PNG, and HTML. At most two passes occur.
Identity/start/end/duration remain fixed; `stop_reason` is refreshed for recovery,
while `execution_stop_reason` preserves the first observed pre-finalization stop.
For example, a finalization failure after victory can retain winning/completed state
and scores while final stop becomes `local_error`. Earlier primary errors and
cancellation retain precedence; raw exceptions are never serialized.

If manifest storage fails persistently, its on-disk metadata may remain at an earlier
stage while writable summaries and embedded HTML reflect current in-memory data.
Missing endpoint information is unknown, not evidence that the process is still
running. There is no cross-artifact transaction, process-termination durability, or
match-resume guarantee. Pre-match setup failure may leave only initialized metadata.

## Reading and compatibility

`read_provenance(manifest)` returns a detached dictionary for supported version-1 and version-2
records after structural, timestamp, and fingerprint validation. Validation covers
known nested settings/prices, environment, request contracts, and room
snapshots; matching a digest alone does not make an arbitrary payload valid.
Known player fields must agree with fingerprinted execution players. Provider,
sampling, declared-identity and API-contract fields must be consistent; historical
Anthropic version headers remain valid independently of the current wire version.
Robot roles match their keys, counters are nonnegative, coordinates fit the
recorded room width, and win/loss flags cannot both be true. Additive annotations
are preserved and do not participate in known-field player comparisons.
Fingerprints are identity/checksum evidence, not signatures or authenticity proofs.
Legacy manifests without the block return `None`; absent provenance means unknown identity, not a
clean or fully reproducible run. Unsupported versions and malformed records raise
a sanitized `ProvenanceError`. The function validates the provenance block, not the
rest of an arbitrary replay. Existing version-2 fixtures/viewers remain readable
without rewriting them. Optional fields may be added within this version; changed
field meanings/types require a provenance version bump and reader updates.

The exporter does not read raw TOML/`.env`, argv, credentials, Git patches, or secret
configuration to fingerprint them. Existing arbitrary caller-supplied legacy
manifest metadata remains that trusted caller's responsibility; neither a metadata
reader nor the old key-name redactor is a general secret detector. Keep credentials
out of prompts, declarations, and spectator metadata. Provenance identifies inputs
and availability limits; it does not recreate nondeterministic remote responses.

## Slice 8 condition and policy identity

Slice 8 wrote provenance version 2. Versions 1 and 2 retain frozen historical
settings/condition readers; version 3 adds `room_id` and embedded room definitions. Old checksums are validated without adding new defaults
or rewriting the record. Historical outer manifest/result version 2 remains readable.
Execution conditions identify the arm and versioned factual request notice, phase
schedule, public-message availability and image availability. The effective prompt
fingerprint includes that notice; request formats 2 and 3 include it in JSON.

Explicit offline context can declare `policy="scripted"`, `"wait"` or `"uniform"`.
Uniform requires a trial UUID and records the uniform-v1 derivation, Python/PRNG
identity and scheduled commitment seeds for every role/possible turn. Actual
commitment attempts are identified by call turn/role; retries use the same seed.
These are local policy seeds, never provider seeds. Undeclared custom policies
remain unknown. Each condition/policy changes effective identity.

## Room archive compatibility

Version-3 readers validate snapshots against the recorded definition, without
constructing a live world or looking up the current catalog. Position bounds, motor
keys, bridge/cell references, terminal flags and single-bridge aliases are checked.
Old provenance/checksums are returned unchanged: current `MatchSettings` defaults
are never inserted into v1/v2 records. Historical native fixtures and the smoke
profile-v1 digest remain intact. Campaign registration/report/analysis version 2
adds catalog/split identity; ledger envelopes stay version 1. Historical registration
version 1 is analyzable, but current execution requires fresh registration.
