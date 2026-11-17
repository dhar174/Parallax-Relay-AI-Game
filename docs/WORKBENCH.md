# Parallax Relay workbench

The [private workbench](https://parallax-relay-lab.dhar174.chatgpt.site) is the browser interface for development-room experiments. Build it from the same checkout as the engine so that its configuration form, offline runner and replay viewer track repository changes. There are three active roles in Milestone 2. See [the player protocol](PROTOCOL.md) and [the running guide](RUNNING.md) for the game and CLI contracts.

## Build and run locally

Activate the repository's Python environment using [the dependency setup](../CONTRIBUTING.md#environment). From the repository root, run:

```bash
python site/build_workbench.py
python site/relay_workbench.py
```

Open the `http://127.0.0.1:<port>` URL printed by the companion. The port is assigned for each launch. On Windows or WSL, open that URL in your browser while the Python process is running. Select **Offline execution → Run offline through Python** to invoke the real `parallax_relay.play --mock` CLI. Use **Load repository fixture** to view the committed seven-turn recording. The smoke preset runs one turn, which should end with `turn_limit` and no terminal scores.

The build regenerates the ignored `build/workbench/dist/` directory. It contains the static Site, native example replay and `relay-workbench.zip`. The ZIP is the portable companion offered on the hosted Site. Extract it and run its `relay_workbench.py` by absolute path from the game checkout root. The companion compares a fingerprint of the package's Python/HTML files, default TOML, named smoke profile and launcher to those used at build time. Documentation-only commits can use the same companion. Rebuild after runtime changes. The build records the project-root Git revision and a clean/dirty/unavailable status. Git-less archives remain usable and show unavailable source identity; an unrelated parent repository is never attributed to the game. Publish from a clean, committed revision with locked dependencies. ZIP entries use fixed timestamps and file modes, with a root LICENSE, so identical build inputs and compression tooling produce identical archives.

Generated runs use temporary storage. Download **Export complete JSON** from Evaluation to keep the record, including images. To keep the native files separately, export the workbench TOML and invoke the CLI as described in the running guide. Import its output folder with **Evaluation → Import run folder**.

Imports accept well-formed native schema-version-2 and version-3 records. Version 3 validates recorded room geometry and snapshot references before replacing the current run. Invalid fields are reported before replacing the selected run, so its evaluation and exported data remain available after a rejected import. Empty logs, incomplete runs, missing optional images and additional metadata such as provenance remain supported. Folder imports preserve `final_spectator.png` along with turn images and reject duplicate accepted image filenames. PNG bytes are signature-checked and encoded independently of browser MIME metadata. File selections reset after each attempt so a corrected file can be selected again. The latest load intent wins, and background completions do not replace an active configuration form. Programmatic and unknown-mode records can omit the room label; exports retain their original metadata.

Evaluation shows the final spectator image when available and the final world JSON.
Rounds without replay records expose their calls and completed phases. Matching
result and final-state turn counts distinguish missing resolved records from an
unfinished round; inconsistent or unavailable counts, a replay row beyond that
checkpoint, or later evidence after a terminal checkpoint leave resolution unknown.
A commitment in a confirmed unfinished round is not applied. Call/phase turn
numbers are zero-based and resolved rounds are one-based. Phase objects without a
usable turn remain visible separately. Engine
outcome and scores remain separate from the operational stop reason. The import
validation and complete JSON export retain their existing data and schema versions.

## Focused frontend verification

With the repository's Python environment activated and Node.js 24 available:

```bash
python site/build_workbench.py
node --check site/web/app.js
node --check site/web/contracts.mjs
node --test --test-concurrency=1 tests/test_workbench_web.mjs
```

No npm packages are needed. The Node tests execute the production modules and import/click handlers with minimal browser I/O substitutes. They check validation and preservation of the selected run, image roundtrips and native CLI incomplete output. They also cover numeric badInput, approval invalidation, Python-validated TOML exports, programmatic records, escaped model text and overlapping load intents. They do not establish browser layout, accessibility or console behavior. The Ubuntu/Python 3.12 locked CI job runs these checks; the other matrix jobs retain their Python checks. Continue to verify actual browser interaction separately when changing the frontend.

## Source and contract map

| Project source | Workbench surface | What to review when it changes |
| --- | --- | --- |
| [config.py](../parallax_relay/config.py) and [three_models.toml](../configs/three_models.toml) | Generated `contract.json`, form validation and TOML export | Field types, bounds, defaults, model and key variable names, provider choices and pricing |
| [state.py](../parallax_relay/state.py), [protocol.py](../parallax_relay/protocol.py) and [observations.py](../parallax_relay/observations.py) | Scenario summary, private objectives and spectator views | Roster, rules, HUD, images and private/public data boundaries. The browser does not construct provider prompts. |
| [play.py](../parallax_relay/play.py), [budget.py](../parallax_relay/budget.py) and [orchestrator.py](../parallax_relay/orchestrator.py) | Offline runner, smoke preset and live preparation | CLI flags, retry reservation, request caps, cost semantics and stop conditions |
| [recording.py](../parallax_relay/recording.py) and [example_run/](../example_run/) | Run import, observations, evaluation and fixture playback | Schema versions, names, record fields, terminal versus partial runs and old replay compatibility |
| [provenance.py](../parallax_relay/provenance.py) | Native manifest identity and programmatic recordings | Preserve optional provenance, programmatic/unknown modes and absent room labels; never infer live execution from missing identity |
| [runtime_contract.py](../site/runtime_contract.py) and [run_records.py](../site/run_records.py) | Build/runtime identity and native record packaging | Project-root Git checks, archive fallback, normalized fingerprint, object records and allowlisted PNGs |
| [conditions.py](../parallax_relay/conditions.py) and [policies.py](../parallax_relay/policies.py) | Condition selector and phase/call estimates; native replay policy labels in replay_template.html | Keep the condition mapping in contracts.mjs synchronized; preserve policy identity and keyboard focus |
| [site/web/](../site/web/) | Static UI, form checks, native run import | Copy, layout, accessibility and controls |
| [site/build_workbench.py](../site/build_workbench.py) and [site/relay_workbench.py](../site/relay_workbench.py) | Build artifacts and loopback adapter | Packaging and integration against the actual CLI |

The builder derives the Pydantic schema, TOML defaults and private goals directly from Python. Form hints, phase summaries and role-specific UI still need review when game semantics change. The fixed roster and player observations come from the engine. A total-token cap, generated rooms, uploaded observations and extra players are beyond the current runtime contract.

The loopback server handles connections on separate daemon threads with a 10-second socket timeout. It admits one offline execution at a time; a concurrent run receives HTTP 409. Host/Origin/token checks and strict request lengths apply before execution. The HTML responses deny framing.

The loopback adapter revalidates TOML settings with the project's Pydantic model, then runs the offline CLI in a temporary directory. Its API accepts a browser session token and listens only on loopback. The hosted Site uses static assets and loads imported recordings in the browser. Treat exported spectator records as private because they include all roles' HUDs, objectives and notes. Evaluation shows the engine's composite scores and transport outcomes. Review phase dialogue and engine events for communication quality and gameplay compliance.

Live preparation exports a local configuration after the user reviews the spending guard and enters all per-role rates. The guard uses the runtime estimate. Provider billing can differ from this estimate. Set actual model IDs and keys in the local environment, use `--check` to validate configuration, and explicitly approve any paid execution before running `--live`. Both browser entry points leave execution to the local CLI.

## Named live-smoke preset

**Match configuration → Use named live-smoke preset** loads the same public
[profile](../configs/live_smoke.json) used by the local helper. Live preparation
shows SPECTRA/PYRA as independent `gpt-6-luna` agents, FLUX as
`gemini-3.5-flash-lite`, the required environment-variable names, dated rates, model/pricing source links, eligibility/accounting notes and
fixed limits. PYRA retains its character, abilities, thermal view and objective.
No credential value enters the browser. Ordinary defaults still map PYRA to
Anthropic; that adapter remains live-unverified. The maintainer's
[scope decision](VERIFICATION.md#provider-acceptance-and-scope-decision--november-15-2026)
retires mandatory validation #15 without removing its adapter or marking it tested.
The current form permits independent choices among the three implemented adapters;
additional APIs and model modalities are future [#37](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/37)
work. The hosted Site is not republished by this documentation change.

Download the TOML and use the displayed `scripts/live_smoke.py --check --config
relay-workbench.toml` command locally. The helper accepts only an export matching
the frozen profile. Editing the settings invalidates approval and switches back
to the general CLI workflow. Local browser approval does not grant billing access
or establish provider support. See [the running guide](RUNNING.md#named-one-turn-live-smoke)
for explicit authorization, credentials, exit codes and one-invocation limits.

The generated `contract.json.live_smoke` addition is public metadata. It contains
model IDs, settings and source links, never keys or real live recordings. The
companion remains mock-only; live records are imported in the browser locally.
Usage-origin annotations are retained when present, and old records without them
remain supported. Rebuild the companion after profile or helper changes. Missing smoke files in
an older checkout produce a clear compatibility mismatch without a traceback.

## Review and release alongside engine changes

1. Update the workbench in the same PR when a change touches the contract map above. Regenerate the build and inspect the relevant settings or replay. If changing recording schema, review compatibility against the committed fixture as well as a newly generated run.
2. Run `python -m unittest discover -s tests -v`. The workbench smoke test checks generated settings and a native one-turn offline run. Verify the actual UI when changing frontend behavior. Check configuration export, a full or smoke offline run, a native replay import and the live-plan gate, as applicable.
3. After merge, build from the clean merged revision with the repository's locked dependencies. Check the revision shown in the UI and retain the generated static directory and companion ZIP together.
4. Publish over the **existing** private Parallax Relay Site. Its deployment source repository is separate from this game repository. In the authorized Sites workspace, keep that repository's existing `.openai/hosting.json`, copy the generated output into its configured static directory (`dist/`), commit and push the updated Site source, then save and deploy that version privately. Keep the Site's access settings and project identity. The hosted URL does not need to change.
5. Confirm the deployment succeeded, then load the Site as its owner. Check the displayed source revision, native fixture and companion download. Record the game revision **G** embedded in `contract.json` and the separate Site-source revision **S** used for the saved version/deployment, plus the archive hash and deployment receipt. Verify hosted contract G and the built fingerprint; the saved Site version must identify S. These are different repositories, so the SHAs need not match. To roll back, republish the previous known-good saved Sites version and verify the revision and fixture again.

There is no automatic deployment on merge. The game repository contains the source and build procedure. It does not contain Sites credentials or provider secrets.

## Evaluation conditions

The condition selector exports the same five protocol arms as the CLI. Selecting
an arm updates its communication-round count and invalidates live preparation.
No-images retains spectator PNGs but sends no image parts to providers. Withheld
communications are spectator-only; imported runs display their recorded arm.
Historical imports without a condition label remain explicitly unspecified.
Campaign registration/execution/analysis are CLI operations. The explicit
[protocol-3 exploratory profile](EXPLORATORY_STUDY.md) is also CLI-only; campaign
UI is outside this change. Native/request format 3, import/export and single-match
workbench behavior remain unchanged.
New native records display known-usage-priced and retained unknown-usage estimates
separately when present. Unpriced amounts remain unavailable. Imported historical
records without the optional split remain readable and round-trip unchanged.

## Curated rooms

The configuration contract includes metadata-only room IDs, versions, families
and splits. The room selector/export/companion allow development rooms; smoke
limits preserve the selected room and invalidate prior live approval. The named
live-smoke preset resets to Split Span and retains its historical profile hash.
Held-out execution is available only through registered protocol-2 confirmation
or matching protocol-3 validation, through the campaign CLI. New native imports
preserve the embedded spectator definition; legacy imports retain their original
shape. See [rooms](ROOMS.md).

Malformed v3 definitions, inconsistent loss flags and contradictory single-bridge
aliases are rejected before replacing the selected run. External-result records
validate against their declared `manifest.room_definition` while retaining unknown
execution/timing identity. The fixed script is an original Split Span control;
it runs unchanged in other development rooms and may fail or miss private goals.
