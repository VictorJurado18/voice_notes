"""Operations on an explicitly selected item in the library browser."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def path_is_within(path: Path, parent: Path) -> bool:
    """Compare complete, normalized path components rather than prefixes."""
    return path.resolve().is_relative_to(parent.resolve())


def checked_delete_target(
    directory: Path, selected: Path, *, protected_roots: Iterable[Path] = (),
) -> Path:
    """Allow only an existing, immediate child explicitly selected in a folder.

    Do not follow a selected shortcut, symlink or junction to a different
    location. Library and recording roots are also protected when the browser
    navigates to their parent directories.
    """
    directory = directory.expanduser().resolve(strict=True)
    selected = selected.expanduser().absolute()
    selected.lstat()
    if selected.is_symlink() or selected.is_junction():
        raise ValueError("Não é possível excluir links ou junções pela Biblioteca.")
    target = selected.resolve(strict=True)
    if target.parent != directory or target == directory or target.parent == target:
        raise ValueError("Selecione um arquivo ou pasta dentro da pasta exibida.")
    if not (target.is_file() or target.is_dir()):
        raise ValueError("Este tipo de item não pode ser excluído pela Biblioteca.")
    if any(path_is_within(root, target) for root in protected_roots):
        raise ValueError(
            "Esta é uma pasta principal da Biblioteca ou das gravações. "
            "Abra a pasta e selecione a gravação que deseja excluir."
        )
    return target


def recycle_library_entry(
    directory: Path, selected: Path, *, protected_roots: Iterable[Path] = (),
) -> Path:
    """Send one selected file or complete folder to the OS Recycle Bin.

    Revalidate immediately before the operation, even if a confirmation dialog
    has already checked the target. There is no permanent-deletion fallback.
    The nativeLib dependency provides the modern IFileOperation backend on
    Windows, including its recycle-on-delete flags and progress sink.
    """
    from send2trash import send2trash

    target = checked_delete_target(directory, selected, protected_roots=protected_roots)
    send2trash(str(target))
    return target
