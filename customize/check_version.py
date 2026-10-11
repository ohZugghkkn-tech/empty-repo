#!/usr/bin/env python3
"""Fork-Tracking-Pruefer: Version und Upstream-Basis muessen zusammenpassen.

Der Changelog in ``CHANGELOG.md`` ist die Quelle fuer die Fork-Version. Diese
Datei prueft, dass die Angaben maschinell stimmen:

  1. Die neueste freigegebene Version im Changelog (ohne ``Unreleased``) traegt
     als Basis dieselbe Nummer wie ``pyproject.toml``. Fork-Releases zaehlen als
     ``0.3.5-fork.1``; ``pyproject.toml`` bleibt bei der Upstream-Version, weil
     PyPI keine lokalen Versionszusatze annimmt.
  2. Die Fork-Tracking-Tabelle nennt das Upstream-Repository ``HKUDS/nanobot``.
  3. Die Abschnitte im Changelog sind eindeutig (keine doppelte Version).

Aufruf:
    python customize/check_version.py
    python customize/check_version.py --self-test

Exit-Codes: 0 = in Ordnung, 1 = Befund, 2 = Datei/Aufruf nicht lesbar.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"

UPSTREAM_REPO = "HKUDS/nanobot"
VERSION_HEADING = re.compile(
    # Datumstrenner: Bindestrich (Keep a Changelog) oder Gedankenstrich.
    r"^##\s+\[(?P<version>[^\]]+)\](?:\s*[-–—]\s*(?P<date>\d{4}-\d{2}-\d{2}))?\s*$",
    re.MULTILINE,
)
FORK_SUFFIX = re.compile(r"^(?P<base>\d+\.\d+\.\d+)-fork\.(?P<counter>\d+)$")


def released_versions(changelog_text: str) -> list[tuple[str, str]]:
    """Return ``(version, date)`` for every released heading, newest first."""
    versions: list[tuple[str, str]] = []
    for match in VERSION_HEADING.finditer(changelog_text):
        version = match.group("version").strip()
        if version.lower() == "unreleased":
            continue
        versions.append((version, match.group("date") or ""))
    return versions


def base_version(version: str) -> str:
    """Strip the ``-fork.N`` suffix; plain upstream versions pass through."""
    match = FORK_SUFFIX.match(version)
    return match.group("base") if match else version


def check(pyproject_text: str, changelog_text: str) -> list[str]:
    """Return the problems found; an empty list means everything matches."""
    problems: list[str] = []

    try:
        project_version = str(tomllib.loads(pyproject_text)["project"]["version"])
    except (KeyError, tomllib.TOMLDecodeError) as exc:
        return [f"pyproject.toml: project.version nicht lesbar ({exc})."]

    versions = released_versions(changelog_text)
    if not versions:
        problems.append(
            "CHANGELOG.md: kein Abschnitt der Form '## [0.3.5-fork.1] - JJJJ-MM-TT' gefunden."
        )
    else:
        newest, date = versions[0]
        if not date:
            problems.append(f"CHANGELOG.md: Abschnitt '{newest}' hat kein Datum.")
        if base_version(newest) != project_version:
            problems.append(
                f"Version passt nicht: CHANGELOG.md nennt '{newest}' "
                f"(Basis {base_version(newest)}), pyproject.toml sagt '{project_version}'."
            )
        seen: dict[str, int] = {}
        for version, _ in versions:
            seen[version] = seen.get(version, 0) + 1
        duplicates = sorted(name for name, count in seen.items() if count > 1)
        if duplicates:
            problems.append(f"CHANGELOG.md: doppelte Abschnitte: {', '.join(duplicates)}.")

    if UPSTREAM_REPO not in changelog_text:
        problems.append(
            f"CHANGELOG.md: Fork-Tracking nennt '{UPSTREAM_REPO}' nicht - "
            "die Upstream-Basis muss auffindbar bleiben."
        )
    return problems


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"\nFEHLER: {path} nicht lesbar: {exc}\n", file=sys.stderr)
        raise SystemExit(2) from exc


# --------------------------------------------------------------------------
# Selbsttest: der Pruefer muss beide Richtungen erkennen.
# --------------------------------------------------------------------------

_SELF_TEST_CASES: list[tuple[str, str, str, bool]] = [
    (
        "passende-version",
        '[project]\nversion = "0.3.5"\n',
        "## [Unreleased]\n\n## [0.3.5-fork.1] - 2026-10-11\n\nUpstream: HKUDS/nanobot\n",
        True,
    ),
    (
        "upstream-version-ohne-suffix",
        '[project]\nversion = "0.3.5"\n',
        "## [0.3.5] - 2026-10-11\n\nUpstream: HKUDS/nanobot\n",
        True,
    ),
    (
        "version-abweichung",
        '[project]\nversion = "0.3.5"\n',
        "## [0.3.4-fork.1] - 2026-10-11\n\nUpstream: HKUDS/nanobot\n",
        False,
    ),
    (
        "upstream-nicht-genannt",
        '[project]\nversion = "0.3.5"\n',
        "## [0.3.5-fork.1] - 2026-10-11\n",
        False,
    ),
    (
        "kein-release-abschnitt",
        '[project]\nversion = "0.3.5"\n',
        "## [Unreleased]\n\nUpstream: HKUDS/nanobot\n",
        False,
    ),
    (
        "doppelter-abschnitt",
        '[project]\nversion = "0.3.5"\n',
        "## [0.3.5-fork.1] - 2026-10-11\nUpstream: HKUDS/nanobot\n"
        "## [0.3.5-fork.1] - 2026-10-10\n",
        False,
    ),
]


def run_self_test() -> int:
    print()
    print("nanobot customize - Selbsttest der Versionspruefung")
    print()
    failures = 0
    for name, pyproject, changelog, expect_ok in _SELF_TEST_CASES:
        problems = check(pyproject, changelog)
        ok = (not problems) == expect_ok
        detail = "wie erwartet" if not problems else problems[0]
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:28s} {detail}")
        if not ok:
            failures += 1
    print()
    print(f"Selbsttest: {len(_SELF_TEST_CASES) - failures}/{len(_SELF_TEST_CASES)} bestanden")
    print()
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prueft Fork-Version und Upstream-Basis (CHANGELOG.md vs. pyproject.toml).",
    )
    parser.add_argument("--self-test", action="store_true",
                        help="Den Pruefer gegen eingebaute Fixtures testen")
    parser.add_argument("--changelog", type=Path, default=CHANGELOG)
    parser.add_argument("--pyproject", type=Path, default=PYPROJECT)
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    print()
    print("nanobot customize - Fork-Tracking")
    print(f"  Changelog:  {args.changelog}")
    print(f"  Projekt:    {args.pyproject}")
    print()

    problems = check(_read(args.pyproject), _read(args.changelog))
    if problems:
        for problem in problems:
            print(f"  ERROR {problem}")
        print()
        print("Bitte Version oder Tracking-Tabelle korrigieren.")
        print()
        return 1

    versions = released_versions(_read(args.changelog))
    print(f"  OK    Fork-Version {versions[0][0]} passt zu pyproject.toml")
    print(f"  OK    Upstream-Basis: {UPSTREAM_REPO}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
