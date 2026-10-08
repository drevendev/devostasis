# Evidence to Action in 0.5.0

0.5.0 is prepared on the release branch and is not tagged yet. Install the
checkout for the offline walkthrough; the pinned workflow examples become
available after release. The published engine remains v0.1.9.

The companion turns recorded work and findings into five bounded queues. It
can collect GitHub or GitLab work context; it does not replace the core Vital
adapter or implement the accepted Instruments carrier. The schemas are
implementation-owned `devostasis.work.v2`, with historical v1 replay preserved, described in
[spec/work-scope.md](spec/work-scope.md) and
[spec/work-evidence.md](spec/work-evidence.md). No command executes work.

The [external adoption guide](external-adoption.md) and
[source-packet contract](spec/work-handoff.md) cover named candidates, glab
reuse, selected collection and enforced pinned source reads introduced in 0.4.

## Offline walkthrough

Install the checkout with `python -m pip install -e .`. The committed example
is synthetic, public and frozen at 2026-10-02T12:00:00Z:

```sh
devostasis work verify --bundle examples/work/bundle
devostasis work replay --bundle examples/work/bundle
devostasis work slice --bundle examples/work/bundle --at 2026-10-02T12:00:00Z --limit 2
devostasis work build --inventory examples/work/inventory.json --policy examples/work/policy.json --evidence examples/work/evidence.json --store /tmp/work-history
```

The slice includes its next cursor and overflow. Pass `--cursor <value>` and
the same role to get the next page. Roles are reviewer, developer, researcher,
analyst or all. `work explain --bundle <path> --item <id>` prints source,
bindings, reasons, read budget and acceptance. Without the frozen `--at`, an
expired example correctly returns a recovery request. New builds from identical
inputs and clock have identical ids and bytes, regardless of output directory.

## Adopt on GitHub

```sh
devostasis work policy --actor YOUR_LOGIN --output .devostasis/work-policy.json
# Review this policy: version, business priorities, required check names,
# criteria, correlated implementations, ownership and declared read budgets.
devostasis work run --repo OWNER/REPO --policy .devostasis/work-policy.json --store /private/work-history --cache /private/work-cache --max-requests 100 --max-pages 5 --seconds 120
```

Token resolution uses DEVOSTASIS_GITHUB_TOKEN, GITHUB_TOKEN, GH_TOKEN or the
local `gh` session; values are never persisted. Use read permissions for
contents, pull requests, issues and checks. REST reads project/default commit,
open and registered PRs, exact-head reviews, checks/statuses and files. GraphQL
uses a generated **query** for exact-head review threads and merge-queue state;
POST here is read-only. GraphQL errors or permission gaps are UNKNOWN.
Anonymous public REST cannot certify discussion completeness.

This repository carries its own explicit policy in `.devostasis/work-policy.json`
and a six-hour/manual self-work workflow. Its actor is the repository owner,
and its register names the new GitLab capability debt and the existing receipt
identity adoption question. The self-work workflow starts only after release;
scheduled/manual invocation avoids the legitimate merge-before-tag window.

Before executing a selected proposal, verify its expected project identity,
read only the declared files/symbols at the recorded revision within its byte
budget, and run:

```sh
devostasis work recheck --bundle BUNDLE --item ITEM_ID --expected-project-id YOUR_IMMUTABLE_PROJECT_ID --actor YOUR_LOGIN --policy-version YOUR_POLICY_VERSION --policy .devostasis/work-policy.json --max-requests 30 --seconds 60
```

Exit 0 means the selected proposal retained eligibility; 3 means invalidated;
2 means admission or refresh failed. Supply the trusted immutable project id,
and for
GitLab supply `--provider gitlab --endpoint YOUR_API_ENDPOINT` as well.
Recheck is read-only and cannot grant merge/deploy authority. Apply provider protection/permissions and conditional
exact-head mutations in the execution client. New checks, claims, dependencies
or actions may require a rebuilt scope. For offline negative cases supply
`--inventory` and an explicit `--at`.

