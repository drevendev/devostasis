# GitHub adapter (devostasis.github.v1)

Read-only. Only `GET` requests, `Accept: application/vnd.github+json`,
API version `2022-11-28`, page-based pagination with 100 items per page.

## Requests per project

| Purpose | Endpoint | Cap |
| --- | --- | --- |
| identity | `GET /repos/{o}/{r}` | 1 (failure aborts the project: no subject, no bundle) |
| commits | `GET /repos/{o}/{r}/commits?sha=<default>&since=<28d>` | 30 pages (3000 commits) |
| change requests | `GET /pulls?state=open` and `GET /pulls?state=all&sort=updated&direction=desc` until older than 28 days | 20 pages each |
| issues | `GET /issues?state=open` and `GET /issues?state=all&since=<28d>` (pull requests filtered out) | 20 pages each; skipped when `has_issues` is false |
| branches | `GET /branches`, then `GET /commits/{sha}` for heads not on the default branch | 2 pages, 60 head lookups |
| targets | `GET /milestones?state=all` | 3 pages; skipped when `planning.source = none` |
| releases | `GET /releases?per_page=30` | 1 page |
| verification | `GET /actions/workflows` (count), `GET /actions/runs?branch=<default>&created=>=<14d>`, `GET /actions/runs/{id}/attempts/{n}` for reruns | 20 pages, 5 attempts per run, 60 attempt lookups |
| fallback verification | `GET /commits/{sha}/check-suites` per revision, paginated, only when no Actions run was seen: none exists in the window, or the workflow lookup itself failed (recorded as `WORKFLOWS_UNAVAILABLE:<reason>`) | 100 revisions, 3 pages each |

A typical small repository costs 10 to 30 requests; a very active one
(hundreds of merged change requests and more than a thousand default-branch
commits a month) costs 50 to 150. Enumerations are newest-first, so a capped
enumeration is a lower bound of the true activity and is reported as
`PARTIAL`.

## Failure mapping

| HTTP | Status | Reason code |
| --- | --- | --- |
| 401 | FORBIDDEN | `UNAUTHENTICATED` |
| 403 rate limited | ERROR | `RATE_LIMITED` (retryable) |
| 403 tier or plan message | UNAVAILABLE | `TIER_UNAVAILABLE` |
| 403 other | FORBIDDEN | `FORBIDDEN` |
| 404 | UNAVAILABLE | `NOT_FOUND` |
| 410 | UNAVAILABLE | `DISABLED` |
| 429 | ERROR | `RATE_LIMITED` |
| 5xx, network | ERROR | `PROVIDER_ERROR`, `NETWORK` |

A capped pagination yields `PARTIAL` with `PAGINATION_CAPPED`; unresolved
branch heads yield `PARTIAL` with `BRANCH_HEADS_UNRESOLVED`; incomplete
attempt history yields `PARTIAL` with `ATTEMPT_HISTORY_INCOMPLETE`. The
workflow-runs listing is read against the provider's own `total_count`: a
filtered `/actions/runs` query stops at 1,000 results and answers the next
page empty, so a listing that ends short of its total is `PARTIAL`
(`PAGINATION_CAPPED`), never complete. A listing that repeats a row between
pages moved while it was read (page-number pagination over a list that
grew): each commit and run counts once, and the inventory is `PARTIAL` with
`LISTING_SHIFTED`, because a row may also have been skipped. A failure below
`urllib` (`http.client.IncompleteRead`, `BadStatusLine`) is a network
failure like any other, an error body that cannot be read keeps its status,
and a body nested beyond the decoder's depth is `MALFORMED_RESPONSE`.

## Successful payloads are validated before they are read

A 200 is not proof that the body is usable. Every field a collector consumes
is typed evidence, checked before any semantic use, and a body that does not
establish it is `ERROR` with `UNEXPECTED_PAYLOAD` for that inventory alone:
the other inventories are still collected, the project still produces a
bundle, and no value is coerced, defaulted or skipped in the malformed one's
place (research audits `PV-AUDIT-GITHUB-*-PAYLOAD-001`). Concretely:

