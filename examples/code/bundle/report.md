# Offline repository analysis

Revision: `505ec5559236affd51ee6621b0eb54780bcd0e11`

Python grammar: 3.12. Static evidence only; repository code was not executed.

Python source coverage: COMPLETE; history: COMPLETE.

Unsupported and unavailable inputs do not establish an absence of findings.

| Source status | Files |
| --- | ---: |
| ANALYZED | 3 |
| PARSE_ERROR | 0 |
| UNAVAILABLE | 0 |
| UNSUPPORTED | 1 |
| OUT_OF_SCOPE | 0 |

## Findings

| Path | Line | Rule | Symbol | Evidence |
| --- | ---: | --- | --- | --- |
| src/widget/app\.py | 1 | DS-PY-IMPORT-CYCLE | cycle:d205d439f837a19cc3f0467afed21a795b586999d0c79f8d3c9fba70482306cc | \{&quot;paths&quot;:\[&quot;src/widget/app\.py&quot;,&quot;src/widget/parser\.py&quot;\]\} |
| src/widget/app\.py | 3 | DS-PY-COMPLEXITY | choose | \{&quot;complexity&quot;:2,&quot;limit&quot;:1\} |
| src/widget/parser\.py | 3 | DS-PY-COMPLEXITY | fallback | \{&quot;complexity&quot;:2,&quot;limit&quot;:1\} |
| src/widget/parser\.py | 6 | DS-PY-BARE-EXCEPT | fallback\.&lt;bare-except&gt;\#1 | \{&quot;catches&quot;:&quot;BaseException&quot;\} |

Showing 4 of 4 findings; analysis.json and findings.sarif retain every finding.

## Source gaps

| Path | Status | Reason |
| --- | --- | --- |

Showing 0 of 0 source gaps.

## Recent change evidence

Non-merge commits in [2026-09-10T12:00:00Z, 2026-10-08T12:00:00Z].

Counts under PARTIAL history are observed counts, not complete totals or productivity.

| Path | Revisions | Added | Deleted | Coverage |
| --- | ---: | ---: | ---: | --- |
| src/widget/parser\.py | 1 | 7 | 0 | COMPLETE |
| src/widget/app\.py | 1 | 6 | 0 | COMPLETE |
| README\.md | 1 | 1 | 0 | COMPLETE |
| src/widget/\_\_init\_\_\.py | 1 | 0 | 0 | COMPLETE |

Showing 4 of 4 paths.

STATIC_SOURCE_EVIDENCE; no execution, independent acceptance, health score or merge authority
