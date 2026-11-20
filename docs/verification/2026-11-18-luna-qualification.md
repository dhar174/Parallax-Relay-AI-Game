# All-Luna qualification evidence

The protocol-4 qualification gate passed on November 18, 2026. Its 60-case
cohort consists of 10 selected development model cases, 45 selected controls,
and five completed Split Span model cases. The qualification stabilizes the
registered exploratory design. The six held-out rooms remain unrun.

## Successful Split Span supplement

The worker and its foreground supervisor exited 0. All five trials launched,
finished with terminal outcomes, and had complete native artifacts and
successful cleanup. The trial, cell, and attempt CSVs reconciled to 5, 5, and
297 rows. The report contains no anomalies or unresolved reservations. Every
request succeeded on its first attempt and had complete recorded usage.

Each match used three independent `openai/gpt-6-luna` agents. Conditions were
run once on this development room.

| Condition | Outcome | Turns | Paid requests | Local estimate |
| --- | --- | ---: | ---: | ---: |
| Full | Victory | 7 | 63 | $0.034190000 |
| Reduced | Victory | 7 | 42 | $0.018926875 |
| Disabled | Victory | 7 | 21 | $0.007633000 |
| Withheld | Victory | 7 | 63 | $0.023165625 |
| No images | Defeat | 12 | 108 | $0.062781625 |
| **Total** | **4 victories, 1 defeat** | **40** | **297** | **$0.146697125** |

The run stayed within the 864-request ceiling and $1.25 aggregate local
estimate guard, with no binding guard. Completed defeats are eligible under
the qualification protocol. These five descriptive outcomes do not establish
an effect of visuals or communication, or predict held-out performance.

## Preserved interruption and accounting

The first supplement registration remains incomplete. Its worker and supervisor
were terminated by SIGKILL. Two trials launched, one finished, and three never
started. The retained artifacts record 60 successful requests with an observed
local estimate of $0.024962875, including 39 recorded requests from the second,
interrupted trial. Unrecorded exposure is unknown. That attempt did not
contribute cases to the successful supplement.

The earlier mixed-provider pilot remains incomplete and its recorded costs stay
in the historical total. The prior pilot and continuation estimate is
$1.044149250, including $0.406677000 retained for unknown usage. Across the
prior runs, the recorded portion of the interruption, and the completed
supplement, the local estimate is $1.215809250, excluding the separate earlier
Q allowance. These figures describe local accounting and do not establish
provider billing.

## Verification and identities

The qualification receipt was reconstructed and checked against the frozen
selection and native evidence. The full local Python suite passed 448 tests.
All seven hosted jobs passed on the evaluated source, including Windows,
77 Node checks, and 37 Chromium checks. Native replays and credentials remain
private. The digests below identify the verified local artifacts.

| Record | Identity |
| --- | --- |
| Evaluated source | `9cbc469b89a2124948090d97f47555d7506f2a28` |
| Hosted verification | [Workflow 44270594441](https://github.com/dhar174/Parallax-Relay-AI-Game/actions/runs/44270594441) |
| Committed selection | `805880e58ee4bb0df152f781f18a9de3ff195ed22c7287abb3e857b207e451b3` |
| Reviewed source bridge | `7bff10c23b71bc7ca802b630a4761d20083040e7712b2521f71eda8956420b63` |
| Interrupted registration | `daf4b0babfd25d9ec8be38fb442892527c0460579ecf8e2e6f605153e93cf7b5` |
| Interrupted report | `3a0e27444360c4752809b9ba3b1f7f7d26ea8fc3aca6f0e9f00677ff3830b3b0` |
| Successful supplement registration | `e1b4c51eecd1418c4ecde6cd76d6286b5d5dce86cc6e544a58905a77a8b5577d` |
| Successful supplement report | `8dd92af830070237043cd60e3ac2f597bf2424d9f847f58238c03f3cd9386c09` |
| Qualification receipt | `e386892b0ca31de42cf2cae81a74ae065639b162757c6fa503dcf488b126da0c` |
| Unstarted held-out registration | `bb13f7d164001360d114632a3551d7f3de6e8a1d5b7f82710dd9a1024b1b9272` |

The held-out registration covers 30 model matches and 90 controls, with up to
5,184 paid requests and a $7.50 local estimate guard. Its spending decision
remains separate. See the [protocol and limits](../LUNA_QUALIFICATION.md).
