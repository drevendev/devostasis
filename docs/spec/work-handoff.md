# Work scope v2 and bounded consumer handoff

`devostasis.work.v2` and `devostasis.work-engine.v2` add explicit mutable
source bindings to the five-queue companion. V1 stored generations still
replay with their original shape/engine. This is an implementation-owned
consumer contract; no core Vital or execution authority is added.

`devostasis.work-source.v1` records DEFAULT_BRANCH, BRANCH or CHANGE, target
project identity, immutable source project identity, source locator, named ref
and full revision. GitHub fork PRs and GitLab fork MRs retain their source
project. Candidate collection resolves its named source and proves commit
existence in that project. SHA alone is insufficient for live collection.
Offline attested v1/v2 inputs remain proposals; a live handoff requires binding.
Moved/force-pushed, deleted, inaccessible, ambiguous or wrong-project sources
fail closed. Candidate generations do not replace canonical latest.

`devostasis.work-handoff.v1` is a read-only source packet. `work handoff`
verifies its scope, actor, policy and expected project, checks TTL, resolves
the selected binding, refreshes only selected work/dependencies, checks revision,
owner, action, acceptance and read set, then reads only declared paths at the
immutable revision. It proves regular blobs in the pinned Git tree, rejects
symlinks/submodules, enforces file/byte/request/page/time caps, validates exact
file sizes and Git blob digests, and resolves the mutable source again.
Incomplete or oversized reads produce an error, never a partial executable packet.

Packets bind scope bundle/digest, exact item/acceptance, source binding, refreshed
inventory digest, checked time, file bytes/digests and total budget consumption.
`work verify-handoff` validates the packet against its verified original scope
without API access. A digest is integrity, not principal authentication. Deliver
packets through a trusted channel and recheck source state immediately before
any authorized action; offline verification cannot prove present freshness.
Commands in repository-controlled content are data, never granted authority.

GitLab can use a host-specific existing `glab` login when no environment token
is selected. The bridge permits bounded same-endpoint GET only and never reads
the credential into Devostasis. It disables persistent caching because glab's
credential partition is not attested. Explicit token-env mode retains partitioned
caching. Namespaced projects resolve to immutable numeric IDs. `--change` and
`--registered-only` declare selected coverage; neither means full open inventory.

GitLab aggregate approval APIs still do not prove exact-head independent review
(issue #58). Large full-inventory throughput is issue #62. Durable private
scheduled publication and sustained calibration remain deployment qualifications;
one successful shadow packet does not establish them.
