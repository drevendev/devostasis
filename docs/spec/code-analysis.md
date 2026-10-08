# Offline code analysis contract

Implementation-owned companion, introduced in 0.6.0. No accepted research
Vital rule, ordering or Work Instrument judgement changes. Its identifiers are
`devostasis.code-analysis.v1`, `devostasis.code-policy.v1`,
`devostasis.code-engine.v1`, `devostasis.code-packet.v1` and
`devostasis.code-comparison.v1`. Case IDs below use the local DEV-CODE family.

## Admission and collection

Policy is a closed object: `contract`, `version`, `grammar`, `include`,
`exclude`, `source_roots`, `budget`, `limits`, `history`. Grammar is
PYTHON_3_12; paths are unique relative prefixes, with `.` allowed only as a
source root. Longest matching source root gives the declared Python module.
Budgets contain `max_files` (1..5000), `max_file_bytes` (1..4194304),
`max_total_bytes` (1..67108864, at least the per-file cap), and `seconds`
(1..3600). Limits contain `complexity`, `function_lines`, `file_lines`
(1..100000). History contains explicit boolean `enabled`, `days` (1..3650)
and `max_commits` (1..10000). Defaults are in `code policy`; thresholds are
local source triage policy, not calibrated health bands. Unknown fields,
boolean integers, unsafe paths and unbounded values are rejected.
The seconds deadline covers Git acquisition; offline replay is bounded by
source/object/bundle sizes and does not invoke subprocesses.

