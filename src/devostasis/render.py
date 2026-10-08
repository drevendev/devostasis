"""Deterministic Markdown renderer (``devostasis.render.v4``).

The renderer is a pure function of the canonical bundle plus the persisted
display configuration: it adds no health semantics, no aggregate score, no
evaluative aliases. Neutral bands such as Direction FULLY_LINKED and Debt
PRESENT stay neutral. Version 3 honours ``display`` (which Vitals, which gauge
components, which sections) and renders the demand interface; version 4
states the demand.v2 ordering (level, then canonical Vital order; gauges are
never compared across Vitals) and renders exact rational durations.
"""

from __future__ import annotations

from typing import Any

from . import gauges as gauges_mod
from .canonical import ratio_text, rational_parts
from .contracts import CORE_VITAL_IDS

VITAL_TITLES = {
    "horizon": "Horizon",
    "clutter": "Clutter",
    "direction": "Direction",
    "flow": "Flow",
    "integrity": "Integrity",
    "debt": "Debt",
    "pulse": "Pulse",
}

VITAL_QUESTIONS = {
    "horizon": "Is future work explicitly declared, and does any declaration reach beyond 28 days?",
    "clutter": "How much unresolved stale residue is observable?",
    "direction": "Is active change work explicitly traceable to declared targets?",
    "flow": "What is the state and friction of the current change-request queue?",
    "integrity": "What does automated verification say about recent immutable revisions?",
    "debt": "How much explicitly registered maintenance obligation is unresolved?",
    "pulse": "How intense is recent observable activity?",
}

DEFAULT_DISPLAY = {"vitals": list(CORE_VITAL_IDS), "gauge": ["bar", "number", "band"], "sections": ["demand", "details", "observability", "changes", "activity", "provenance"]}


def _display(display: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_DISPLAY)
    if display:
        for key in ("vitals", "gauge", "sections"):
            if display.get(key) is not None:
                merged[key] = list(display[key])
    return merged


def _band(vital: dict[str, Any]) -> str:
    return vital.get("band") or "UNKNOWN"


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "true" if value else "false"
    parts = rational_parts(value)
    if parts is not None:
        return f"{ratio_text(value)} ({parts[0]}/{parts[1]})"
    if isinstance(value, dict):
        return ", ".join(f"{k}={_fmt(v)}" for k, v in sorted(value.items())) or "none"
    if isinstance(value, list):
        return ", ".join(_fmt(v) for v in value) or "none"
    return str(value)


def _metric_rows(derived: dict[str, Any]) -> list[str]:
    rows = []
    for key in sorted(derived):
        value = derived[key]
        if isinstance(value, dict) and rational_parts(value) is None:
            continue
        rows.append(f"| {key} | {_fmt(value)} |")
    return rows


