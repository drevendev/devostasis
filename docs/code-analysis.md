# Offline Repository Analysis

The 0.6.0 companion turns a local Git revision into reproducible Python source
evidence. It inventories the entire committed tree, parses in-policy Python
files, records function decision counts and spans, resolves declared local
imports, detects static import cycles and lists recent change hotspots.
Repository code, hooks, tests and dependencies are never executed by analysis.
It uses the standard library and an installed Git supporting `--no-lazy-fetch`.
Python 3.12 is the fixed analysis grammar.

Install the checkout with `python -m pip install -e .`. Select the revision
explicitly; uncommitted work is excluded. Generate and edit a policy to declare
source roots, include/exclude prefixes, local thresholds and read limits:

```sh
devostasis code policy --output code-policy.json
devostasis code analyze --repo . --revision HEAD --policy code-policy.json --output /private/code-analysis
devostasis code verify --bundle /private/code-analysis
devostasis code show --bundle /private/code-analysis
devostasis code sarif --bundle /private/code-analysis --output /private/findings.sarif
```

The default observation time is the commit's committer time, so repeating the
same command at the same revision is reproducible. `--at` explicitly selects a
UTC history anchor. The source tree remains the pinned revision, even when
that anchor precedes its commit time. History includes only non-merge ancestors
inside the recorded 28-day window. A commit/time/read cap or shallow checkout
retains an explicit history gap. Hotspot counts under PARTIAL history are
observed lower counts, with no productivity or health judgement.

The bundle contains `inputs.json`, `policy.json`, `analysis.json`,
`findings.sarif`, `report.md` and `manifest.json`. Verification needs no Git
checkout or network: it binds admitted bytes to their Git blob IDs, binds the
complete tree inventory to the commit, and replays every output byte. Commit
metadata and source bytes are included; keep real analysis bundles private
when those inputs are private. The public example is entirely synthetic:

```sh
devostasis code verify --bundle examples/code/bundle
```

Python coverage is COMPLETE, PARTIAL or NOT_APPLICABLE. Other languages remain
UNSUPPORTED; exclusions, syntax failures, encoding failures, links/submodules
and budget omissions retain distinct file states. COMPLETE means analysis of
the admitted Python scope, with the recorded static resolution assumptions.
It does not prove runtime behavior or the absence of defects in other languages.
The local identity derives from the recorded root commit IDs, not a forge URL;
shallow or unrelated roots and changed policy make comparisons INCOMPARABLE.
History counts and root traversal are acquisition observations; their complete
ancestry is not independently proved by the source tree proof (issue #73).

Compare two verified bundles under the same policy:

```sh
devostasis code compare --before /private/code-before --after /private/code-after --output /private/code-delta.json
```

A disappeared finding is RESOLVED only when every involved file is analyzed
or positively absent from the proved tree. An unavailable file gives
UNOBSERVED. Newly visible findings behind prior gaps are FIRST_OBSERVED. Line
moves retain finding identity and report CHANGED. These are finding transitions,
without an aggregate improvement judgement.

Create a bounded exact-source packet for a selected set of admitted files:

```sh
devostasis code packet --bundle /private/code-analysis --path src/app.py --max-files 5 --max-bytes 65536 --output /private/code-packet.json
devostasis code verify-packet --bundle /private/code-analysis --packet /private/code-packet.json
```

Packets retain original bytes, blob IDs, subject, bundle identity and declared
limits. They execute nothing and grant no permission or freshness guarantee.

To feed findings into the existing `analyze_code` queue, supply an already
admitted work inventory collected for the *same full commit ID*:

```sh
devostasis code work-evidence --bundle /private/code-analysis --inventory /private/inventory.json --output /private/code-evidence.json
devostasis work build --inventory /private/inventory.json --policy /private/work-policy.json --evidence /private/code-evidence.json --store /private/work-history
```

The inventory supplies immutable forge identity explicitly. Export preserves
the analysis time and marks incomplete source coverage PARTIAL; it cannot
re-date evidence. Existing work freshness, revision, dependency, acceptance and
read-budget rules still apply. Reanalyze with an explicit appropriate `--at`
to acquire a new observation, and recheck live sources before execution.
No external runner, schedule, credentials or deployment is required for the
offline commands. B1, B7 and release/review gates remain separate.

See the [wire contract](spec/code-analysis.md) and
[synthetic report](../examples/code/bundle/report.md).
