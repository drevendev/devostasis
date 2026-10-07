# Optional report profiles — devostasis.work.v1

`evidence.json` is a separate companion input: contract, kind=evidence,
sources (at most 100). Missing evidence is not a zero score or a proven clean
repository. An empty list says no producer was selected. An adopter expecting
a producer must supply UNAVAILABLE when it did not run.

Each source has profile, producer, version, subject, observed_at,
COMPLETE/PARTIAL/UNAVAILABLE status, nullable reason and nullable report.
Report contains canonical base64 source bytes and their SHA-256 digest. The
envelope binds exact immutable project identity and commit, producer/profile
version, collection time and completeness. Individual reports are bounded to
2 MiB, 10,000 normalized locations, one source per producer/profile. UNAVAILABLE
requires a reason and no report; PARTIAL requires a reason. Digest mismatches
and duplicate envelopes are inadmissible. Malformed producer payloads become
explicit recovery gaps; no partial parser results survive a parser failure.

Paths must be plain repository-relative POSIX paths: no absolute path, drive,
backslash, empty/dot/parent component, URI or encoded path. Source locations
have positive line numbers and optional symbols. Unknown XML DTD/entities,
duplicate JSON members and non-finite numbers are rejected. Reports do not
provide commands, permissions or business priorities. Raw messages are not
used as instructions or emitted as trusted Markdown. An analysis task means
inspect and verify the observed trigger, not that a bug was proved.

| Profile | Admitted evidence and verification |
| --- | --- |
| sarif.v1 | SARIF 2.1.0 runs/results with ruleId and physical repository location; pass/notApplicable ignored; unresolved uriBaseId refused |
| junit.v1 | testsuite/testsuites, testcase with file, line, name and failure/error/flakyFailure/flakyError; reproduce the exact test |
| cobertura.v1 | coverage with a positive lines-valid denominator; class filename and instrumented line number/hits; zero-hit lines trigger behavior/test assessment |
| performance.v1 | measurements with name/path/line, positive integer baseline, integer current, consumer limit_percent, unit and immutable baseline_revision; regression uses integer cross multiplication |

Cobertura percentages and JUnit timings are not used in scoring. Performance
units/benchmark methodology are declared by producer/version; the threshold
is explicit consumer evidence, not a Vital rule. Missing location or coverage
denominator cannot produce a current analysis item. Duplicate finding locations
within a source reject that source rather than hiding conflicting evidence.
Finding identity hashes profile, producer, rule, path, line and symbol; exact
revision and producer version bind the occurrence separately. Changed
revision/expiry reconsiders a disposition. Same-revision acknowledgements
remain explicit exclusions with their reference. IMPLEMENTING suppresses work
only with a live correlated implementation.

Wrong repo/revision and expired/future reports produce bounded recovery gaps,
not findings for the current revision. Reports are verified and re-normalized
offline from persisted bytes. See [work-scope.md](work-scope.md) for execution
boundaries and [../work-scopes.md](../work-scopes.md) for producer examples.