def _gauge_map(snapshot: dict[str, Any], gauges_doc: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    items = gauges_doc["gauges"] if gauges_doc else gauges_mod.gauges_for_snapshot(snapshot)
    return {g["vital_id"]: g for g in items}


def render_status_card(snapshot: dict[str, Any], display: dict[str, Any] | None = None, gauges_doc: dict[str, Any] | None = None) -> str:
    """Monospace status card honouring the display configuration."""
    options = _display(display)
    gauges = _gauge_map(snapshot, gauges_doc)
    vitals = {v["vital_id"]: v for v in snapshot["vitals"]}
    modes = options["gauge"]
    lines = []
    for vital_id in options["vitals"]:
        gauge = gauges[vital_id]
        vital = vitals[vital_id]
        parts = [f"{VITAL_TITLES[vital_id]:<10}"]
        if "bar" in modes:
            parts.append(gauges_mod.bar(gauge["value"]))
        if "number" in modes:
            parts.append(f"{gauges_mod.value_text(gauge):>4}")
        if "band" in modes:
            parts.append(_band(vital))
        if vital["evaluation_status"] != "AVAILABLE":
            parts.append(f"[{vital['evaluation_status']}]")
        lines.append("  ".join(parts).rstrip())
    return "\n".join(lines)


def render_report(
    manifest: dict[str, Any],
    snapshot: dict[str, Any],
    delta: dict[str, Any],
    activity: dict[str, Any] | None,
    gauges_doc: dict[str, Any] | None = None,
    demand_doc: dict[str, Any] | None = None,
    display: dict[str, Any] | None = None,
) -> str:
    options = _display(display)
    sections = set(options["sections"])
    shown = [v for v in snapshot["vitals"] if v["vital_id"] in options["vitals"]]
    shown.sort(key=lambda v: options["vitals"].index(v["vital_id"]))
    gauges = _gauge_map(snapshot, gauges_doc)
    show_gauge = "number" in options["gauge"] or "bar" in options["gauge"]
    identity = manifest["project_identity"]
    lines: list[str] = []
    lines.append(f"# Devostasis report: {identity['display_locator']}")
    lines.append("")
    lines.append(f"- Observed at: {manifest['observed_at']}")
    lines.append(f"- Comparison: {manifest['comparison_status']}" + (f" (previous bundle `{manifest['previous_bundle_id']}`)" if manifest.get("previous_bundle_id") else ""))
    lines.append(f"- Bundle: `{manifest['bundle_id']}`")
    lines.append(f"- Contracts: vitals {manifest['vitals_contract_version']}, observations {manifest['observation_contract_version']}, policy {manifest['policy_version']}")
    lines.append("")
    lines.append("```text")
    lines.append(render_status_card(snapshot, options, gauges_doc))
    lines.append("```")
    lines.append("")
    lines.append(
        "Bands are the canonical states. Gauges are the versioned 0-100 normalization "
        f"({gauges_mod.GAUGE_CONTRACT}) of each band on the scale of the phenomenon it describes "
        "(activity, queue pressure, verification stability, residue, declared future work, traceability share, registered debt). "
        "UNKNOWN means evidence was insufficient; DEGRADED means a conservative bound, shown as ≥ or ~."
    )
    lines.append("")

    if "demand" in sections and demand_doc:
        lines.append("## Attention")
        lines.append("")
        lines.append(f"Demand levels come from mapping `{demand_doc.get('mapping_version')}` ({demand_doc.get('contract')}); inside a level the canonical Vital order applies and gauges are never compared across Vitals. There is no aggregate.")
        lines.append("")
        lines.append("| Order | Vital | Level | Band | Gauge |")
        lines.append("| --- | --- | --- | --- | --- |")
        rows = {r["vital_id"]: r for r in demand_doc.get("vitals", [])}
        position = 0
        for entry in demand_doc.get("attention_order", []):
            if entry["vital_id"] not in options["vitals"]:
                continue
            position += 1
            row = rows.get(entry["vital_id"], {})
            gauge = gauges.get(entry["vital_id"], {})
            lines.append(f"| {position} | {VITAL_TITLES[entry['vital_id']]} | {entry['level']} | {row.get('band') or 'UNKNOWN'} | {gauges_mod.value_text(gauge) if gauge else 'n/a'} |")
        lines.append("")

    lines.append("## Vitals")
    lines.append("")
    header = "| Vital | " + ("Gauge | " if show_gauge else "") + "Band | Evaluation | Semantics | Explanation |"
    lines.append(header)
    lines.append("| --- | " + ("--- | " if show_gauge else "") + "--- | --- | --- | --- |")
    for vital in shown:
        gauge = gauges[vital["vital_id"]]
        cells = [VITAL_TITLES[vital["vital_id"]]]
        if show_gauge:
            cells.append(gauges_mod.value_text(gauge))
        cells.extend([_band(vital), vital["evaluation_status"], vital.get("band_semantics") or "n/a", vital.get("explanation", "")])
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    if "details" in sections:
        for vital in shown:
            gauge = gauges[vital["vital_id"]]
            lines.append(f"### {VITAL_TITLES[vital['vital_id']]}: {_band(vital)}")
            lines.append("")
            lines.append(f"_{VITAL_QUESTIONS[vital['vital_id']]}_")
            lines.append("")
            lines.append(f"- Evaluation: {vital['evaluation_status']}; rule `{vital['rule_id']}`")
            if show_gauge:
                lines.append(f"- Gauge ({gauge['scale']}): {gauges_mod.bar(gauge['value'])} {gauges_mod.value_text(gauge)}")
            if vital.get("possible_bands"):
                lines.append(f"- Possible bands (conservative superset): {', '.join(vital['possible_bands'])}")
            if vital.get("dependency_group_ids"):
                lines.append(f"- Shares signals with: {', '.join(vital['dependency_group_ids'])}")
            metric_rows = _metric_rows(vital.get("derived") or {})
            if metric_rows:
                lines.append("")
                lines.append("| Metric | Value |")
                lines.append("| --- | --- |")
                lines.extend(metric_rows)
            if vital.get("diagnostics"):
                lines.append("")
                lines.append("Diagnostics:")
                for code in vital["diagnostics"]:
                    lines.append(f"- `{code}`")
            lines.append("")

    if "observability" in sections:
        lines.append("## Observability")
        lines.append("")
        receipt = manifest.get("receipt_identity") or manifest.get("receipt") or {}
        non_available = [
            (key, meta) for key, meta in sorted((receipt.get("per_key") or {}).items())
            if meta.get("status") != "AVAILABLE" or meta.get("freshness") != "FRESH"
        ]
        if non_available:
            lines.append("| Observation | Status | Freshness |")
            lines.append("| --- | --- | --- |")
            for key, meta in non_available:
                lines.append(f"| {key} | {meta.get('status')} | {meta.get('freshness')} |")
        else:
            lines.append("Every requested observation was available and fresh.")
        if receipt.get("capability_notes"):
            lines.append("")
            lines.append("Capability notes:")
            for note in receipt["capability_notes"]:
                lines.append(f"- `{note}`")
        lines.append("")

    if "changes" in sections:
        lines.append("## Changes since previous bundle")
        lines.append("")
        status = delta["comparison_status"]
        if status == "BASELINE":
            lines.append("This is the first canonical bundle for the project: there is no previous state to compare against.")
        elif status == "HISTORY_GAP":
            lines.append("History exists but the previous bundle could not be loaded or verified. No change is inferred.")
        elif status == "INCOMPARABLE":
            lines.append("The previous bundle was produced under different semantics: " + "; ".join(delta.get("incomparable_reasons") or []) + ". No change is inferred.")
        else:
            lines.append(f"Compared with the bundle observed at {delta.get('previous_observed_at')}.")
            lines.append("")
            lines.append("| Vital | Previous | Current | Transition | Reasons |")
            lines.append("| --- | --- | --- | --- | --- |")
            for row in delta["vitals"]:
                if row["vital_id"] not in options["vitals"]:
                    continue
                lines.append(
                    f"| {VITAL_TITLES[row['vital_id']]} | {row.get('previous_band') or 'UNKNOWN'} | {row.get('current_band') or 'UNKNOWN'} | {row['transition_class']} | {', '.join(row.get('reason_codes') or []) or 'none'} |"
                )
            metric_lines = []
            for row in delta["vitals"]:
                if row["vital_id"] not in options["vitals"]:
                    continue
                for key, entry in sorted((row.get("metric_deltas") or {}).items()):
                    change = entry.get("change")
                    change_text = f" ({'+' if isinstance(change, int) and change > 0 else ''}{change})" if isinstance(change, int) else ""
                    metric_lines.append(f"- {VITAL_TITLES[row['vital_id']]} {key}: {_fmt(entry.get('previous'))} to {_fmt(entry.get('current'))}{change_text}")
            if metric_lines:
                lines.append("")
                lines.append("Metric changes:")
                lines.extend(metric_lines)
        lines.append("")

    if "activity" in sections:
        lines.append("## Activity")
        lines.append("")
        if activity is None:
            lines.append("Activity collection is disabled for this project.")
        else:
            interval = activity["interval"]
            basis = "since the previous bundle" if interval["basis"] == "PREVIOUS_BUNDLE" else "over the trailing 28-day observation window (no previous bundle)"
            lines.append(f"Interval {basis}: ({interval['start']}, {interval['end']}].")
            classes = activity["classes"]
            lines.append("")
            lines.append("| Class | Counts |")
            lines.append("| --- | --- |")
            lines.append(f"| Revisions on default branch | {classes['REVISION']['count']} |")
            cr = classes["CHANGE_REQUEST"]
            lines.append(f"| Change requests | opened {cr['opened']}, merged {cr['merged']}, closed {cr['closed']} |")
            wi = classes["WORK_ITEM"]
            lines.append(f"| Work items | opened {wi['opened']}, closed {wi['closed']} |")
            ver = classes["VERIFICATION"]
            lines.append(f"| Verification | {ver['revisions_verified']} revisions verified, {ver['failed']} with an observed failure, {ver['unresolved']} unresolved |")
            lines.append(f"| Releases | {classes['RELEASE']['count']} |")
            lines.append(f"| Capability changes | {classes['CAPABILITY_CHANGE']['count']} |")
            for label, key, formatter in (
                ("Change requests", "CHANGE_REQUEST", lambda e: f"- {e['kind']} #{e['number']} {e.get('title') or ''} ({e['at']})"),
                ("Work items", "WORK_ITEM", lambda e: f"- {e['kind']} #{e['number']} {e.get('title') or ''} ({e['at']})"),
                ("Verification findings", "VERIFICATION", lambda e: f"- {e['revision'][:12]} current {e.get('current_verdict')}, history {e.get('history_state')} ({e['committed_at']})"),
                ("Releases", "RELEASE", lambda e: f"- {e.get('tag')} {e.get('name') or ''} ({e.get('published_at')})"),
                ("Capability changes", "CAPABILITY_CHANGE", lambda e: f"- {e['observation_id']}: {_fmt(e.get('previous'))} to {_fmt(e.get('current'))}"),
            ):
                items = classes[key]["items"]
                if items:
                    lines.append("")
                    lines.append(f"{label}:")
                    for item in items:
                        lines.append(formatter(item))
                    if activity["truncated"].get(key):
                        lines.append(f"- list truncated to {activity['list_cap']} items")
            if activity.get("coverage_notes"):
                lines.append("")
                lines.append("Coverage notes: " + "; ".join(activity["coverage_notes"]))
        lines.append("")

    if "provenance" in sections:
        lines.append("## Provenance")
        lines.append("")
        lines.append(f"- Artifact contract: {manifest['artifact_contract_version']}; bundle identity: {manifest['bundle_identity_contract']}; renderer: {manifest['renderer_version']}; gauges: {gauges_mod.GAUGE_CONTRACT}; demand: {manifest.get('demand_contract', 'n/a')}")
        lines.append(f"- Effective config digest: `{manifest['effective_config_digest']}` (config version `{manifest['config_version']}`)")
        lines.append(f"- Adapters: {', '.join(a['provider'] + ' ' + a['adapter_version'] for a in manifest.get('adapters', []))}")
        lines.append(f"- Observations digest: `{snapshot['observations_digest']}`")
        lines.append("- Generated deterministically from the machine bundle without any language model.")
        lines.append("")
    return "\n".join(lines)


def _cell(bands: dict[str, Any], gauges: dict[str, Any], vital_id: str) -> str:
    band = bands.get(vital_id) or "UNKNOWN"
    value = gauges.get(vital_id) if isinstance(gauges, dict) else None
    if value is None:
        return band
    return f"{band} {value}"


def render_fleet_index(entries: list[dict[str, Any]]) -> str:
    """Convenience overview of the latest bands of every project in a store (non-canonical)."""
    lines = [
        "# Devostasis fleet overview",
        "",
        "Latest canonical bundle per project. Bands are descriptive, not grades; UNKNOWN is honest, not empty. "
        f"The number after a band is the gauge ({gauges_mod.GAUGE_CONTRACT}), 0-100 on the scale of the phenomenon the Vital describes. "
        "Attention is the first entry of the project's demand order; it is not a score.",
        "",
    ]
    lines.append("| Project | Observed at | Comparison | Attention | Pulse | Flow | Integrity | Clutter | Horizon | Direction | Debt | Report |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for entry in sorted(entries, key=lambda e: e["locator"]):
        bands = entry["bands"]
        gauges = entry.get("gauges") or {}
        cells = [_cell(bands, gauges, v) for v in ("pulse", "flow", "integrity", "clutter", "horizon", "direction", "debt")]
        lines.append(
            f"| {entry['locator']} | {entry['observed_at']} | {entry['comparison_status']} | {entry.get('top_attention') or 'n/a'} | " + " | ".join(cells) + f" | [report]({entry['report_path']}) |"
        )
    lines.append("")
    return "\n".join(lines)
