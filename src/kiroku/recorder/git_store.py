"""Git-on-disk backup store. One repo, one file per device."""

from __future__ import annotations

import hashlib
from pathlib import Path

from kiroku.config import get_settings
from kiroku.logging import get_logger

log = get_logger(__name__)


def _slugify(value: str) -> str:
    keep = "-_."
    return "".join(c if c.isalnum() or c in keep else "_" for c in value)


class GitStore:
    """Wraps a bare-on-disk git repo for storing device configs.

    Layout::

        <repo_root>/<group>/<device>.cfg

    Each successful backup that *changes* the file produces a commit. If the
    content hash matches the prior commit's blob, no commit is created and
    we return ``None`` for the sha.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or get_settings().backup_repo_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._repo = self._open_or_init()

    def _open_or_init(self):
        from git import Repo

        if (self.root / ".git").exists():
            return Repo(self.root)
        repo = Repo.init(self.root)
        # Seed an initial commit so subsequent commits have a parent.
        gitkeep = self.root / ".gitkeep"
        gitkeep.touch()
        repo.index.add([str(gitkeep.relative_to(self.root))])
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "Kiroku Recorder")
            cw.set_value("user", "email", "kiroku@localhost")
        repo.index.commit("init")
        return repo

    def file_path(self, *, group: str, device: str) -> str:
        """Return the repo-relative path for a device's config file."""
        return str(Path(_slugify(group)) / f"{_slugify(device)}.cfg")

    def stage(self, *, group: str, device: str, content: str) -> tuple[bool, str]:
        """Write file to disk only. Does NOT add to git index.

        Returns (changed, sha256). changed=False means content was identical to what was on disk.
        """
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        rel = Path(_slugify(group)) / f"{_slugify(device)}.cfg"
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            existing = target.read_text(encoding="utf-8", errors="replace")
            if hashlib.sha256(existing.encode("utf-8")).hexdigest() == sha256:
                log.debug("no change", device=device, group=group)
                return False, sha256

        target.write_text(content, encoding="utf-8")
        return True, sha256

    def commit_batch(self, rel_paths: list[str], message: str) -> str | None:
        """Stage all given paths and commit in one operation. Returns commit sha or None."""
        if not rel_paths:
            return None
        self._repo.index.add(rel_paths)
        if not self._repo.index.diff("HEAD"):
            return None
        commit = self._repo.index.commit(message)
        log.info("git batch commit", sha=commit.hexsha[:8], files=len(rel_paths))
        return commit.hexsha

    def changed_files(self, sha: str) -> list[str]:
        """Return repo-relative paths of files changed in a commit."""
        try:
            commit = self._repo.commit(sha)
            if not commit.parents:
                return [item.path for item in commit.tree.traverse() if item.type == "blob"]
            return [d.b_path or d.a_path for d in commit.diff(commit.parents[0])]
        except Exception:
            return []

    def history(self, rel_path: str, max_count: int = 50) -> list[dict]:
        """Return git log entries for a specific file."""
        return [
            {
                "sha": c.hexsha[:8],
                "sha_full": c.hexsha,
                "message": c.message.strip().split("\n")[0],
                "date": c.committed_datetime.isoformat(),
            }
            for c in self._repo.iter_commits(paths=rel_path, max_count=max_count)
        ]

    def search_history(self, rel_path: str, query: str, max_count: int = 200) -> list[dict]:
        """Search for query across all commits of a file.

        Returns list of match dicts: sha, sha_full, date, message, line_no, line.
        Case-insensitive substring match.
        """
        results = []
        q = query.lower()
        for commit in self._repo.iter_commits(paths=rel_path, max_count=max_count):
            try:
                blob = commit.tree[rel_path]
                content = blob.data_stream.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                if q in line.lower():
                    results.append({
                        "sha": commit.hexsha[:8],
                        "sha_full": commit.hexsha,
                        "date": commit.committed_datetime.isoformat(),
                        "message": commit.message.strip().split("\n")[0],
                        "line_no": line_no,
                        "line": line,
                    })
        return results

    def read_at(self, rel_path: str, sha: str) -> str | None:
        """Return file content at a specific commit SHA (full or short)."""
        try:
            commit = self._repo.commit(sha)
            blob = commit.tree[rel_path]
            return blob.data_stream.read().decode("utf-8", errors="replace")
        except Exception:
            return None

    def diff_commits(self, rel_path: str, sha_a: str, sha_b: str) -> list[dict]:
        """Return structured diff lines between two commits for one file.

        Each entry has: type ('context'|'added'|'removed'|'header'),
        old_no (int|None), new_no (int|None), text (str).
        """
        import difflib

        a = (self.read_at(rel_path, sha_a) or "").splitlines(keepends=True)
        b = (self.read_at(rel_path, sha_b) or "").splitlines(keepends=True)

        rows: list[dict] = []
        old_no = new_no = 0
        for line in difflib.unified_diff(
            a, b, fromfile=sha_a[:8], tofile=sha_b[:8], lineterm=""
        ):
            text = line.rstrip("\n")
            if text.startswith("@@"):
                # parse @@ -old_start,... +new_start,... @@
                try:
                    parts = text.split(" ")
                    old_no = abs(int(parts[1].split(",")[0]))
                    new_no = abs(int(parts[2].split(",")[0]))
                except Exception:
                    pass
                rows.append(
                    {"type": "header", "old_no": None, "new_no": None, "text": text}
                )
            elif text.startswith("---") or text.startswith("+++"):
                rows.append(
                    {"type": "header", "old_no": None, "new_no": None, "text": text}
                )
            elif text.startswith("-"):
                rows.append(
                    {
                        "type": "removed",
                        "old_no": old_no,
                        "new_no": None,
                        "text": text[1:],
                    }
                )
                old_no += 1
            elif text.startswith("+"):
                rows.append(
                    {
                        "type": "added",
                        "old_no": None,
                        "new_no": new_no,
                        "text": text[1:],
                    }
                )
                new_no += 1
            else:
                rows.append(
                    {
                        "type": "context",
                        "old_no": old_no,
                        "new_no": new_no,
                        "text": text[1:] if text.startswith(" ") else text,
                    }
                )
                old_no += 1
                new_no += 1
        return rows

    def write(
        self, *, group: str, device: str, content: str, author_note: str = ""
    ) -> tuple[str | None, str]:
        """Write content, commit if changed. Returns (commit_sha_or_None, sha256)."""
        changed, sha256 = self.stage(group=group, device=device, content=content)
        if not changed:
            return None, sha256
        rel = Path(_slugify(group)) / f"{_slugify(device)}.cfg"
        self._repo.index.add([str(rel)])
        msg = f"backup: {group}/{device}"
        if author_note:
            msg += f"\n\n{author_note}"
        commit = self._repo.index.commit(msg)
        return commit.hexsha, sha256
