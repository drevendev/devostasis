"""Bounded local Git object reads. Never checkout, execute source or use a forge."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

from ..canonical import digest
from ..workscope.model import instant, path, require, timestamp


def local_environment():
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
               "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
               "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "LANG", "LC_ALL", "LC_CTYPE"}
    return {**{k: v for k, v in os.environ.items() if k.upper() in allowed},
            "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}


def object_digest(data, object_format, kind="blob"):
    algorithm = hashlib.sha1 if object_format == "sha1" else hashlib.sha256
    return algorithm(kind.encode("ascii") + b" " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def blob_digest(data, object_format):
    return object_digest(data, object_format)


class Git:
    def __init__(self, directory, seconds=120):
        self.directory = Path(directory).resolve()
        require(self.directory.is_dir(), "local repository unavailable")
        self.executable = shutil.which("git")
        require(self.executable is not None, "Git executable unavailable")
        self.deadline = time.monotonic() + seconds
        self.calls = 0
        require(self.run(["rev-parse", "--is-bare-repository"]).strip() == b"false", "working repository required")
        self.object_format = self.run(["rev-parse", "--show-object-format"]).strip().decode("ascii")
        require(self.object_format in ("sha1", "sha256"), "unsupported Git object format")

    def run(self, args, *, data=None, cap=4 * 1024 * 1024):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "GIT_TIME_CAP")
        self.calls += 1
        command = [self.executable, "--no-lazy-fetch", "--no-replace-objects", "-c", "core.fsmonitor=false", "-c", "core.pager=cat", *args]
        process = subprocess.Popen(command, cwd=self.directory, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            env=local_environment(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        chunks, problems = [], []
        def read():
            try:
                value = process.stdout.read(cap + 1)
                chunks.append(value)
                if len(value) > cap:
                    process.kill()
            except OSError:
                problems.append("GIT_RESPONSE_UNAVAILABLE")
        def write():
            try:
                process.stdin.write(data); process.stdin.close()
            except OSError:
                problems.append("GIT_INPUT_UNAVAILABLE")
        reader = threading.Thread(target=read, daemon=True); reader.start()
        writer = threading.Thread(target=write, daemon=True) if data is not None else None
        if writer: writer.start()
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            process.kill(); process.wait(); reader.join(timeout=1)
            if writer: writer.join(timeout=1)
            raise ValueError("GIT_TIME_CAP") from exc
        reader.join(timeout=1)
        if writer: writer.join(timeout=1)
        process.stdout.close()
        require(not reader.is_alive() and (not writer or not writer.is_alive()) and not problems, "GIT_RESPONSE_UNAVAILABLE")
        result = b"".join(chunks)
        require(len(result) <= cap, "GIT_RESPONSE_BYTE_CAP")
        require(process.returncode == 0, "GIT_READ_FAILED")
        return result

    def resolve(self, ref):
        require(isinstance(ref, str) and 0 < len(ref) <= 1024 and not ref.startswith("-") and
                not any(ord(c) < 32 for c in ref), "invalid Git revision")
        commit = self.run(["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"]).strip().decode("ascii")
        require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit), "full Git commit required")
        return commit


def collect(directory, ref, config, at=None):
    git = Git(directory, config["budget"]["seconds"])
    commit = git.resolve(ref)
    tree = git.run(["rev-parse", commit + "^{tree}"]).strip().decode("ascii")
    commit_epoch = int(git.run(["show", "-s", "--format=%ct", commit]).strip())
    observed = timestamp(at or datetime.fromtimestamp(commit_epoch, timezone.utc).isoformat())
    # A local identity names the complete root set, never an inferred forge id.
    roots_raw = git.run(["rev-list", "--max-parents=0", commit], cap=65536)
    roots = sorted(set(roots_raw.decode("ascii").splitlines()))
    require(0 < len(roots) <= 256 and all(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", r) for r in roots), "local root identity unavailable")
    rows = git.run(["ls-tree", "-r", "-l", "-z", "--full-tree", tree])
    commit_bytes = git.run(["cat-file", "commit", commit], cap=1024 * 1024)
    tree_rows = git.run(["ls-tree", "-r", "-t", "-z", "--full-tree", tree])
    tree_ids = {tree}
    for row in filter(None, tree_rows.split(b"\0")):
        mode, kind, oid = row.split(b"\t", 1)[0].split()
        if kind == b"tree": tree_ids.add(oid.decode("ascii"))
    require(len(tree_ids) <= 10000, "TREE_PROOF_COUNT_CAP")
    tree_proof = {}
    if tree_ids:
        raw = git.run(["cat-file", "--batch"], data="".join(t + "\n" for t in sorted(tree_ids)).encode("ascii"), cap=8 * 1024 * 1024)
        offset = 0
        for oid in sorted(tree_ids):
            end = raw.index(b"\n", offset); actual, kind, size = raw[offset:end].split(); offset = end + 1
            require(actual.decode("ascii") == oid and kind == b"tree", "tree proof header mismatch")
            value = raw[offset:offset + int(size)]; offset += int(size)
            require(raw[offset:offset + 1] == b"\n", "tree proof truncation"); offset += 1
            tree_proof[oid] = base64.b64encode(value).decode("ascii")
        require(offset == len(raw), "unexpected tree proof bytes")
    entries, selected, total = [], [], 0
    for row in sorted(filter(None, rows.split(b"\0")), key=lambda r: r.split(b"\t", 1)[1]):
        header, filename = row.split(b"\t", 1)
        mode, kind, oid, size = header.split()
        entry = {"path": None, "path_base64": base64.b64encode(filename).decode("ascii"), "mode": mode.decode("ascii"),
                 "kind": kind.decode("ascii"), "object_id": oid.decode("ascii"), "size": None if size == b"-" else int(size),
                 "status": "UNAVAILABLE", "reason": "UNSAFE_PATH"}
        try:
            entry["path"] = path(filename.decode("utf-8"))
        except (UnicodeError, ValueError):
            entries.append(entry); continue
        name = entry["path"]
        included = not config["include"] or any(name == p or name.startswith(p + "/") for p in config["include"])
        excluded = any(name == p or name.startswith(p + "/") for p in config["exclude"])
        if not included or excluded:
            entry.update(status="OUT_OF_SCOPE", reason="POLICY_EXCLUSION")
        elif mode not in (b"100644", b"100755") or kind != b"blob":
            entry.update(reason="SOURCE_LINK_OR_SUBMODULE")
        elif not name.endswith(".py"):
            entry.update(status="UNSUPPORTED", reason="LANGUAGE_UNSUPPORTED")
        elif entry["size"] > config["budget"]["max_file_bytes"]:
            entry.update(reason="FILE_BYTE_CAP")
        elif len(selected) >= config["budget"]["max_files"]:
            entry.update(reason="FILE_COUNT_CAP")
        elif total + entry["size"] > config["budget"]["max_total_bytes"]:
            entry.update(reason="TOTAL_BYTE_CAP")
        else:
            entry.update(status="ADMITTED", reason=None); selected.append(entry); total += entry["size"]
        entries.append(entry)
    sources = {}
    if selected:
        data = "".join(e["object_id"] + "\n" for e in selected).encode("ascii")
        raw = git.run(["cat-file", "--batch"], data=data, cap=total + len(selected) * 160)
        offset = 0
        for entry in selected:
            end = raw.index(b"\n", offset)
            oid, kind, size = raw[offset:end].split(); offset = end + 1
            require(oid.decode("ascii") == entry["object_id"] and kind == b"blob" and int(size) == entry["size"], "Git blob header mismatch")
            value = raw[offset:offset + entry["size"]]; offset += entry["size"]
            require(raw[offset:offset + 1] == b"\n" and blob_digest(value, git.object_format) == entry["object_id"], "Git blob content mismatch")
            offset += 1; sources[entry["path"]] = base64.b64encode(value).decode("ascii")
        require(offset == len(raw), "unexpected Git blob bytes")
    start = instant(observed) - timedelta(days=config["history"]["days"])
    history = {"status": "NOT_REQUESTED", "reasons": [], "start": timestamp(start.isoformat()), "end": observed,
               "commits": []}
    if config["history"]["enabled"]:
        limit = config["history"]["max_commits"]
        try:
            if git.run(["rev-parse", "--is-shallow-repository"]).strip() == b"true":
                history["reasons"].append("SHALLOW_HISTORY")
            raw = git.run(["log", "--no-merges", "--format=%H%x00%ct", "-z", "--since-as-filter=" + history["start"],
                "--until=" + observed, "--max-count=" + str(limit + 1), commit], cap=(limit + 1) * 100)
            values = [v for v in raw.split(b"\0") if v]
            require(len(values) % 2 == 0, "Git history response malformed")
            refs = [(values[i].decode("ascii"), int(values[i + 1])) for i in range(0, len(values), 2)]
            history["status"] = "PARTIAL" if len(refs) > limit or history["reasons"] else "COMPLETE"
            if len(refs) > limit: history["reasons"].append("HISTORY_COMMIT_CAP")
            for oid, epoch in refs[:limit]:
                when = datetime.fromtimestamp(epoch, timezone.utc)
                require(start <= when <= instant(observed), "Git history timestamp outside window")
                raw = git.run(["diff-tree", "--root", "--no-commit-id", "--numstat", "-z", "-r", "--no-renames",
                               "--no-ext-diff", "--no-textconv", oid])
                changes = []
                for change in filter(None, raw.split(b"\0")):
                    added, deleted, filename = change.split(b"\t", 2)
                    try: name = path(filename.decode("utf-8"))
                    except (ValueError, UnicodeError):
                        history["status"] = "PARTIAL"
                        if "HISTORY_PATH_UNAVAILABLE" not in history["reasons"]:
                            history["reasons"].append("HISTORY_PATH_UNAVAILABLE")
                        continue
                    changes.append({"path": name, "added": None if added == b"-" else int(added),
                                    "deleted": None if deleted == b"-" else int(deleted)})
                history["commits"].append({"revision": oid, "committed_at": timestamp(when.isoformat()), "changes": sorted(changes, key=lambda c: c["path"])})
        except (ValueError, OSError) as exc:
            history["status"] = "PARTIAL" if history["commits"] else "UNAVAILABLE"
            history["reasons"].append("HISTORY_TIME_CAP" if "TIME_CAP" in str(exc) else "HISTORY_READ_UNAVAILABLE")
    history["commits"].sort(key=lambda c: (c["committed_at"], c["revision"]))
    return {"subject": {"kind": "LOCAL_GIT", "object_format": git.object_format, "roots": roots,
            "repository_id": digest({"object_format": git.object_format, "roots": roots}), "revision": commit, "tree": tree},
            "observed_at": observed, "entries": entries, "sources": sources, "history": history,
            "proof": {"commit": base64.b64encode(commit_bytes).decode("ascii"), "trees": tree_proof}}
