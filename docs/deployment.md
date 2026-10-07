# Deployment

For the 0.5.0 Evidence to Action companion, five queues, producer reports,
GitHub/GitLab CI and protected durable history, see
[work-scopes.md](work-scopes.md). Its store and contract are separate from the
Vital bundles described here.
For explicit caller bindings and verified private history transfer, see
[work-operations.md](work-operations.md).

There are two ways to run Devostasis, and they complement each other:

| | Fleet observer | Self-observation |
| --- | --- | --- |
| Who reads whom | one history repository reads many projects | a project reads itself |
| Token | one read-only personal access token | none: the workflow's own `GITHUB_TOKEN` |
| History and deltas | full, in one place | only when a history store is given for comparison |
| Meant for | the human overview across projects and cross-project routing | the project's own autonomous loop deciding what to work on |
| Change in the project | none | one job in a workflow |

## Self-observation from a project (no secrets)

Add a job that calls the reusable workflow shipped in this repository:

```yaml
permissions:
  contents: read
  issues: read
  pull-requests: read
  actions: read
  checks: read

jobs:
  vitals:
    uses: drevendev/devostasis/.github/workflows/observe-self.yml@v0.5.0
    with:
      debt-labels: "type:debt"          # optional: issue labels that mark debt items
      # planning-source: file             # optional: targets register instead of milestones
      # planning-path: devostasis/targets.json
      # history-repo: owner/history       # optional: compare with the latest bundle there
    # secrets:
    #   history-token: ${{ secrets.HISTORY_READ_TOKEN }}   # only if history-repo is private

  decide:
    needs: vitals
    runs-on: ubuntu-latest
    steps:
      - run: echo "work on ${{ needs.vitals.outputs.attention }}"
      - if: contains(fromJSON(needs.vitals.outputs.levels).integrity, 'CRITICAL')
        run: echo "verification first"
```

What the job does: installs Devostasis at the given ref, observes the calling
repository with the workflow's own token, writes the status card and the
attention order to the job summary, uploads the bundle as the artifact
`devostasis-bundle`, and exposes outputs: `attention` (first attention entry,
e.g. `integrity CRITICAL`), `attention-order`, `levels`, `bands` and `gauges`
as JSON, `bundle-id`, `comparison-status`. Without `history-repo` every run
is a `BASELINE` bundle, which is enough to decide the current focus; with it
the run compares against the latest bundle of that store without writing to
it.

The caller's `permissions` block must grant the five read scopes above. A
called workflow can only narrow the caller's token, never widen it, so when
the caller grants less (the default for a new repository is read-only
contents) GitHub refuses the run before it starts, with an error naming the
scope the nested `observe` job asks for, and no bundle is produced at all.

### The worked example is this repository

Devostasis observes itself this way, with register files rather than
milestones and labels. Its caller
([`.github/workflows/self-observe.yml`](../.github/workflows/self-observe.yml))
passes:

```yaml
    with:
      planning-source: file
      planning-path: .devostasis/targets.json
      link-marker: "Target:"
      debt-path: .devostasis/debt.json
      debt-mapping-version: "2026-09-06"
```

and the two registers live in [`.devostasis/`](../.devostasis). Copy that
shape rather than the fictional paths in
[the register specification](spec/registers.md): the files there are real,
maintained by hand, and small enough to read in a minute.

Both registers are read from the repository's **default branch**, not from the
branch the workflow runs on. A register added on a working branch is
`UNAVAILABLE / REGISTER_NOT_FOUND` until it merges, and Horizon, Direction and
Debt are `UNKNOWN` in the meantime. That is the contract failing closed rather
than guessing, and it means the register lands before the configuration that
points at it.

Self-observation is a convenience shape, not durable history. The bundle
lives in the job's workspace and in the uploaded artifact, which expires with
the repository's artifact retention; nothing is appended to a canonical
store, and without `history-repo` every run is a `BASELINE` bundle. A project
that needs previous-vs-current deltas, an audit trail or replay must be
observed into a companion history repository as described below (decision
recorded by the research review of the reporting contract).

## Fleet observer with a companion history repository

The recommended production setup for history is a **companion history
repository**: a separate, private Git repository that holds the
configuration, runs Devostasis once a day in GitHub Actions, and commits the
bundles to itself. The observed repositories are never written to, and the
history repository is never observed, so storage activity cannot leak into
project telemetry.

## 1. Create the history repository

Create a private repository, for example `devostasis-history`, with:

