# Dependency assurance — November 16, 2026 UTC

Issue [#24](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/24) remains
open: the Python remediation passes the checks below, but Playwright's inlined
components have unresolved advisory candidates. This is dependency assurance,
not the separate source/security audit in #23 or a universal safety certificate.

## Source, environment, and results

Dee Pendenz audited the original Python environment at
`4e0851b2b1ebfeb2f23a8037b9b9c10169d97675`, specifically
`/workspace/scratch/parallax-replay/.venv`. The remediation input revision is
`3272faa`, which includes browser harness revision `572573c`. The npm inputs are
that committed harness's `tools/browser/package.json` and `package-lock.json`.
[Evidence](audits/dependencies-2026-11-16/evidence.json) records input SHA-256s,
actual tool results, exact inventories, OS release, advisory identifiers and
publication/modification dates. These results cover those dependency inputs;
subsequent source changes need their own behavioral verification. Historical
execution commits `3272faa2e9962cbcbad9009913680004de8f207c` and
`572573c7c1ae126b0722fc0787e0fc91e17c392a` are retained in the original local
repository, but were unavailable from a fresh remote clone during independent
review. Their full historical test trees are therefore not remotely
reconstructable from the published branch stack. The six recorded dependency and
workflow input hashes match the reviewed stack; current-head verification is
separate evidence and does not recreate those historical executions.

Actual execution used Debian 13.6/Linux x86_64, Python 3.12.14, pip 26.3,
pip-audit 2.10.1, uv 0.13.6, Node 24.22.1, and npm 11.9.0. Audit tooling lives in
this worktree's ignored `.venv`; target environments are separate external
scratch venvs. No tooling was installed globally or added to runtime requirements.
Registry/advisory requests used live PyPI, npm and OSV on November 16, 2026 UTC;
these were not offline or dry-run clearances. Empty HTTP caches were used for the
initial PyPI scans. OSV individual records retain their data dates; an empty
result has a query date, not a claimed global database snapshot date.

| Input | Actual advisory result |
|---|---|
| Original locked 12 packages plus pip | PyPI: 42 records in Pillow 12.3.0; OSV: 62 records, including duplicates |
| Original independently resolved ranges plus pip | Same installed versions; PyPI: same 42 Pillow records |
| Patched locked 12 packages plus pip | PyPI and OSV: zero known advisories, no skipped distributions |
| Patched independently resolved ranges plus pip | Same installed versions as patched lock; PyPI: zero known advisories |
| uv 0.13.6 generator | PyPI: zero known advisories for that distribution |
| pip 26.3's 18 declared vendor versions | Five records/three unique setuptools advisories; affected modules absent from pip's vendored subset, as described below |
| Complete npm lock, including development and optional nodes | npm: zero advisories across playwright 1.62.1, playwright-core 1.62.1, and fsevents 2.3.2 |
| Playwright inlined npm components | OSV: 39 advisory matches across nine of 175 declared package/version pairs; unresolved candidates |

The baseline PyPI/OSV results identify **43 distinct GHSA IDs** after alias
deduplication, all with fixed release 13.0.0. OSV additionally reports
`GHSA-rfgq-q3w2-pmv2` (Image.quantize empty-palette memory disclosure), absent from
the PyPI scan result. Retain both sources rather than treating their different
counts as separate vulnerabilities. Complete IDs, aliases, affected ranges,
dates and source references are in the evidence JSON; advisory projections omit
long descriptions, while the saved scanner outputs retain their original fields.

## Pillow remediation and applicability

Live [PyPI release metadata](https://pypi.org/pypi/Pillow/json) had no patched
12.x release after 12.3.0. The upstream
[13.0.0 release](https://github.com/python-pillow/Pillow/releases/tag/13.0.0)
was published October 16, 2026. Examples include
[GHSA-4558-3h8r-v8xp](https://osv.dev/vulnerability/GHSA-4558-3h8r-v8xp)
(raw decoder over-read),
[GHSA-4rr5-89j8-mwwm](https://osv.dev/vulnerability/GHSA-4rr5-89j8-mwwm)
(TIFF encoder use-after-free), and
[GHSA-j4m9-6w36-pw47](https://osv.dev/vulnerability/GHSA-j4m9-6w36-pw47)
(FreeType stroker cleanup). They are valid matches for the installed distribution;
application exploitability was not demonstrated. `render.py` creates fixed-size
RGB images, draws fixed geometry/text, loads a local/default font, and encodes
PNG. It does not decode uploaded images, save TIFF/PDF, quantize images, or request
nonzero text strokes. These observed boundaries reduce applicable paths without
proving that all native-library risks are unreachable.

The fix changes the direct range to `Pillow>=13.0,<14` and the hash lock to
13.0.0. A lower floor of 10.4 would continue allowing known affected releases.
The documented uv 0.13.6 universal regeneration changed only Pillow's version and
hashes; every non-Pillow lock byte and `requirements-tested.txt` stayed unchanged.
Pillow 13 requires Python >=3.11, preserving this repository's minimum. PyPI
published wheels cover CPython 3.11–3.13 Linux x86_64 and CPython 3.12 Windows
x86_64/macOS arm64 and x86_64. Wheel availability is not successful hosted testing.

An isolated 13.0.0 candidate passed 366 Python tests before the range edit. A
fresh hashed/binary-only install passed 366 tests, pip check, compilation, both
mock games (7 turns, 63/42 calls, energy 5, all scores 100), and nine room
certificates. An independently bootstrapped, freshly resolved range environment
also passed 366 tests. After including browser revision 572573c, the patched
environment passed all 366 tests again in 61.144 seconds; 364 are existing tests
and two exercise the new inventory utility. The workbench build, Node syntax
checks and all 66 offline Node tests also passed. An initial Node invocation
failed because its generated workbench contract was absent; running the documented
build before retrying resolved that setup failure. Hosted matrix and real-browser
acceptance on the eventual PR revision remain separate checks.

The extra pip vendor-name scan reports `GHSA-5rjg-fvgr-3xxf`,
`GHSA-h35f-9h28-mq5c`, and `GHSA-xmj3-9gf7-h52w` for setuptools 70.3.0. Their
affected code is respectively `setuptools/package_index.py`, sdist
`FileList`/`command/egg_info.py`, and `setuptools/wheel.py`. pip 26.3 carries
only the legacy `pkg_resources` subset, not these setuptools modules. These
full-package matches therefore do not establish affected code in that subset;
the raw findings are preserved rather than suppressed. This does not clear a
separately installed setuptools or all vendored code paths.

## Browser tooling candidates and separate coverage

The final npm command was `npm audit --package-lock-only --include=dev
--include=optional --json --prefix tools/browser`, exit 0. This includes the
Darwin-only fsevents node even though it is not installed on Linux. All three
downloaded npm tarballs matched their lockfile SHA-512 integrities. Their actual
LICENSE/NOTICE files and inlined-component sidecars were inspected and preserved.

An additional OSV querybatch used the names and exact versions declared in
Playwright's `*.js.LICENSE` sidecars. These components are not npm lock nodes:

| Inlined component | Version | Advisory matches |
|---|---|---:|
| @hono/node-server | 1.19.14 | 3 |
| @modelcontextprotocol/sdk | 1.29.0 | 6 |
| baseline-browser-mapping | 2.10.40 | 1 |
| brace-expansion | 5.0.7 | 5 |
| browserslist | 4.28.4 | 2 |
| fast-uri | 3.1.3 | 12 |
| ip-address | 10.2.0 | 8 |
| minimatch | 10.2.5 | 1 |
| zod | 4.4.3 | 1 |

Individual advisory records confirm those declared versions fall in affected
ranges. They do not establish that each affected function survives bundling or
receives attacker-controlled input in our harness. The harness uses Node's test
runner and Playwright's Chromium API; it does not invoke the Playwright CLI,
MCP/OAuth services, Hono application server, or Babel test transpilation. Glob,
URI, IP and schema-validation reachability still needs targeted inspection.
No candidate is graded as a confirmed exploit or dismissed as a false positive.

One bounded comparison downloaded the official latest Playwright/core **1.65.1**
tarballs without changing the project. Its Node >=20 requirement admits Node 24,
but OSV still matched nine advisories across four of 164 inlined component/version
pairs: @hono/node-server 2.1.5, hono 4.13.12, ip-address 10.7.2, and minimatch
10.2.5. A package bump alone would not establish clearance. **Follow-up for #24:**
trace these candidates through the actual bundled exports and harness inputs;
refresh upstream tooling when a verified fix is available, and rerun the browser
suite and both lock/bundle advisory checks before claiming remediation. The
current Playwright pin is preserved; the comparison receipt is in evidence.

Neither npm audit nor pip-audit independently inventories browser executables,
Node/npm, Python's interpreter/stdlib, OS packages, fonts, native wheel libraries,
or vendored Rust crates inside uv. Pillow's supplied SBOMs and Playwright's browser
revision manifest (Chromium 151.0.7922.34, revision 1234) are recorded as inventories,
not independently scanned binary
clearances. The tested Pillow wheel dynamically loads system FriBiDi 1.0.16 and
system zlib; optional libimagequant is absent even though its upstream SBOM lists
it. Other platforms' wheel contents and browser/OS combinations were not audited.

CI actions are a separate supply-chain surface: checkout
`3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1), setup-python
`6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` (v7.1.0), setup-node
`249970729cb0ef3589644e2896645e5dc5ba9c38` (v6.5.0), and upload-artifact
`ea165f8d65b6e75b540449e92b4886f43607fa02` (v4.6.2). Their pinned upstream MIT
license texts were checked. The named package audits do not scan their bundled
JavaScript, transitive build tooling or runner images. Node 24 in CI is a major
selector, not an exact binary pin. Browser/OS support comes from the browser
verification record, not the npm result.

## Licenses and distribution obligations

The repository remains [MIT](../LICENSE). The
[license evidence](audits/dependencies-2026-11-16/licenses.json) contains exact
installed metadata, supplied license texts and SHA-256s, including pip's vendor
notices, uv's two licenses, npm LICENSE/NOTICE/sidecar texts and pinned action
licenses. `scripts/dependency_inventory.py` collects those Python records offline
with the selected interpreter, preserving missing metadata and undecodable text
as explicit unknowns. It does not enumerate environment key/value pairs or collect
direct-install URLs. Platform descriptions use Python's platform library, which
can invoke an ambient-PATH `uname` on Linux; run collection only in a trusted
installed environment. This is not a privacy boundary against hostile executables
on PATH. License labels alone are not a redistribution checklist.

Collector review follow-up: RECORD paths are checked against the distribution's
own canonical metadata directory and license area before reading. Traversal,
absolute paths, symlink escapes and direct_url.json aliases (including hard links)
are rejected as unavailable evidence. Unreadable, missing and directory entries
receive per-file error categories without exception messages, and collection
continues. `License-File` declarations are also checked when RECORD is absent or
omits them; `file_inventory_available` makes a missing file inventory explicit.
The collector assumes an installed filesystem environment that is not concurrently
being modified. It is not a sandbox for hostile installation processes.

Five focused tests cover these cases using fake private metadata and temporary
licenses; the full 369-test Python suite passed in 74.674 seconds. Link-specific
tests skip when the filesystem does not permit creating links. The real patched
environment still yields exactly the same 34 license
file hashes across 13 distributions, with no unavailable entries. The frozen JSON
snapshot retains the original collector digest; these changes harden subsequent
collection without rewriting its package/advisory/license observations.

### Windows CI portability follow-up — November 16, 2026 UTC

Hosted [run 43960834905](https://github.com/dhar174/Parallax-Relay-AI-Game/actions/runs/43960834905)
on assembled revision `2ac6df1c67735724c1ec00ce7e4faa1583545c22` passed six jobs,
including Chromium, but its
[Windows/Python 3.12 job](https://github.com/dhar174/Parallax-Relay-AI-Game/actions/runs/43960834905/job/133627458103)
failed. Those job statuses were independently checked through GitHub. The supplied
Windows diagnostics identified CRLF-dependent notice fixtures, a permission mock
that missed Windows' resolved temporary-path spelling, and an unsuccessful
inventory subprocess whose stderr had been hidden by `check=True`.

A Linux regression with only a fake installed Unicode notice and
`PYTHONIOENCODING=ascii` reproduced `UnicodeEncodeError` against the prior CLI.
The CLI now emits ASCII-escaped JSON; JSON decoding preserves the original Unicode
text, and collection still hashes the unmodified raw file bytes. Notice fixtures
write explicit bytes, the permission mock compares resolved paths, and directory
errors accept the platform's actual unavailable-file category. Mandatory traversal,
private-metadata and absolute-path tests run independently of link-specific tests,
which alone may skip when links cannot be created. Subprocess assertions now show
return codes and captured stderr on failure.

All seven focused tests and the full 371-test Python suite passed locally (the
full suite took 55.085 seconds). Actual environment readback preserved all 34
notice hashes across 13 distributions with no unavailable entries. A new
hosted run on the patched assembled revision is required for Windows acceptance;
the prior six passing jobs do not establish that acceptance.

### Independent collector review repairs — November 17, 2026 UTC

The collector repair starts at `9b3b6b570c9cff4ed66f2e1fe4b36e0c7ba830f8`.
License candidates that are regular files with more than one hard link are now
rejected before reading, including aliases to another distribution or a file
outside the installation. This conservatively marks genuinely shared hardlinked
notices unavailable too. A missing distribution Name remains `null` with
`metadata_error`; per-distribution metadata failures retain an unavailable row
and an exception category without its message, while healthy neighbors remain
available. Healthy rows have `metadata_error: null`.

Raw RECORD CSV entries now supply candidates because Python 3.12's importlib can
filter nonexistent files from its file inventory. Missing recorded licenses
remain explicit even without a `License-File` declaration. Installations without
RECORD retain the existing importlib file-inventory fallback. Embedded NUL paths
receive a per-file `ValueError` category rather than aborting collection.

Against the unchanged collector, 12 focused tests exited 1 with four failures
(three hardlink cases and one missing recorded notice) and three errors (missing
Name, metadata read failure and NUL path). After repair all 12 passed with no
skips or warnings in 0.332 seconds. Real locked-environment readback preserved
all 34 notice hashes across 13 distributions, with no metadata or text errors.
The complete offline Python suite passed all 387 tests with no skips in
141.259 seconds.
`pip check`, compilation, the normal/fast mock verifier, and a real temporary
no-RECORD egg-info SOURCES fallback check also passed. These checks used the
existing locked Python 3.12 interpreter without changing its environment.

This remains offline inventory repair: no advisory database refresh, formal
security scan, hosted Windows acceptance, or zip-distribution support is claimed.
The no-concurrent-installation-modification assumption above still applies.

| Locked distribution | Version | Supplied license |
|---|---|---|
| Pillow | 13.0.0 | MIT-CMU, plus bundled notices |
| pydantic / pydantic-core | 2.14.3 / 2.50.4 | MIT |
| httpx / httpcore | 0.28.1 / 1.0.9 | BSD-3-Clause |
| annotated-types / anyio | 0.8.0 / 4.16.0 | MIT |
| certifi | 2026.10.23 | MPL-2.0 |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0, with historical Python terms |
| typing-inspection | 0.4.5 | MIT |
| pip bootstrap | 26.3 | MIT, plus vendor notices |
| uv generator | 0.13.6 | MIT OR Apache-2.0 |
| playwright / playwright-core | 1.62.1 | Apache-2.0, NOTICE and inlined sidecars |
| fsevents (optional) | 2.3.2 | MIT |

For source/static workbench distribution, retain this project's MIT notice.
The portable workbench does not include Python wheels or this development npm
tooling. PNG output alone does not distribute the imaging library. A companion
source checkout that requires users to install dependencies differs from a
bundle that ships a Python environment, npm tree, browser, font, or native binary.

When redistributing dependencies, retain their actual copyright, permission,
conditions and disclaimer notices. BSD terms also restrict endorsement; MIT-CMU
requires notices in supporting documentation. Apache-2.0 requires a copy of the
license, retention of applicable NOTICE material and notices of modifications.
Retain the complete Playwright sidecars, not only its top-level Apache label.
PSF/historical Python notices must accompany applicable copies and derivative
changes must be summarized where required. certifi's covered source files and
modifications remain MPL-2.0; preserve its notice and provide covered source and
license information when distributing executable form. MPL permits a larger MIT
work without relicensing this repository.

Pillow's supplied composite notice includes FreeType (FTL), IJG/libjpeg,
HarfBuzz, libtiff, libpng, OpenJPEG, libwebp, AVIF-related components and other
native notices. A binary bundle using FreeType must acknowledge the FreeType Team;
IJG's required documentation credit is “this software is based in part on the
work of the Independent JPEG Group”. Preserve all applicable native notices and
mark source modifications. System FriBiDi is LGPL-2.1-or-later; shipping it would
need its own LGPL source/relinking/license review. Its full licensing, browser
binary notices and fonts are outside this dependency-package license snapshot.
The optional upstream libimagequant GPL entry is not proof that the tested wheel
includes that component. Redistributing a binary application or container needs
an inventory of the actual binaries and OS packages before license sign-off.

## Refresh procedure

Use fresh target venvs and a separate tooling venv. Install targets with the
documented hashed/binary-only bootstrap and project lock; resolve `requirements.txt`
without the lock in the separate range target. Record Git revision, clean/dirty
state, input hashes, UTC times, Python/OS/architecture and tool versions. Do not
dump environment variables, npm/pip configuration, credentials or direct URLs.

```bash
TARGET_PYTHON=/absolute/path/to/target/bin/python
AUDIT_PYTHON=/absolute/path/to/audit-tools/bin/python
"$TARGET_PYTHON" scripts/dependency_inventory.py > inventory.json
"$TARGET_PYTHON" -m pip check
"$AUDIT_PYTHON" -m pip_audit --version
"$AUDIT_PYTHON" -m pip_audit --strict --path /absolute/path/to/target/lib/python3.12/site-packages -s pypi -f json --desc off --progress-spinner off --cache-dir /fresh/empty/cache -o pypi.json
"$AUDIT_PYTHON" -m pip_audit --strict --path /absolute/path/to/target/lib/python3.12/site-packages -s osv -f json --desc off --progress-spinner off -o osv.json
npm audit --package-lock-only --include=dev --include=optional --json --prefix tools/browser > npm-audit.json
```

The tooling venv can install `pip-audit==2.10.1` and `uv==0.13.6` with
`--only-binary=:all:` to reproduce these tool versions; re-evaluate maintained
versions on refresh. Derive the site's installation path with the target Python
on Windows or another Python version instead of copying the Linux example.
Check every exit code: advisory findings normally exit 1; collection/network/tool
errors and missing/skipped records are unavailable coverage, not clean results.
Do not use dry-run or ignore IDs to manufacture clearance.

For bundled npm coverage, `npm pack --ignore-scripts` each exact locked package
into a temporary directory and verify tarball SHA-512 against the lock. Inspect
LICENSE, NOTICE, ThirdPartyNotices and `*.LICENSE` files. Extract the `- name@version`
entries in `*.js.LICENSE` sidecars and POST their exact npm package/version queries
to `https://api.osv.dev/v1/querybatch`; the complete query/response format is saved
in evidence. Fetch each match from `/v1/vulns/<id>` to retain dates, affected
ranges and references. Repeat for any candidate upgrade, and keep omitted/inlined
code and runtime reachability distinct from a full package match.

Review current license files, wheel SBOMs, browser manifests, pinned actions and
binary/OS exclusions again; neither today's inventory nor old zero counts cover
new resolutions. Coordinate compatible fixes with lock regeneration and fresh
offline/browser verification. Before sharing outputs, review them for secrets,
local configuration and provider data. This snapshot includes public package
metadata/notices only; no credentials, provider calls, billable runs, deploys or
GitHub writes were used.
