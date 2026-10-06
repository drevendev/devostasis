"""Append-only filesystem HistoryStore.

Layout (PV-REPORT-001 companion-store recommendation)::

    projects/README.md                 fleet overview for people
    projects/index.json                fleet index for machines
    projects/<forge>/<owner>/<repo>/
      latest/            convenience copy of the newest bundle, never authoritative
      history/YYYY/MM/DD/<bundle_id>/   immutable bundles
      index.json         chronological index of bundles

The store root is meant to be a companion Git repository committed by the
scheduler, or a plain directory in local mode. Storage activity never enters
the telemetry of the observed project because the store is never a target.

**A project is identified by its immutable project id, not by its path**
(RPT-7). The directory keeps the human-readable ``<forge>/<owner>/<repo>``
locator because a store is browsed by people, but a project is located by the
provider's immutable id first. When a repository is renamed or transferred,
the directory is relocated once to the new locator and the rename is recorded
in the project index, so history stays one chain instead of silently splitting
into an old orphan and a new BASELINE.

Fail-closed rules:

* if the locator a project now claims is already occupied by a different
  project, nothing is written. That is the case of a repository being renamed
  and its old name immediately reused, which would otherwise merge two
  projects' histories into one directory;
* a locator derives a store path only when it is a ``<forge>/<owner>/<repo>``
  triple of plain name characters, strictly beneath ``projects/``; a component
  pathlib would read as a parent reference, a drive or an absolute path is
  refused rather than normalized away (PV-AUDIT-STORE-PATH-001);
* the index tail is followed only when it names the canonical history path of
  the bundle id it claims, inside this project's ``history/`` tree, and the
  bundle found there must belong to this project: a tail that points elsewhere
  is a store inconsistency, never a comparison against another project's
  history (review of issue #28's repair);
* an unreadable or malformed per-project index is an explicit store failure
  wherever it is met: when proving that an immutable id lives nowhere else
  (PV-AUDIT-HISTORYSTORE-001) and when the fleet surfaces are generated
  (PV-AUDIT-FLEET-INDEX-001), corruption is uncertainty, not absence;
* the index is replaced, never truncated in place, and the previous
  convenience copy is kept until the new one is in place
  (PV-AUDIT-HISTORYSTORE-ATOMIC-PUBLICATION-001).
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import canonical
from .bundle import Bundle, load_bundle_dir, verify_members

INDEX_SCHEMA = "devostasis.index.v1"
BUNDLE_ID = re.compile(r"[0-9a-f]{64}")
LOCATOR_PART = re.compile(r"[A-Za-z0-9._-]+")

INDEX_TAIL_INVALID = "INDEX_TAIL_INVALID"
PROJECT_IDENTITY_MISMATCH = "PROJECT_IDENTITY_MISMATCH"
BUNDLE_BINDING_MISMATCH = "BUNDLE_BINDING_MISMATCH"
INDEXLESS_CANDIDATE_UNREADABLE = "INDEXLESS_CANDIDATE_UNREADABLE"


class HistoryStoreError(Exception):
    pass


class ImmutabilityError(HistoryStoreError):
    """Raised when an existing immutable bundle would be overwritten with different content."""


class IdentityConflictError(HistoryStoreError):
    """Raised when a locator is claimed by a project that is not the one being written."""


@dataclass
class LatestState:
    """What the store knows about the newest bundle of a project."""

    exists: bool
    verified: bool
    bundle_id: str | None
    manifest: dict[str, Any] | None
    snapshot: dict[str, Any] | None
    problems: list[str]
    # The observation set the bundle was evaluated over, when it keeps one: the
    # replay source of durable revision history for a bundle older than the
    # carrier in its snapshot (PV-HIST-002, HIST-13).
    observations: dict[str, Any] | None = None


@dataclass
class ResolvedLocation:
    """Where a project's history lives, and whether the locator moved since the last bundle."""

    directory: Path
    previous_directory: Path | None = None

    @property
    def relocated(self) -> bool:
        return self.previous_directory is not None and self.previous_directory != self.directory


