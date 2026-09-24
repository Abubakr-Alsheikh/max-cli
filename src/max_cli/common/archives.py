"""Safe tar extraction: no member may land outside the destination folder."""

import tarfile
from pathlib import Path
from typing import Iterable, List, Optional

from max_cli.common.exceptions import ProcessingError


class UnsafeArchiveError(ProcessingError):
    """An archive member would escape the extraction folder."""


def _is_inside(candidate: Path, root: Path) -> bool:
    return candidate == root or root in candidate.parents


def _check_member(member: tarfile.TarInfo, root: Path) -> None:
    if member.isdev():
        raise UnsafeArchiveError(f"Refusing device file in archive: {member.name}")

    target = (root / member.name).resolve()
    if not _is_inside(target, root):
        raise UnsafeArchiveError(f"Archive member escapes destination: {member.name}")

    if member.issym():
        link_target = (target.parent / member.linkname).resolve()
        if not _is_inside(link_target, root):
            raise UnsafeArchiveError(
                f"Symlink points outside destination: {member.name} -> {member.linkname}"
            )
    elif member.islnk():
        link_target = (root / member.linkname).resolve()
        if not _is_inside(link_target, root):
            raise UnsafeArchiveError(
                f"Hard link points outside destination: {member.name} -> {member.linkname}"
            )


def safe_extract_tar(
    archive: tarfile.TarFile,
    dest: Path,
    members: Optional[Iterable[tarfile.TarInfo]] = None,
) -> None:
    """Extract `members` (default: all) into `dest` after validating every member.

    Nothing is extracted if any member is unsafe. Uses the stdlib "data" filter
    where available (Python 3.12+, 3.9.17+ security releases) as a second layer.
    """
    root = Path(dest).resolve()
    selected: List[tarfile.TarInfo] = (
        list(members) if members is not None else archive.getmembers()
    )
    for member in selected:
        _check_member(member, root)

    if hasattr(tarfile, "data_filter"):
        archive.extractall(root, members=selected, filter="data")
    else:
        for member in selected:  # each member validated above
            archive.extract(member, root)
