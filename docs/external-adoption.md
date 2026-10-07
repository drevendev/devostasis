# External adoption: shadow consumer qualification

0.5.0 is prepared, not tagged. Install this reviewed checkout with
`python -m pip install -e .`. After release, pin `v0.5.0` or its exact commit.
The public synthetic examples use work scope v2; frozen v1 bundles remain in
`examples/legacy/work-v1`. Do not replace production intake just because a
shadow packet verifies.

Use a GitLab read token from an existing environment, or an already configured
`glab` login for the chosen host. Devostasis reuses glab's credential without
extracting it. The glab bridge requires an HTTPS `/api/v4` base and no cache.
Explicit `--token-env` mode supports credential-partitioned conditional caching.

```sh
devostasis work policy --actor YOUR_LOGIN --output policy.json
# Declare criteria, dependencies, paths and acceptance in policy.json first.
devostasis work run --provider gitlab --endpoint https://gitlab.example/api/v4 \
  --repo GROUP/PROJECT --policy policy.json --registered-only --store private-history
devostasis work slice --bundle BUNDLE_DIRECTORY --role researcher --limit 1 --output slice.json
devostasis work handoff --bundle BUNDLE_DIRECTORY --item ITEM_ID \
  --provider gitlab --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID \
  --policy policy.json --actor YOUR_LOGIN --policy-version example-1 --output packet.json
devostasis work verify-handoff --bundle BUNDLE_DIRECTORY --packet packet.json \
  --provider gitlab --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID \
  --actor YOUR_LOGIN --policy-version example-1
```

`--registered-only` collects policy-registered implementations; `--change N`
collects named changes. Both record SELECTED coverage. Without either, collection
attempts the open-and-registered inventory and may return PARTIAL at a budget
cap. Never describe a selected or capped generation as the entire backlog.
Use the scope's recorded recovery items and refresh selected evidence.

For a candidate, add `--context CANDIDATE --source-ref BRANCH` or
`--source-change PR_OR_MR_NUMBER`. `--source-project` can bind a branch in a fork;
PR/MR mode resolves the native source project. Optional `--revision` is an
expected full SHA and must match live resolution. A deleted ref, changed head
or unavailable permission is a failure; no historic-SHA fallback exists.
Candidate scopes are persisted without moving canonical latest.

The receiver verifies one role slice and its scope bundle, selects a READY
item and obtains a live handoff. Files remain Base64 data with sizes/digests,
acceptance and immutable source binding. The receiver can analyze only those
bytes, record a result tied to scope/item/packet/revision, and use its existing
claim, independent review, merge and deployment procedures. Source content
cannot grant permission. Refresh immediately before an authorized action;
an offline packet verifier does not prove current source state.

The external shadow path supports a declared bounded research task, immutable
scope/slice/packet and a deleted-ref negative control. Store private source bytes
and detailed qualification results in the adopter's private issue/history.

The 0.5 repeatable caller supports fresh bound generations, packet-bound caller
results, disabled controls and verified history restore. Keep detailed external
qualification and all inventory/timing/calendar evidence in the adopter's private
issue and history. Full bridge collection qualification remains #62; no missing
MR is treated as absent or exact-head approval invented.
See [work-operations.md](work-operations.md) for the repeatable caller path.

Remaining deployment acceptance: reviewed pinned release; existing credential
capability qualification; private durable history/writer; scheduled repeated
generations over real work; independent comparison with forge state; installed
caller → configuration → invocation evidence plus a removed-binding negative
control; explicit activation/rollback authority. GitLab exact-head approvals
remain UNKNOWN (#58). Full large-project generation performance is #62.
Phase B7's sustained calibration bar remains open until these observations exist.