def index_problems(index: Any) -> list[str]:
    """Shape problems of a per-project index; empty when every entry is one the store could have written."""
    if not isinstance(index, dict):
        return [f"index is not an object but {type(index).__name__}"]
    bundles = index.get("bundles")
    if not isinstance(bundles, list):
        return [f"index bundles is not a list but {type(bundles).__name__}"]
    problems = []
    for position, entry in enumerate(bundles):
        if not isinstance(entry, dict):
            problems.append(f"index entry {position} is not an object but {type(entry).__name__}")
        elif not isinstance(entry.get("bundle_id"), str) or not BUNDLE_ID.fullmatch(entry["bundle_id"]):
            problems.append(f"index entry {position} carries no bundle id")
    return problems


def _write_atomic(path: Path, data: bytes) -> None:
    """Write a complete file beside the target and replace the target in one step.

    A reader sees the previous file or the new one, never a truncated one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


class FilesystemHistoryStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    @property
    def projects_root(self) -> Path:
        return self.root / "projects"

    def _rel(self, path: Path | str | None) -> str:
        """A path as the store names it: relative to its root, in POSIX form.

        Problem texts reach the delta of a HISTORY_GAP bundle, and so its
        identity: an absolute path, or an exception message that differs by
        operating system and Python version, made the same evidence and the
        same damage produce a different bundle id per checkout.
        """
        if path is None:
            return "None"
        try:
            return Path(path).resolve().relative_to(self.root.resolve()).as_posix()
        except (ValueError, OSError):
            return Path(path).name

    def project_dir(self, project_key: str) -> Path:
        """The directory a locator names, strictly beneath ``projects/``. Where a project actually lives is ``resolve``."""
        parts = project_key.split("/")
        if len(parts) != 3 or any(not part or part in (".", "..") or not LOCATOR_PART.fullmatch(part) for part in parts):
            raise HistoryStoreError(f"project key {project_key!r} is not a <forge>/<owner>/<repo> locator; refusing to derive a store path from it")
        directory = self.projects_root.joinpath(*parts)
        if directory.resolve().parent.parent.parent != self.projects_root.resolve():
            raise HistoryStoreError(f"project key {project_key!r} does not resolve beneath projects/; refusing to derive a store path from it")
        return directory

    def index_path(self, project_key: str) -> Path:
        return self.project_dir(project_key) / "index.json"

    # ------------------------------------------------------------------ identity

    def _project_index_paths(self) -> list[Path]:
        """Every per-project index, excluding the fleet index that shares the name."""
        if not self.projects_root.exists():
            return []
        # Exactly three levels down, and files only: rglob also matched a
        # repository named index.json (a valid name) and read its directory
        # as an index, which broke every identity lookup of the store.
        return [path for path in sorted(self.projects_root.glob("*/*/*/index.json")) if path.is_file()]

    @staticmethod
    def _identity_of(index: dict[str, Any] | None) -> str | None:
        identity = (index or {}).get("project_identity") or {}
        if not isinstance(identity, dict):
            return None
        value = identity.get("immutable_project_id")
        return str(value) if value not in (None, "") else None

    def _read_index_at(self, directory: Path) -> dict[str, Any] | None:
        path = directory / "index.json"
        if not path.exists():
            return None
        try:
            index = canonical.load_file(path)
        except Exception as exc:  # noqa: BLE001
            raise HistoryStoreError(f"index unreadable at {self._rel(directory)}: {type(exc).__name__}") from exc
        problems = index_problems(index)
        if problems:
            raise HistoryStoreError(f"index invalid at {self._rel(directory)}: {'; '.join(problems)}")
        return index

    def find_by_identity(self, immutable_project_id: str | None) -> Path | None:
        """The directory whose recorded identity matches, wherever it currently sits.

        An unreadable candidate index makes the lookup fail rather than
        continue: absence of a project elsewhere in the store is proven by
        reading every index, and one that cannot be read may be the project
        being looked for (PV-AUDIT-HISTORYSTORE-001).
        """
        if not immutable_project_id:
            return None
        for index_path in self._project_index_paths():
            try:
                index = self._read_index_at(index_path.parent)
            except HistoryStoreError as exc:
                raise HistoryStoreError(f"{exc}; the identity {immutable_project_id} cannot be proven absent from the store") from exc
            if self._identity_of(index) == str(immutable_project_id) and index.get("bundles"):
                return index_path.parent
        return None

    def resolve(self, project_key: str, immutable_project_id: str | None = None) -> ResolvedLocation:
        """Locate a project by identity, falling back to its locator.

        Without an immutable id the store behaves exactly as before: the
        locator is the identity, and a rename starts a new history. Adapters
        that cannot prove an id therefore lose continuity honestly rather than
        by guessing which directory belonged to whom.
        """
        wanted = self.project_dir(project_key)
        identity = str(immutable_project_id) if immutable_project_id not in (None, "") else None
        if identity is None:
            return ResolvedLocation(wanted)

        at_locator = self._identity_of(self._read_index_at(wanted))
        if at_locator == identity:
            return ResolvedLocation(wanted)
        if at_locator is not None:
            raise IdentityConflictError(
                f"{project_key} is occupied by project {at_locator}, and this run observes project {identity}; "
                "refusing to merge two histories in one directory"
            )

        existing = self.find_by_identity(identity)
        if existing is None or existing == wanted:
            return ResolvedLocation(wanted)
        if wanted.exists() and any(wanted.iterdir()):
            raise IdentityConflictError(
                f"project {identity} moved to {project_key}, but that directory already holds unidentified content; "
                "refusing to write over it"
            )
        return ResolvedLocation(wanted, previous_directory=existing)

    def _relocate(self, location: ResolvedLocation) -> None:
        """Move a renamed or transferred project to its new locator, once."""
        source, target = location.previous_directory, location.directory
        if source is None or source == target:
            return
        if target.exists():
            occupant = self._identity_of(self._read_index_at(target))
            raise IdentityConflictError(
                f"cannot move {source} to {target}: the destination already exists"
                + (f" and holds project {occupant}" if occupant else "")
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)

    # ------------------------------------------------------------------ reading

    def read_index(self, project_key: str, directory: Path | None = None) -> dict[str, Any]:
        directory = directory if directory is not None else self.project_dir(project_key)
        index = self._read_index_at(directory)
        if index is None:
            return {"schema": INDEX_SCHEMA, "project_key": project_key, "bundles": []}
        return index

    @staticmethod
    def _tail_dir(directory: Path, tail: dict[str, Any]) -> tuple[Path | None, str | None]:
        """The immutable directory an index tail names, or why it cannot be followed.

        The store only ever records ``history/YYYY/MM/DD/<bundle_id>``, so
        that is the only shape followed: an absolute path, a parent reference,
        a native separator, a basename that is not the claimed bundle id, or a
        path that resolves outside this project's ``history/`` tree is refused
        before anything is opened.
        """
        bundle_id = tail.get("bundle_id")
        path = tail.get("path")
        if not isinstance(bundle_id, str) or not BUNDLE_ID.fullmatch(bundle_id):
            return None, f"{INDEX_TAIL_INVALID}: index tail bundle_id {bundle_id!r} is not a bundle id"
        if not isinstance(path, str) or not path:
            return None, f"{INDEX_TAIL_INVALID}: index tail names no path for bundle {bundle_id}"
        parts = path.split("/")
        canonical_shape = (
            "\\" not in path
            and len(parts) == 5
            and parts[0] == "history"
            and all(part.isdigit() and 2 <= len(part) <= 4 for part in parts[1:4])
            and parts[4] == bundle_id
        )
        if not canonical_shape:
            return None, f"{INDEX_TAIL_INVALID}: index tail path {path!r} is not the canonical history path of bundle {bundle_id}"
        candidate = directory.joinpath(*parts)
        if candidate.resolve().parent.parent.parent.parent != (directory / "history").resolve():
            return None, f"{INDEX_TAIL_INVALID}: index tail path {path!r} resolves outside {self._rel(directory / 'history')}"
        return candidate, None

    def _newest_immutable(self, directory: Path) -> tuple[Path | None, str | None, list[str]]:
        """The newest immutable bundle directory when no index names one: scanned, ordered like the index.

        Every bundle directory is a candidate, and one whose manifest is
        missing, unreadable or names another bundle is reported, never
        skipped: it may be the newest, so passing over it compared the next
        run against an older bundle, or called a store with history BASELINE.
        Only an interrupted write (``*.staging``) is not a candidate.
        """
        newest: tuple[str, str, Path] | None = None
        problems: list[str] = []
        for candidate in sorted((directory / "history").glob("*/*/*/*")):
            if not candidate.is_dir() or candidate.name.endswith(".staging"):
                continue
            try:
                manifest = canonical.load_file(candidate / "manifest.json")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{INDEXLESS_CANDIDATE_UNREADABLE}: {self._rel(candidate)}: {type(exc).__name__}")
                continue
            if not isinstance(manifest, dict) or candidate.name != manifest.get("bundle_id"):
                problems.append(f"{INDEXLESS_CANDIDATE_UNREADABLE}: {self._rel(candidate)} does not carry the bundle it is named after")
                continue
            key = (str(manifest.get("observed_at") or ""), str(manifest.get("bundle_id") or ""), candidate)
            if newest is None or key[:2] > newest[:2]:
                newest = key
        if newest is None:
            return None, None, problems
        return newest[2], newest[1], problems

    def _identity_problem(self, index: dict[str, Any], project_key: str, immutable_project_id: str | None, manifest: dict[str, Any], bundle_dir: Path | None) -> str | None:
        """Why the loaded bundle is not this project's: the identity the history records, or its locator, disagrees."""
        recorded = self._identity_of(index)
        expected = recorded or (str(immutable_project_id) if immutable_project_id not in (None, "") else None)
        actual = self._identity_of({"project_identity": manifest.get("project_identity")})
        if expected is not None:
            if actual != expected:
                return f"{PROJECT_IDENTITY_MISMATCH}: immutable bundle at {self._rel(bundle_dir)} belongs to project {actual}, this history is project {expected}"
            return None
        expected_key = index.get("project_key") or project_key
        if manifest.get("project_key") != expected_key:
            return f"{PROJECT_IDENTITY_MISMATCH}: immutable bundle at {self._rel(bundle_dir)} was written for {manifest.get('project_key')!r}, this history is {expected_key!r}"
        return None

    def latest(self, project_key: str, immutable_project_id: str | None = None) -> LatestState:
        """The newest bundle of a project, read from where the contract says it lives.

        The authority is the immutable bundle the project index names (its
        tail), verified from its own contents. ``latest/`` is a convenience
        copy: it is never the source of the comparison, it is republished on
        every commit, and it may be compacted away. It is still checked when
        present, because a copy that names a different bundle than the index
        is a store inconsistency worth refusing to compare across (#12
        finding 6), and that check keeps its problem text.

        The tail is followed only along the canonical history path of the
        bundle it names, and the bundle found there must carry this project's
        identity: a damaged index that points at another project's bundle
        yields an unverified state, never a comparison against it.
        """
        try:
            location = self.resolve(project_key, immutable_project_id)
        except HistoryStoreError as exc:
            return LatestState(True, False, None, None, None, [str(exc)])
        directory = location.previous_directory or location.directory
        latest_dir = directory / "latest"
        try:
            index = self.read_index(project_key, directory)
        except HistoryStoreError as exc:
            return LatestState(True, False, None, None, None, [str(exc)])

        problems: list[str] = []
        bundle_dir: Path | None = None
        expected_id: str | None = None
        if index["bundles"]:
            tail = index["bundles"][-1]
            expected_id = tail.get("bundle_id")
            bundle_dir, problem = self._tail_dir(directory, tail)
            if problem is not None:
                problems.append(problem)
            elif not bundle_dir.exists():
                problems.append(f"immutable bundle {expected_id} named by the index tail is missing at {tail.get('path')}")
                bundle_dir = None
        else:
            bundle_dir, expected_id, scan_problems = self._newest_immutable(directory)
            if scan_problems:
                # History exists but its order cannot be proven: a gap, not a
                # comparison against whichever bundle happened to be readable.
                return LatestState(True, False, None, None, None, scan_problems)
            if bundle_dir is None:
                if not latest_dir.exists():
                    return LatestState(False, False, None, None, None, [])
                problems.append("a latest copy exists but no immutable bundle and no index name it")

        members = load_bundle_dir(bundle_dir) if bundle_dir is not None else {}
        if not members:
            if not problems:
                problems.append(f"immutable bundle directory {self._rel(bundle_dir)} is empty")
            return LatestState(True, False, expected_id, None, None, problems)
        problems.extend(verify_members(members))
        try:
            manifest = canonical.loads(members["manifest.json"].decode("utf-8"))
            snapshot = canonical.loads(members["snapshot.json"].decode("utf-8")) if "snapshot.json" in members else None
            observations = canonical.loads(members["observations.json"].decode("utf-8")) if "observations.json" in members else None
        except Exception as exc:  # noqa: BLE001
            return LatestState(True, False, expected_id, None, None, problems + [f"immutable bundle unreadable: {type(exc).__name__}"])
        if not isinstance(manifest, dict):
            return LatestState(True, False, expected_id, None, None, problems + ["immutable bundle manifest is not an object"])
        if expected_id and manifest.get("bundle_id") != expected_id:
            problems.append(f"immutable bundle at {self._rel(bundle_dir)} carries {manifest.get('bundle_id')}, the index names {expected_id}")
        identity_problem = self._identity_problem(index, project_key, immutable_project_id, manifest, bundle_dir)
        if identity_problem is not None:
            problems.append(identity_problem)

        if latest_dir.exists():
            copy = load_bundle_dir(latest_dir)
            try:
                copied_id = canonical.loads(copy["manifest.json"].decode("utf-8")).get("bundle_id") if "manifest.json" in copy else None
            except Exception:  # noqa: BLE001
                copied_id = None
            if copied_id is not None and copied_id != manifest.get("bundle_id") and not self._is_stale_copy(index, copied_id, manifest):
                problems.append(f"latest pointer {copied_id} differs from index tail {manifest.get('bundle_id')}")
        return LatestState(True, not problems, manifest.get("bundle_id"), manifest, snapshot, problems, observations if isinstance(observations, dict) else None)

    @staticmethod
    def _is_stale_copy(index: dict[str, Any], copied_id: str, tail_manifest: dict[str, Any]) -> bool:
        """A convenience copy of an indexed bundle not newer than the tail is an interrupted republication, not an inconsistency.

        The index is written before the copy is refreshed, so a failure between
        the two leaves the previous copy in place; the next commit replaces it.
        A copy naming a bundle the index does not know, or one observed after
        the tail, is still a store inconsistency and is refused.
        """
        for entry in index.get("bundles") or []:
            if entry.get("bundle_id") == copied_id:
                return str(entry.get("observed_at") or "") <= str(tail_manifest.get("observed_at") or "")
        return False

    # ------------------------------------------------------------------ writing

    def bundle_identity(self, bundle: Bundle) -> str | None:
        return self._identity_of({"project_identity": bundle.manifest.get("project_identity")})

    @staticmethod
    def _binding_problems(bundle: Bundle) -> list[str]:
        """The wrapper must name the bundle its canonical members name, or nothing is routed by it."""
        problems: list[str] = []
        try:
            manifest = canonical.loads(bundle.members["manifest.json"].decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return [f"{BUNDLE_BINDING_MISMATCH}: manifest.json unreadable: {exc}"]
        if not isinstance(manifest, dict):
            return [f"{BUNDLE_BINDING_MISMATCH}: manifest.json is not an object"]
        if manifest.get("bundle_id") != bundle.bundle_id or bundle.manifest.get("bundle_id") != bundle.bundle_id:
            problems.append(f"{BUNDLE_BINDING_MISMATCH}: wrapper names bundle {bundle.bundle_id}, the manifest names {manifest.get('bundle_id')}")
        if manifest.get("project_key") != bundle.project_key:
            problems.append(f"{BUNDLE_BINDING_MISMATCH}: wrapper routes to {bundle.project_key!r}, the manifest was written for {manifest.get('project_key')!r}")
        if not BUNDLE_ID.fullmatch(str(bundle.bundle_id)):
            problems.append(f"{BUNDLE_BINDING_MISMATCH}: {bundle.bundle_id!r} is not a bundle id")
        return problems

    def history_dir(self, bundle: Bundle, directory: Path | None = None) -> Path:
        day = bundle.observed_at[:10].split("-")
        directory = directory if directory is not None else self.project_dir(bundle.project_key)
        return directory.joinpath("history", *day, bundle.bundle_id)

    def put_immutable(self, bundle: Bundle, directory: Path | None = None) -> Path:
        problems = self._binding_problems(bundle)
        if problems:
            raise HistoryStoreError("; ".join(problems))
        target = self.history_dir(bundle, directory)
        if target.exists():
            existing = load_bundle_dir(target)
            if existing == bundle.members:
                return target
            raise ImmutabilityError(f"bundle {bundle.bundle_id} already exists with different content; history is append-only")
        staging = target.with_name(target.name + ".staging")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for name, data in bundle.members.items():
            (staging / name).write_bytes(data)
        staging.rename(target)
        return target

    def publish_latest(self, bundle: Bundle, directory: Path | None = None) -> Path:
        """Republish the convenience copy: the previous copy stays until the new one is in place."""
        directory = directory if directory is not None else self.project_dir(bundle.project_key)
        latest_dir = directory / "latest"
        staging = latest_dir.with_name("latest.staging")
        retired = latest_dir.with_name("latest.retired")
        for leftover in (staging, retired):
            if leftover.exists():
                shutil.rmtree(leftover)
        staging.mkdir(parents=True)
        for name, data in bundle.members.items():
            (staging / name).write_bytes(data)
        if latest_dir.exists():
            latest_dir.rename(retired)
        staging.rename(latest_dir)
        if retired.exists():
            shutil.rmtree(retired)
        return latest_dir

    def update_index(
        self,
        bundle: Bundle,
        bands: dict[str, str | None],
        gauges: dict[str, int | None] | None = None,
        top_attention: str | None = None,
        directory: Path | None = None,
        renamed_from: str | None = None,
    ) -> dict[str, Any]:
        directory = directory if directory is not None else self.project_dir(bundle.project_key)
        index = self.read_index(bundle.project_key, directory)
        entries = [entry for entry in index["bundles"] if entry.get("bundle_id") != bundle.bundle_id]
        relative = self.history_dir(bundle, directory).relative_to(directory).as_posix()
        entries.append(
            {
                "bundle_id": bundle.bundle_id,
                "observed_at": bundle.observed_at,
                "comparison_status": bundle.manifest["comparison_status"],
                "previous_bundle_id": bundle.manifest.get("previous_bundle_id"),
                "path": relative,
                "bands": dict(sorted(bands.items())),
                "gauges": dict(sorted((gauges or {}).items())),
                "top_attention": top_attention,
            }
        )
        entries.sort(key=lambda entry: (entry["observed_at"], entry["bundle_id"]))
        index["schema"] = index.get("schema", INDEX_SCHEMA)
        index["bundles"] = entries
        index["project_key"] = bundle.project_key
        index["project_identity"] = bundle.manifest["project_identity"]
        if renamed_from:
            renames = [entry for entry in (index.get("renames") or []) if entry.get("to") != bundle.project_key or entry.get("from") != renamed_from]
            renames.append(
                {
                    "from": renamed_from,
                    "to": bundle.project_key,
                    "observed_at": bundle.observed_at,
                    "bundle_id": bundle.bundle_id,
                }
            )
            index["renames"] = sorted(renames, key=lambda entry: (entry["observed_at"], entry["bundle_id"]))
        _write_atomic(directory / "index.json", canonical.pretty_json(index).encode("utf-8"))
        return index

    def commit(
        self,
        bundle: Bundle,
        bands: dict[str, str | None] | None = None,
        gauges: dict[str, int | None] | None = None,
        top_attention: str | None = None,
    ) -> Path:
        """Relocate on rename, persist immutably, then the index, then the convenience copy.

        The index is the authority and is written first; the copy is refreshed
        last, so an interruption between the two leaves a stale copy of an
        indexed bundle, which the next commit replaces, and never an index
        that names a bundle the copy contradicts.
        """
        from .demand import top_attention as _top

        problems = self._binding_problems(bundle)
        if problems:
            raise HistoryStoreError("; ".join(problems))
        location = self.resolve(bundle.project_key, self.bundle_identity(bundle))
        renamed_from = None
        if location.relocated:
            renamed_from = location.previous_directory.relative_to(self.projects_root).as_posix()
            self._relocate(location)
        directory = location.directory
        path = self.put_immutable(bundle, directory)
        bands = bands if bands is not None else bundle.bands()
        gauges = gauges if gauges is not None else bundle.gauges()
        if top_attention is None:
            try:
                top_attention = _top(bundle.demand())
            except KeyError:
                top_attention = None
        self.update_index(bundle, bands, gauges, top_attention, directory, renamed_from)
        self.publish_latest(bundle, directory)
        return path

    # ------------------------------------------------------------------ fleet

    def all_projects(self) -> list[dict[str, Any]]:
        """Latest index entry of every project in the store, for the fleet overview and index.

        Fails closed: an unreadable or malformed project index, a tail that
        cannot be followed, or a demand member that is present but unreadable
        stops the enumeration with a ``HistoryStoreError`` instead of dropping
        the project from a fleet surface that would then look complete
        (PV-AUDIT-FLEET-INDEX-001, PV-AUDIT-FLEET-COVERAGE-001).
        """
        entries = []
        projects_root = self.projects_root
        if not projects_root.exists():
            return entries
        for index_path in self._project_index_paths():
            project_dir = index_path.parent
            index = self._read_index_at(project_dir)
            if not index["bundles"]:
                continue
            tail = index["bundles"][-1]
            bundle_dir, problem = self._tail_dir(project_dir, tail)
            if problem is not None:
                raise HistoryStoreError(f"{self._rel(project_dir)}: {problem}")
            identity = index.get("project_identity") or {}
            if not isinstance(identity, dict):
                raise HistoryStoreError(f"{self._rel(project_dir)}: index project_identity is not an object")
            entries.append(
                {
                    "project_key": index.get("project_key"),
                    "locator": identity.get("display_locator") or index.get("project_key"),
                    "immutable_project_id": identity.get("immutable_project_id"),
                    "observed_at": tail.get("observed_at"),
                    "bundle_id": tail.get("bundle_id"),
                    "previous_bundle_id": tail.get("previous_bundle_id"),
                    "comparison_status": tail.get("comparison_status"),
                    "bands": tail.get("bands") or {},
                    "gauges": tail.get("gauges") or {},
                    "top_attention": tail.get("top_attention"),
                    "demand_rows": self._demand_rows(bundle_dir),
                    "attention_order": self._attention_order(bundle_dir),
                    "report_path": self._report_path(project_dir, bundle_dir, projects_root),
                    "bundle_path": bundle_dir.relative_to(projects_root).as_posix(),
                }
            )
        return entries

    @staticmethod
    def _report_path(project_dir: Path, bundle_dir: Path, projects_root: Path) -> str | None:
        """The report of the newest bundle: the convenience copy when it exists, the immutable one otherwise."""
        for candidate in (project_dir / "latest" / "report.md", bundle_dir / "report.md"):
            if candidate.exists():
                return candidate.relative_to(projects_root).as_posix()
        return None

    def _latest_demand(self, bundle_dir: Path) -> dict[str, Any] | None:
        """The demand member of the newest bundle, or None when the bundle predates the demand interface.

        Bundles written before the demand interface existed have no such
        member; their rows carry null levels rather than invented ones. A
        member that is present but cannot be read is not such a bundle, and
        is a store failure rather than a null row.
        """
        path = bundle_dir / "demand.json"
        if not path.exists():
            return None
        try:
            document = canonical.load_file(path)
        except Exception as exc:  # noqa: BLE001
            raise HistoryStoreError(f"demand member unreadable at {self._rel(path)}: {type(exc).__name__}") from exc
        if not isinstance(document, dict):
            raise HistoryStoreError(f"demand member at {self._rel(path)} is not an object")
        return document

    def _demand_rows(self, bundle_dir: Path) -> list[dict[str, Any]]:
        demand = self._latest_demand(bundle_dir)
        rows = (demand or {}).get("vitals")
        return [row for row in rows if isinstance(row, dict) and row.get("vital_id")] if isinstance(rows, list) else []

    def _attention_order(self, bundle_dir: Path) -> list[dict[str, Any]]:
        demand = self._latest_demand(bundle_dir)
        order = (demand or {}).get("attention_order")
        if not isinstance(order, list):
            return []
        return [
            {"vital_id": item["vital_id"], "level": item.get("level")}
            for item in order
            if isinstance(item, dict) and item.get("vital_id")
        ]
