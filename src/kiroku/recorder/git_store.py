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

    def write(self, *, group: str, device: str, content: str,
              author_note: str = "") -> tuple[str | None, str]:
        """Write content, commit if changed. Returns (commit_sha_or_None, sha256)."""
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        rel = Path(_slugify(group)) / f"{_slugify(device)}.cfg"
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            existing = target.read_text(encoding="utf-8", errors="replace")
            if hashlib.sha256(existing.encode("utf-8")).hexdigest() == sha256:
                log.debug("no change", device=device, group=group)
                return None, sha256

        target.write_text(content, encoding="utf-8")
        self._repo.index.add([str(rel)])
        msg = f"backup: {group}/{device}"
        if author_note:
            msg += f"\n\n{author_note}"
        commit = self._repo.index.commit(msg)
        return commit.hexsha, sha256
