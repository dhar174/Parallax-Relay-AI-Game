# Run provenance

The main recorder adds `manifest.provenance.schema_version = 1` inside the existing
version-2 manifest. Results, call/phase/turn records, engine behavior, and the replay
data shape retain their existing versions. Provenance is spectator information:
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

The room fingerprint covers named geometry/item/deadline constants, sorted gap
coordinates, private objective definitions, and the actual initial world snapshot.
It is an identity for the current fixed room, not a general room registry. Prompt
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
input identities together only after collection succeeds. A failed begin hook or
collector leaves `initialized` with null identities, execution times and lifecycle
stop reasons; result/HTML output still records the local failure. The recorder is
claimed before the begin hook and cannot be reused after failed setup.

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

`read_provenance(manifest)` returns a detached dictionary for supported version-1
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
