from __future__ import annotations

from pathlib import Path


PROBLEM_DIRNAMES = ("문제", "원본문제")
SOLUTION_DIRNAME = "풀이"
OX_DIRNAME = "OX문제"


def resolve_case_insensitive(base_dir: Path, filename: str) -> Path | None:
    candidate = base_dir / filename
    if candidate.exists():
        return candidate
    if not base_dir.is_dir():
        return None
    target = filename.casefold()
    for path in base_dir.iterdir():
        if path.name.casefold() == target:
            return path
    return None


def year_problem_dirs(year_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    for dirname in PROBLEM_DIRNAMES:
        problem_dir = year_dir / dirname
        if problem_dir.is_dir():
            dirs.append(problem_dir)
    dirs.append(year_dir)
    return dirs


def year_solution_dirs(year_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    solution_dir = year_dir / SOLUTION_DIRNAME
    if solution_dir.is_dir():
        dirs.append(solution_dir)
    dirs.append(year_dir)
    return dirs


def year_ox_dirs(year_dir: Path) -> list[Path]:
    dirs: list[Path] = []
    shared_ox_dir = year_dir.parent / OX_DIRNAME
    if shared_ox_dir.is_dir():
        dirs.append(shared_ox_dir)
    ox_dir = year_dir / OX_DIRNAME
    if ox_dir.is_dir():
        dirs.append(ox_dir)
    dirs.append(year_dir)
    return dirs


def find_year_file(year_dir: Path, filename: str, *, kind: str) -> Path:
    if kind == "solution":
        candidates = [base / filename for base in year_solution_dirs(year_dir)]
    elif kind == "ox":
        year_prefixed = f"{year_dir.name}_{filename}"
        candidates = []
        for base in year_ox_dirs(year_dir):
            candidates.append(base / year_prefixed)
            candidates.append(base / filename)
    elif kind == "problem":
        candidates = [base / filename for base in year_problem_dirs(year_dir)]
    else:
        candidates = [
            year_dir / filename,
            *(base / filename for base in year_solution_dirs(year_dir)),
            *(base / filename for base in year_problem_dirs(year_dir)),
        ]

    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        direct = resolve_case_insensitive(path.parent, path.name)
        if direct is not None:
            return direct
    raise FileNotFoundError(f"Cannot find '{filename}' under {year_dir}")


def list_year_pdfs(year_dir: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for base in year_problem_dirs(year_dir):
        for path in sorted(base.glob("*.pdf")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    return files