```text
devostasis.json                 the fleet configuration (store.path = ".")
.github/workflows/observe.yml   the daily job below
.gitattributes                  * -text   (store the bundles byte for byte)
projects/                       written by the job
```

`report.md` and `effective-config.json` are verified by the digest of their
bytes. A clone with `core.autocrlf=true` (the Git for Windows default) would
check them out with CRLF line endings, and every report would then fail
`devostasis verify` and turn the next local comparison into a
`HISTORY_GAP`. `* -text` (or `* text=auto eol=lf`) in the store's
`.gitattributes` keeps the checkout identical to what was committed.

The history repository must be at least as private as the most private
repository it observes; bundles contain issue and pull request titles,
commit subjects and branch names.

## 2. Create a read-only token

Create a fine-grained personal access token with read-only access to the
repositories you want to observe: Contents, Issues, Pull requests, Actions
and Metadata. Store it as the repository secret `DEVOSTASIS_TOKEN` in the
history repository. Devostasis never persists the token. A fine-grained token
is bound to one resource owner (a user or one organization); repositories of
other owners need their own token and configuration file, or use
self-observation instead.

## 3. The workflow

```yaml
name: Observe

on:
  schedule:
    - cron: "17 5 * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: devostasis-observe
  cancel-in-progress: false

jobs:
  observe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Devostasis
        run: python -m pip install --quiet "git+https://github.com/drevendev/devostasis@v0.5.0"
      - name: Observe every configured project
        id: run
        continue-on-error: true
        env:
          DEVOSTASIS_GITHUB_TOKEN: ${{ secrets.DEVOSTASIS_TOKEN }}
        run: devostasis run --config devostasis.json --store .
      - name: Commit bundles
        run: |
          git config user.name "devostasis"
          git config user.email "devostasis@users.noreply.github.com"
          git add projects
          git diff --cached --quiet || git commit -m "observe: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
          git push
      - name: Fail the job if any project failed
        if: steps.run.outcome == 'failure'
        run: exit 1
```

Add `--cache .devostasis-cache` and, if the fleet is large, a per-project
`--request-budget`, then persist the cache between runs with
`actions/cache`. Unchanged answers then cost a round trip instead of quota:

```yaml
      - uses: actions/cache@v4
        with:
          path: .devostasis-cache
          key: devostasis-etags-${{ github.run_id }}
          restore-keys: devostasis-etags-
      - name: Observe every configured project
        id: run
        continue-on-error: true
        env:
          DEVOSTASIS_GITHUB_TOKEN: ${{ secrets.DEVOSTASIS_TOKEN }}
        run: devostasis run --config devostasis.json --store . --cache .devostasis-cache
```

Only the `--cache` flag and the cache step are new; the `id`, the
`continue-on-error` and the token are the ones of the step above, and without
them the fleet runs unauthenticated and one failing project stops the job
before the bundles are committed.

The cache holds provider bodies, so it is as sensitive as the store: keep it
inside the private repository's own workspace and never in a public artifact.
A run without it is not wrong, only more expensive, and a bundle built from a
cached answer has the same identity as one built from a fresh fetch.

Pin the installed version to a release tag and bump it deliberately, so an
engine change never arrives unannounced in a nightly run. `cancel-in-progress`
is false so that two overlapping runs never race on the store; the store
itself refuses to overwrite an existing bundle.

## 4. Cadence

Once per day plus manual dispatch is the recommended cadence. Devostasis is
schedule-agnostic: every bundle compares itself with the previous successful
bundle, so a missed day is covered by the next run and never fabricates a gap
as "no change".

## 5. Reading the results

- `projects/README.md` is the fleet overview: latest bands per project.
- `projects/index.json` is the same fleet as data
  ([devostasis.fleet.v1](spec/history-and-reports.md)), for a control plane
  that routes attention without parsing Markdown. It carries no aggregate and
  no cross-project order: a fleet-wide priority is the consumer's policy, not
  ours.
- `projects/<forge>/<owner>/<repo>/latest/report.md` is the current report.
- `history/YYYY/MM/DD/<bundle_id>/` holds every immutable bundle; verify any
  of them with `devostasis verify --bundle <dir>`.

For example, the projects whose Integrity currently calls for the most
attention:

```bash
jq -r '.projects[] | select(.vitals.integrity.level == "CRITICAL") | .locator' projects/index.json
```

`devostasis index --store .` regenerates both files from the store without
observing anything.

## Local mode

Everything also works without Actions: `devostasis run --config devostasis.json --store ./history`
writes the same layout into a local directory. Commit it to any repository you
like, or keep it local.