`inputs.json` is a closed object with `subject`, `observed_at`, `entries`,
`sources`, `history`, `proof`. Subject contains `kind: LOCAL_GIT`,
`object_format: sha1|sha256`, sorted unique `roots`, `repository_id`, full
`revision` and `tree`. Repository identity hashes object format and locally
observed roots; it is not an authenticated forge/project identity. Observation
timestamps use the existing UTC timestamp contract. Collection resolves the
revision once and uses only immutable IDs thereafter, with replacements, lazy
fetch, filesystem monitors, external diff and text conversion disabled. Source
acquisition does not inspect index/worktree modifications or execute hooks.
Git processes receive only required OS/path/home/locale environment and explicit
read controls; inherited Git directory/config injection and unrelated credential
variables cannot override the selected repository (#74).
Output/time/object caps fail explicitly rather than publish an empty success.

Each entry contains decoded safe `path` or null, canonical `path_base64`,
Git `mode`, `kind`, `object_id`, `size` (null only for a gitlink), `status` and
`reason`. Entries sort by raw path bytes and cover every leaf in the proved
tree. In-policy regular `.py` blobs within all budgets are ADMITTED. Excluded
prefixes are OUT_OF_SCOPE/POLICY_EXCLUSION; other regular languages are
UNSUPPORTED/LANGUAGE_UNSUPPORTED. UNAVAILABLE reasons are UNSAFE_PATH,
SOURCE_LINK_OR_SUBMODULE, FILE_BYTE_CAP, FILE_COUNT_CAP and TOTAL_BYTE_CAP.
`sources` maps exactly admitted paths to canonical base64 of unmodified bytes.

`proof` contains the raw base64 commit object and an object-ID-to-base64 map
of every reachable tree. Verification computes framed Git object hashes,
checks the commit/tree link, expands all trees, checks the entire inventory and
hashes every admitted blob. Tree proofs are bounded to 8 MiB and 10000 objects,
commit proof to 1 MiB, expanded leaves to 100000. Missing/extra/duplicate tree,
path or source data is rejected. SHA-1/SHA-256 Git format is explicit. This
establishes a commitment to source bytes, not authenticated commit authorship.

History contains `status`, unique `reasons`, `start`, `end`, `commits`. The
window is inclusive, ends at observed_at and spans policy days. COMPLETE means
the bounded collector exhausted its selected non-merge ancestor walk;
PARTIAL retains admitted rows and cap/shallow/path gaps; UNAVAILABLE admits no
commits; NOT_REQUESTED requires history disabled and admits no commits.
Each commit has `revision`, `committed_at`, `changes`; changes contain `path`,
`added`, `deleted` (both null for binary changes). Changes sort by path,
commits by timestamp/full ID, with no duplicates. Counts, traversal roots and
history completeness are recorded acquisition claims, not proved ancestry.
Offline verification replays those observations; proof hardening is #73.

## Derived source evidence

`analysis.json` contains `engine`, `subject`, `observed_at`, `coverage`,
`files`, `findings`, `imports`, `import_cycles`, `hotspots`, `history` and
`authority`. Coverage is PARTIAL if any source is UNAVAILABLE or PARSE_ERROR;
otherwise COMPLETE if Python inputs are applicable, else NOT_APPLICABLE.
Unsupported languages/exclusions remain visible beside that scoped coverage.
History coverage is independent and does not disappear behind source coverage.

File rows contain `path`, `object_id`, `status`, `reason`, `module`, `lines`,
`functions`. Admitted Python uses its declared encoding cookie/BOM;
unavailable encoding becomes SOURCE_ENCODING_UNAVAILABLE. AST parsing at
grammar 3.12 yields ANALYZED or PARSE_ERROR/PYTHON_3_12_SYNTAX. Lines are
decoded splitlines count; unavailable/unsupported inputs retain null metrics.
Function records contain qualified `symbol`, `line`, `end_line`, inclusive
`lines`, `complexity`, `async`. Repeated symbols receive deterministic #2 etc.
Decision count starts at one and adds if/for/async-for/while/if-expression/
exception handlers, boolean operand count minus one, comprehension generators
and filters, and match case count minus one. Nested functions/classes/lambdas
are excluded from the enclosing body count, as are signature defaults,
annotations and decorators. This is a named syntactic count;
decorators, runtime dispatch and path reachability are not evaluated.

Rules: DS-PY-SYNTAX, DS-PY-COMPLEXITY, DS-PY-FUNCTION-SIZE, DS-PY-FILE-SIZE,
DS-PY-BARE-EXCEPT and DS-PY-IMPORT-CYCLE. Size/count rules trigger strictly
above configured limits; bare except catches BaseException. Findings contain
`id` (digest of rule/path/qualified symbol), `rule`, `level`, `path`, `symbol`,
`line`, `end_line`, fixed `message`, rule-specific `evidence`, `related_paths`.
Syntax is error, other rules warning. Syntax/file findings use <module>;
bare exceptions use qualified traversal ordinals. Cycle symbol hashes its
sorted path component. Findings sort by path/line/rule/symbol.

Import rows contain `from`, `to`, `module`, `line`, `status`, `candidates`.
Only a unique declared module with analyzed source is RESOLVED. Multiple
roots are AMBIGUOUS, missing syntax/bytes UNAVAILABLE, other names
EXTERNAL_OR_UNRESOLVED. Relative imports outside the declared package remain
unresolved. Strongly connected components of RESOLVED edges form sorted
`import_cycles`, including self edges. These are static graph cycles, not
proof of runtime initialization failure; dynamic imports and package export
semantics are not executed. Implicit parent imports are not inferred.

Hotspots contain current in-scope `path`, number of observed distinct
non-merge `revisions`, summed `added`, `deleted`, `binary_changes` and history
`coverage`; sort descending revisions, then added+deleted, then path. Current
non-Python files can appear with change evidence without invented AST metrics.
Analysis history retains input status/reasons/start/end, omitting commit rows.
Authority is STATIC_SOURCE_EVIDENCE, without execution, independent acceptance,
health score or merge authority.

## Artifacts and consumers

Exactly six members: inputs.json, policy.json, analysis.json, findings.sarif,
report.md, manifest.json. JSON uses the existing canonical byte contract.
Manifest contains contract, engine, subject, member byte digests and bundle_id
(digest of the manifest without that ID). Total bundle cap is 128 MiB.
Verification recomputes source admission, derived JSON, SARIF and Markdown,
then requires every byte to match. Merely updating outer hashes is insufficient.
Bundle destinations are immutable, reject links and foreign/changed contents,
and publish atomically under a parent lock. Matching content is idempotent.

SARIF 2.1.0 retains every finding, rule, source revision, stable fingerprint,
physical path/line/span and source/history coverage. Markdown escapes source
strings and displays up to 100 findings and 20 hotspots with visible totals.
It grants no freshness, live-state or acceptance authority.

Comparisons contain contract, before/after bundle IDs, status, reasons,
findings, files, authority. Different local identity or exact policy body gives
INCOMPARABLE. Finding rows contain id/state/before/after: PERSISTING for equal
records, CHANGED for altered records sharing ID, NEW/FIRST_OBSERVED when new,
RESOLVED/UNOBSERVED when absent. NEW/RESOLVED require every involved path on
the opposite side to be ANALYZED or absent from the complete proved inventory;
other statuses yield the conservative alternative. File transitions retain
path/state/before_status/after_status with ADDED/REMOVED/CHANGED/UNCHANGED
based on tree presence and blob ID. No aggregate ordering is inferred.

Packets contain contract, analysis_bundle_id, subject, budget, files,
total_bytes, authority, packet_id. Budget has max_files (1..1000) and
max_bytes (1..67108864); files are nonempty unique sorted admitted paths with
path/object_id/size/base64, preserving whole blobs. Verification reconstructs
the packet against its verified bundle. No metadata truncation, duplicated
path, relabelled authority or changed bytes are admitted.

Work export requires an admitted forge inventory and exact full revision
equality. It supplies sarif.v1 under the existing evidence contract, preserves
the source observation time and carries PARTIAL for any non-COMPLETE Python
coverage. Standalone SARIF encodes relative URI references; work export retains
literal repository-relative paths as required by the historical sarif.v1
profile, including filenames with spaces or URI metacharacters. An optional
export time may only equal the recorded time. Consumer
freshness and source/subject admission still run; native code evidence proposes
analyze_code work without closing acceptance, B1, B7 or instrument gates.
Public manifest/policy/packet schemas accompany the executable admission
rules. Local conformance citations are in [conformance.md](conformance.md).