| Surface | Required of a successful answer |
| --- | --- |
| repository metadata | an object with an integer `id`, a non-empty `default_branch`, boolean `has_issues` and `archived`, and `pushed_at` null or a timestamp; a body that does not establish them fails the project (`CollectionError`) rather than guessing `main` or reading a string's truthiness |
| commits | every row an object with a non-empty `sha`, an object `commit`, object or null `committer` and `author`, and at least one readable date; a commit without a date is not skipped |
| change requests | every row an object with an integer `number`, readable `created_at` and `updated_at`, null or readable `merged_at` and `closed_at`, boolean `draft`, object or null `user`; the window predicate itself validates `updated_at`; linkage-bearing `title`, `body` and `milestone` of the wrong type are not an absent link and not a failed project: the record keeps what could be read and names the rest in `linkage_unresolved`, and Direction counts the change request unresolved unless a readable reference already links it (`PV-DIRECTION-INCOMPLETE-001`) |
| issues | every row an object with an integer `number`, readable timestamps, a list of objects with string `name` as `labels`, object or null `user` |
| branches | every row an object with a non-empty `name`, an object `commit` with a non-empty `sha`, boolean `protected`; a head detail that cannot be read leaves that head unresolved (`PARTIAL / BRANCH_HEADS_UNRESOLVED`), never stale or fresh |
| milestones | every row an object with an integer `number`, null or readable `due_on`, integer or null `open_issues` and `closed_issues` |
| releases | every row an object with boolean `draft` and `prerelease`; a draft is ignored only once `draft` is positively `true`; every other row needs a non-empty `tag_name` and a readable `published_at`, and one without is a failure, never an omission |
| workflow runs | an object with a `workflow_runs` list and a non-negative integer `total_count`; every run an object with a non-empty `head_sha` (validated before the window is applied), an integer `id`, an integer `run_attempt` >= 1, a `status` string, a null or string `conclusion`, and null or string `name`, `event` and `html_url` and a null or integer `workflow_id`, because the parent record carries them into the bundle; a workflow count that is absent or not a non-negative integer |
| run attempts | an object whose `id` is the run asked for and whose `run_attempt` is the number asked for; anything else is not this run's history and fails the series |
| check suites | an object with a `check_suites` list (a missing list is not zero suites); every suite an object with an integer `id`, a `status` string, null or string `conclusion`, null or object `app`, null or string `url`, and an integer `latest_check_runs_count`, which is never assumed |
| register files | an integer `size`, required rather than defaulted; string `content` in base64 (line breaks allowed, nothing else outside the alphabet) that decodes to no more than the byte bound; a document nested beyond the decoder's depth is invalid; the register document itself is judged by the register contract (`INVALID_REGISTER`) |

## Redirects

The transport follows a redirect only to the configured API origin (scheme
and host of the API base, `https://api.github.com` unless configured
otherwise), because `urllib` copies the `Authorization` header onto the
redirected request. A redirect to another origin, or from HTTPS to HTTP, is
refused as `ERROR / REDIRECT_REFUSED` and the token never leaves
(`PV-AUDIT-GITHUB-REDIRECT-AUTH-001`); the API's own redirects, such as a
renamed repository, stay on the origin and still work.

## Retry hints

A retryable answer (`429`, a rate-limited `403`, `5xx`) is retried after the
wait `Retry-After` or `X-RateLimit-Reset` asks for, within the bounded retry
policy. A hint that cannot be read as a finite number (`inf`, an overflowing
exponent, text) is no hint at all: the deterministic backoff applies and,
when retries are exhausted, the answer's own classification stands
(`RATE_LIMITED`, `PROVIDER_ERROR`), never a host exception
(`PV-AUDIT-GITHUB-RETRY-HEADER-001`).

## Conditional cache

The entity-tag cache (`--cache`, `devostasis.http-cache.v2`) is an
optimization and never a truth surface. An entry is replayed after a `304`
only when its complete shape is readable and the body it holds still hashes
to the digest recorded beside the tag; a corrupt, foreign or older entry is a
miss and costs exactly one unconditional request, never a replayed body
(`PV-AUDIT-GITHUB-CACHE-INTEGRITY-001`). The digest guards against
accidental corruption, not against an adversary who can rewrite the file.

The check-suite surface carries its own coverage (issue #12 finding 1). The
series records how many revisions were planned and examined
(`suite_revisions_planned`, `suite_revisions_examined`), whether every suite
page was read (`suites_complete`) and why sampling stopped
(`suites_stop_reason`: `CHECK_SUITE_SAMPLE_CAPPED` past 100 revisions,
`PAGINATION_CAPPED` past 3 pages of one revision, `REQUEST_BUDGET_EXHAUSTED`,
or the failure reason of the fetch that broke off). Any of those makes
`ci.revision_verdicts_14d` `PARTIAL` with `CHECK_SUITES_INCOMPLETE`; the
parents already collected are kept, a failure among them stays, and a
truncated sample is never an exact favourable result.

## `ci.configured`

`true` when the repository has at least one workflow or any verification
parent was observed; `false` only when there are zero workflows and no check
suite on every revision of the window, each read to its last page; `UNKNOWN`
with `SAMPLE_INCOMPLETE` when any of them could not be read (more revisions
than could be sampled, a failed or refused fetch, a page cap). A revision
whose first suite page the budget refused is not counted as examined.

## Normalization decisions

- Commit time is the committer date; active days are distinct UTC dates.
- A pull request is `MERGED` when `merged_at` is set, `CLOSED` when closed
  without merge, else `OPEN`. Its planning target is its milestone number;
  the target state is the milestone state.
- Only Actions runs whose `head_sha` is a default-branch commit of the window
  become parents; runs of pull-request branches are not default-branch
  verification.
- Skipped workflow runs are parents with `NOT_EXECUTED`; a revision whose
  only parents are skipped counts as verification activity without a decisive
  verdict.

## Not collected in this version

Branch protection and rulesets, commit statuses, external check apps when
Actions runs exist, GitHub Projects fields, pull request to issue linkage,
review latency, deployments and environments, discussions. Each is listed in
the ROADMAP with the observation it would feed.

## Token handling

Order of resolution: `--token`, the configured `token_env`,
`DEVOSTASIS_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, then `gh auth token`.
Without a token only public repositories are readable and the unauthenticated
rate limit applies. The token is sent only to `api.github.com` and is never persisted.
