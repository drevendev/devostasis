# Repeatable consumer operations

0.5.0 is prepared for review, not tagged. Install this checkout with
`python -m pip install -e .`; after review/release pin the exact source commit
or published tag. Existing glab authentication works unchanged. Runtime remains
standard-library-only and read-only toward the forge.

Commit an adopter-owned work policy, then generate a binding (disabled by default):

```sh
devostasis work bind --provider gitlab --endpoint https://gitlab.example/api/v4 \
  --repo GROUP/PROJECT --expected-project-id NUMERIC_ID \
  --policy .devostasis/work-policy.json --integration-id daily-shadow \
  --output .devostasis/work-adoption.json
```

Review the immutable project id, policy digest, engine version, selection and
budgets. REGISTERED is the initial selection; choose OPEN_AND_REGISTERED for a
complete inventory attempt or CHANGES with explicit numeric refs. Set enabled
to true only for the intended caller. A policy edit requires regenerating the
binding digest; it cannot silently replace the caller's policy under one version.

```sh
devostasis work observe --binding .devostasis/work-adoption.json \
  --policy .devostasis/work-policy.json --store /private/work-history
devostasis work audit --store /private/work-history --provider gitlab \
  --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID
```

The observer verifies engine/policy/project before publication, emits the bundle
path/id and an immutable invocation receipt, and preserves failed/partial runs.
Disabled binding records a DISABLED invocation with no network/canonical write;
missing/wrong binding is an error. A fresh generation does not overwrite an older
receipt. Scheduling belongs to the caller: use
[gitlab-operations.yml](../examples/work/gitlab-operations.yml) or the protected
[GitHub reusable workflow](../.github/workflows/work-operations.yml), with a
protected private durable volume and reviewed default-branch configuration.
Both remain observational jobs. Candidates use the existing isolated `work run`.
Templates do not install runners, create schedules or activate production.

History transfer includes all admitted bundles, invocation receipts and reported
results for exactly one project. Keep archives in the same private permission
domain as their source history; CI artifact expiry is not a backup policy.

```sh
devostasis work export-history --store /private/work-history --provider gitlab \
  --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID --output history.zip
devostasis work verify-history --archive history.zip --provider gitlab \
  --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID
devostasis work import-history --archive history.zip --store /private/restored-history \
  --provider gitlab --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID
```

The archive is deterministic, bounded and verified before publication. No paths
are extracted. Restore can be retried after interruption; existing newer latest
stays latest, and candidates stay candidates. Corrupt history, foreign projects,
same-time conflicts and changed same-id bytes are errors. Audit every restored
store and compare its report with the source at the same explicit `--at` time.
The default cap is 64 MiB (`--max-bytes` up to 512 MiB); fixed per-category record
caps are documented in [the contract](spec/work-operations.md).

After a consumer acts under its own authority, report the original acceptance:

```json
{"actor":"YOUR_LOGIN","outcome":"REPORTED_COMPLETE","notes":"Bounded qualification completed.",
 "acceptance":[{"criterion":"EXACT ORIGINAL ACCEPTANCE TEXT","status":"PASS",
                "evidence":["issue:123#qualification"]}]}
```

```sh
devostasis work record-result --bundle BUNDLE_DIRECTORY --packet packet.json \
  --result result.json --store /private/work-history --provider gitlab \
  --endpoint https://gitlab.example/api/v4 --expected-project-id NUMERIC_ID \
  --actor YOUR_LOGIN --policy-version YOUR_POLICY_VERSION
```

All criteria must appear in their original order, with evidence references for
PASS. BLOCKED/ABANDONED may record UNKNOWN/FAIL. The report retains the full packet
and a digest-bound append-only record. `work verify-result --record RECORD_PATH`
uses the same bundle/project/actor/policy arguments to check it offline. These
are caller reports; independent acceptance, claim/review/merge/deployment stay
in the consumer's existing process. Recheck a live source before action.

Parallel collection uses one shared quota/deadline. A binding selects workers
1..8; direct `work collect/run --workers 4` also supports it. For a capped run,
reduce selection, raise an intentional budget or recover explicitly missing
evidence. A selected generation cannot be labelled the complete backlog.