For CANDIDATE issue/research/analysis proposals, supply a freshly attested
`--inventory` from the execution client's current source/checkout. A fixed
candidate commit does not identify a mutable source branch, so the CLI refuses
to infer that it is still current. Automatic named-ref refresh is tracked in
[#60](https://github.com/drevendev/Devostasis/issues/60). Canonical default-branch
content and selected candidate PR head recheck already have live source bindings.

[examples/work/github-observe.yml](../examples/work/github-observe.yml) calls
the reusable workflow after release. It runs after pushes, periodically and
for candidate PRs. It is non-gating, uses read credentials and uploads failure
receipts even when it cannot bind project identity. Candidate work cannot be
promoted to canonical latest. Artifact retention is **not** durable history:
for durable publication pass `history-runner` (a protected self-hosted runner
label) and `history-store` (its private mounted volume). The separate serialized
history job admits only a verified bundle matching the calling project id,
revision and CANONICAL context on a protected default branch. It has no forge
write token. Infrastructure can back up this volume to a separate private
history repository/object store. Keep writer credentials out of the
observer and out of PR jobs. Never commit generated history to the observed
branch. The core `observe-self` workflow continues to provide Vitals.

## Producer profiles

Collect context at the exact commit the report inspected, then import:

```sh
devostasis work import --inventory inventory.json --profile sarif.v1 --producer semgrep --producer-version declared-profile-1 --report results.sarif --output evidence.json
devostasis work import --inventory inventory.json --evidence evidence.json --profile junit.v1 --producer pytest --producer-version pytest-profile-1 --report tests.xml --output evidence.json
devostasis work import --inventory inventory.json --evidence evidence.json --profile cobertura.v1 --producer coveragepy --producer-version coverage-profile-1 --report coverage.xml --output evidence.json
devostasis work build --inventory inventory.json --policy policy.json --evidence evidence.json --store /private/work-history
```

The importer does not discover the report's commit: **the caller must attest
the envelope's exact commit** from its CI job, not relabel an older report.
SARIF locations must resolve to repository-relative physical paths without
uriBaseId. JUnit producers must include testcase file/name/line for failures
(a producer omitting file yields UNKNOWN instead of a guessed path). Configure
your JUnit exporter accordingly. Cobertura needs lines-valid and line hits;
an unavailable denominator is UNKNOWN. Include a reasoned UNAVAILABLE source
when expected instrumentation is absent. Performance input is a JSON object
with a measurements array of name/path/line/baseline/current/limit_percent/
unit/baseline_revision records; integer values avoid rounding ambiguity.
Reports are embedded with their digests for offline replay; secrets must not
be included in producer artifacts. There is no command interpretation.

## GitLab integration

```sh
devostasis work run --provider gitlab --endpoint https://gitlab.example/api/v4 --repo 123 --policy policy.json --store /private/work-history --max-requests 100 --max-pages 5 --seconds 120
```

Use numeric project ids and DEVOSTASIS_GITLAB_TOKEN with `read_api` (or an
explicit `--token-env`). Endpoint capability receipts reveal rejected calls;
CI_JOB_TOKEN is not assumed sufficient. The adapter reads MRs, exact-commit
pipeline jobs, discussions, diffs and declared issues/dependencies. Diff
count/result caps stay PARTIAL. Merge trains are probed through their active
inventory; missing licensed/permission capability stays UNKNOWN. The standard
aggregate approvals API has no reviewed SHA: **this adapter never fabricates
exact-head approvals**. MR context and issue/research/analysis scopes are usable;
exact-head review completeness and automatic merge admission need the later
revision-bound approval profile tracked in #58.

[examples/work/gitlab-observe.yml](../examples/work/gitlab-observe.yml) supplies
protected canonical and isolated candidate jobs, serialization, bounded cost,
failure artifacts, six-hour cadence guidance and a mounted private durable
store. Configure runner volumes/tags and read credentials in the adopter;
the candidate runner has neither the volume nor writer credentials. The store
is append-only; the current default SHA is checked before canonical collection.
A project moved during collection is not relabelled as fresh. Infrastructure
replication remains separate from the read adapter. The external GitLab shadow
pilot now exercises bound observation, result receipts and portable history;
see [work-operations.md](work-operations.md). Private production scheduling
and sustained calibration remain the integrating project's deployment gates.

## Validation record

On 2026-10-02, the authenticated read-only GitHub pilot on
drevendev/Devostasis collected all five then-open PRs in 38 successful API
requests. Reviews, checks/statuses, file inventories and GraphQL threads were
COMPLETE; draft/conflict/merge-queue facts were typed. The inventory built a
verified scope, replayed offline and preserved independent reviewer and owner
roles. This is a public project integration check, not the external sustained
calibration pilot B7. No repository object was mutated. CI additionally
verifies the synthetic example and repeated builds across supported Python
versions. Private GitLab credentials and deployment were intentionally not
assumed.
