# Contributing

Devostasis is small on purpose. Contributions are welcome when they keep the
runtime deterministic, model-free and honest about missing evidence.

## Branches and releases

- `master` holds released versions only. Nothing lands there except a release
  merge and its tag.
- Work happens on a release branch named `release/<version>` (for example
  `release/0.1.0`). Feature branches target the current release branch.
- When a release branch is complete and green, it is merged into `master`
  with a merge commit and tagged `v<version>`.
- Dependabot version-update PRs also target the active release branch. When
  opening the next release, advance both `target-branch` entries in
  `.github/dependabot.yml`; do not send maintenance directly to `master`.

## Linking a pull request to a target

This repository declares its planning targets in
[`.devostasis/targets.json`](.devostasis/targets.json) and its registered
maintenance obligations in [`.devostasis/debt.json`](.devostasis/debt.json).
Devostasis observes itself through those two files, so they are also the
worked example an adopter copies.

A pull request that advances a target carries a line in its description:

```text
Target: B1
```

Several lines link to several targets. The marker is the only linkage the
engine accepts: it never infers intent from a branch name, a title or prose,
because a heuristic that guesses drifts from run to run. A marker naming an id
that is not in the register counts as unlinked and is reported separately, so
a typo is visible rather than silently flattering.

Two rules keep the registers honest:

- a target gets a `due` date only when the date is real. An invented deadline
  moves Horizon from `DECLARED` to `VISIBLE` without moving the project;
- an item belongs in the debt register when the current code carries a cost.
  Work we intend to do is a target, not debt.

Adding, closing or renaming a target is an ordinary change. Changing the
register *path* or the debt `mapping_version` changes the semantic
configuration, so the next bundle is deliberately `INCOMPARABLE` with the
previous one.

## Ground rules

1. **No language model in the runtime path.** Collection, evaluation,
   comparison and rendering are pure functions of recorded evidence and the
   declared policy version. A change that needs "judgement" belongs in the
   research process, not in the code.
2. **Unknown is not zero.** A collector that cannot prove a value must emit an
   explicit status. A Vital that lacks evidence must say UNKNOWN or emit a
   conservative DEGRADED bound. Never make a project look healthier because
   data was missing.
3. **Thresholds are policy.** The numbers in `src/devostasis/policy.py` are
   provisional calibration constants. Changing one requires a new
   `POLICY_VERSION`, a fixture that shows the mistaken classification, and an
   argument that the change does not break the other fixtures. One
   repository "looking right" is not an argument.
4. **Conformance cases keep their identifiers.** Tests are named after the
   research case they implement (C1..C7, T1..T9, R1..R57, V1-01..V1-15,
   ART-01..ART-25, RPT-1..RPT-10, ORDER-01..15, INT-UNKNOWN-01..06,
   INT-TOTAL-01..14, CLU-INCOMPLETE-01..20, CLU-PARTIAL-TRUST-01..08,
   ACT-COV-01..05); a repair of a research audit uses the regression labels
   the audit names, and anything else is an implementation-local label that
   never claims a research identifier (`DEV-ORDER-01..03`). A new rule needs a new case
   with a new identifier; identifiers are never reused. A case can be a pytest
   function or an executable vector under `tests/vectors`
   ([docs/spec/vectors.md](docs/spec/vectors.md)); either way it is cited in
   `docs/spec/conformance.md`, and a citation that does not resolve fails the
   build.
5. **Neutral bands stay neutral.** Direction `FULLY_LINKED` and Debt `PRESENT`
   are facts, not verdicts. Renderers never alias them into ALIGNED, ON_TRACK,
   HEALTHY or similar words, and never introduce colours or numbers that imply
   an ordering the contract does not declare.
6. **Adapters are read-only.** No adapter may perform a mutating request.

## Development

```bash
python -m venv .venv
. .venv/bin/activate            # .venv\Scripts\activate on Windows
pip install -e ".[dev]"
python -m pytest
```

The test suite needs no network, and it runs every conformance vector as an
ordinary test. `devostasis vectors` runs the same corpus from the command
line, and `devostasis vectors --case ORDER-07` runs one case. Run the real
adapter against a repository you can read with
`devostasis observe --repo owner/name` (a token is taken from
`DEVOSTASIS_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`).

## Pull request checklist

- the description carries `Target: <id>` when the change advances a declared
  target, and the id exists in `.devostasis/targets.json`;
- tests pass on Python 3.12 or newer, and no new dependency was added to the
  runtime;
- every new observation key or derived metric is documented in `docs/spec/`;
- every semantic change bumps the relevant contract or policy version and is
  listed in `CHANGELOG.md`;
- the example bundle in `examples/sample-bundle` still verifies, or was
  regenerated on purpose;
- nothing private entered the repository: no tokens, no private repository
  content, no personal data.

## Reporting spec disagreements

The specification behind this implementation is maintained in a separate
research process. When the implementation disagrees with the specification,
or a rule produces a clearly wrong classification on real data, open an issue
labelled `for:researcher` with the observation set that triggers it. The
implementation follows the accepted specification until the specification
changes; it does not fix rules ad hoc.
