# Register files

Horizon, Direction and Debt read explicit metadata only. Repositories that do
not use GitHub milestones or labels can declare that metadata in two small
JSON files committed to the repository. The adapter reads them through the
contents API at the default branch; no free-form text is ever interpreted.

## Targets register (planning.source = file)

Configuration: `"planning": {"source": "file", "path": "devostasis/targets.json", "link_marker": "Target:"}`.

```json
{
  "schema": "devostasis.targets.v1",
  "targets": [
    {"id": "T-3", "title": "Release 1.2", "state": "open", "due": "2026-10-31"},
    {"id": "T-2", "title": "Release 1.1", "state": "closed", "due": "2026-08-15"}
  ]
}
```

- `id`: stable identifier, unique in the file, never reused;
- `state`: `open`, or `closed` (`done`, `resolved`, `cancelled` and
  `canceled` count as closed); absent or empty means `open`; any other value,
  or a value that is not a string, makes the whole register
  `ERROR / INVALID_REGISTER` rather than an open item
  (`PV-AUDIT-REGISTER-STATE-001`);
- `due`: `YYYY-MM-DD` or RFC 3339, optional. Without it the target is
  `DECLARED`; with a date within 28 days `VISIBLE`; beyond, `EXTENDED`.

A change request is **linked** to a target when its title or body contains
the marker followed by the target id, for example a line `Target: T-3`. The
marker is a token of its own, matched exactly, case included: it starts the
text or follows a character that cannot continue a word, so `SubTarget: T-3`,
`NotTarget: T-3` and `PreTarget:T-3` link nothing
(`PV-AUDIT-TARGET-MARKER-SYNTAX-001`); a marker that ends in a letter or digit
also needs a boundary after it. Several markers link to several targets, in
order, each once.

Linkage is state-neutral: a closed target is still the target the work was
declared against, so a change request that references it stays linked
(`PV-REV-DIRECTION-CLOSED-TARGET-001`). Keep closed targets in the file for as
long as recent work references them. A reference to an id the register does
not contain is a broken reference: the change request counts as unlinked,
`planning.linkage.missing_target_reference_count_28d` reports it, and
Direction carries `DIRECTION_TARGET_REFERENCE_MISSING`. When the register
itself cannot be read, nothing about the id is known, so the change request is
unresolved rather than unlinked (`PV-DIRECTION-INCOMPLETE-001`).

A missing file is `UNAVAILABLE / REGISTER_NOT_FOUND` and makes Horizon and
Direction `UNKNOWN` (the mechanism is configured but absent). An invalid file
is `ERROR / INVALID_REGISTER`. An empty `targets` list is a positive
`SUPPORTED_UNUSED`, so Horizon and Direction become `UNDECLARED`.

## Debt register (debt.source = file)

Configuration: `"debt": {"source": "file", "path": "devostasis/debt.json", "mapping_version": "2026-09"}`.

```json
{
  "schema": "devostasis.debt.v1",
  "items": [
    {"id": "D-1", "title": "Replace the legacy parser", "state": "open", "opened": "2026-06-01", "updated": "2026-07-01"},
    {"id": "D-2", "title": "Remove dead flags", "state": "closed", "opened": "2026-08-01", "closed": "2026-08-20"}
  ]
}
```

- `opened`, `updated`, `closed`: `YYYY-MM-DD` or RFC 3339; `updated` defaults
  to `opened`; one of them is required;
- an open item not updated for 30 days is stale; an item closed within 28
  days counts in `closed_count_28d`.

The register is the debt register itself, so `debt.registry.capability` is
`CONFIGURED`, `PRESENT` when any item is open and `CLEAR` when none is.
Changing `path` or `mapping_version` makes history `INCOMPARABLE` once.

## Label mapping (debt.source = labels)

The alternative that needs no file: `"debt": {"source": "labels", "labels": ["type:debt"], "mapping_version": "1"}`.
Open issues carrying any listed label are the debt items.

## Why not ROADMAP.md

The accepted contracts forbid deriving planning or debt meaning from prose:
a Markdown roadmap cannot be parsed without heuristics, and heuristics are
exactly the kind of inference that drifts from run to run. The registers are
deliberately small so a roadmap author can maintain both, or generate the
register from the roadmap with a script the project owns.
