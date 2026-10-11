#!/usr/bin/env python3
"""Eval-Harness fuer nanobot.

Stellt dem Bot eine Reihe von Aufgaben und prueft die Antworten gegen erwartete
Muster. Zweck: "Der Bot ist dumm" von einem Gefuehl in eine Zahl verwandeln.

Aufruf:
    python customize/eval/run_eval.py --home ~/.nanobot
    python customize/eval/run_eval.py --home ~/.nanobot --json report.json
    python customize/eval/run_eval.py --only rechnen

Beendet sich mit Exit-Code 0, wenn alle Aufgaben bestanden wurden, sonst 1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
HERE = Path(__file__).resolve().parent

#: Marker that unmistakably indicate the UnconfiguredProvider stub is answering.
STUB_MARKERS = (
    "Nanobot needs a model before it can chat",
    "Agent cannot start: No provider is configured",
    "No provider is configured for model",
)


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def find_nanobot() -> str:
    """Locate a usable nanobot executable."""
    override = os.environ.get("NANOBOT_BIN")
    if override and Path(override).exists():
        return override
    found = shutil.which("nanobot")
    if found:
        return found
    # Fall back to a virtualenv next to the repository root.
    for candidate in (HERE.parents[1] / ".venv" / "bin" / "nanobot",):
        if candidate.exists():
            return str(candidate)
    return "nanobot"


@dataclass
class TaskResult:
    id: str
    category: str
    passed: bool
    duration_s: float
    reason: str
    answer: str = ""
    tool_calls: list[str] = field(default_factory=list)


def run_one(nanobot_bin: str, home: str, task: dict, timeout: int) -> TaskResult:
    """Run a single task in a fresh session and score it."""
    session = f"eval-{task['id']}-{int(time.time())}"
    cmd = [
        nanobot_bin,
        "--home", home,
        "agent",
        "-s", session,
        "--no-markdown",
        "-m", task["prompt"],
    ]

    started = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
        )
        raw = strip_ansi((proc.stdout or "") + "\n" + (proc.stderr or ""))
    except subprocess.TimeoutExpired:
        return TaskResult(
            task["id"], task["category"], False, float(timeout), f"Timeout nach {timeout}s",
        )
    except FileNotFoundError:
        return TaskResult(
            task["id"], task["category"], False, 0.0,
            f"nanobot nicht ausfuehrbar: {nanobot_bin}",
        )
    duration = time.time() - started

    # Detect the unconfigured stub: everything fails for one reason, not eight.
    for marker in STUB_MARKERS:
        if marker in raw:
            return TaskResult(
                task["id"], task["category"], False, duration,
                "KEIN MODELL KONFIGURIERT - der Bot antwortet mit dem Setup-Stub",
                answer=marker, tool_calls=[],
            )

    tool_calls = sorted(set(re.findall(
        r"\b(exec|read_file|write_file|edit_file|apply_patch|list_dir|rg|web_search|web_fetch|cron|subagent)\b",
        raw,
    )))

    pattern = re.compile(task["expect_pattern"], re.IGNORECASE | re.MULTILINE)
    match = pattern.search(raw)
    if match:
        return TaskResult(task["id"], task["category"], True, duration, "ok",
                          answer=match.group(0).strip(), tool_calls=tool_calls)

    # Give a useful reason: did the answer line exist but carry the wrong value?
    result_line = re.search(r"ERGEBNIS:\s*(.+)", raw)
    if result_line:
        reason = f"falscher Wert: {result_line.group(1).strip()[:40]}"
    else:
        tail = " ".join(raw.split())[-100:]
        reason = f"kein Treffer (Ausgabe endet: ...{tail})"
    return TaskResult(task["id"], task["category"], False, duration, reason, tool_calls=tool_calls)


def main() -> int:
    ap = argparse.ArgumentParser(description="nanobot Eval-Harness")
    ap.add_argument("--home", default=os.path.expanduser("~/.nanobot"),
                    help="nanobot-Instanzverzeichnis (Default: ~/.nanobot)")
    ap.add_argument("--tasks", default=str(HERE / "tasks.json"), help="Pfad zur Aufgabenliste")
    ap.add_argument("--only", default=None, help="Nur diese Kategorie ausfuehren")
    ap.add_argument("--timeout", type=int, default=180, help="Timeout pro Aufgabe in Sekunden")
    ap.add_argument("--json", default=None, help="Bericht als JSON hierhin schreiben")
    args = ap.parse_args()

    nanobot_bin = find_nanobot()
    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"Aufgabenliste nicht gefunden: {tasks_path}", file=sys.stderr)
        return 2

    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"]
    if args.only:
        tasks = [t for t in tasks if t["category"] == args.only]
        if not tasks:
            print(f"Keine Aufgaben in Kategorie {args.only!r}", file=sys.stderr)
            return 2

    print(f"nanobot Eval - {len(tasks)} Aufgaben")
    print(f"  Binary: {nanobot_bin}")
    print(f"  Instanz: {args.home}")
    print()

    results: list[TaskResult] = []
    for i, task in enumerate(tasks, 1):
        r = run_one(nanobot_bin, args.home, task, args.timeout)
        results.append(r)
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{i:2d}/{len(tasks)}] {mark}  {task['id']:20s} {r.duration_s:5.1f}s  {r.reason}")
        if r.passed and r.tool_calls:
            print(f"{'':18s}Tools: {', '.join(r.tool_calls)}")

    # Summary by category
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print()
    print("=" * 62)
    categories: dict[str, list[TaskResult]] = {}
    for r in results:
        categories.setdefault(r.category, []).append(r)
    for cat, rs in sorted(categories.items()):
        ok = sum(1 for r in rs if r.passed)
        bar = "#" * round(20 * ok / len(rs))
        print(f"  {cat:12s} {ok}/{len(rs)}  {bar}")
    print("=" * 62)
    pct = (100 * passed / total) if total else 0.0
    print(f"  GESAMT: {passed}/{total}  ({pct:.0f} %)")

    stub_hits = [r for r in results if "Setup-Stub" in r.reason]
    if stub_hits:
        print()
        print("  !! Der Bot hat KEIN Modell. Alle Fehlschlaege haben dieselbe Ursache.")
        print("     Einrichten mit:  nanobot onboard --wizard")
        print("     oder:            nanobot webui   ->   Settings -> Models")

    tool_used = sum(1 for r in results if r.tool_calls)
    print(f"  Aufgaben mit Tool-Nutzung: {tool_used}/{total}")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "nanobot_bin": nanobot_bin,
            "home": args.home,
            "passed": passed,
            "total": total,
            "percent": round(pct, 1),
            "tool_used": tool_used,
            "no_model_configured": bool(stub_hits),
            "results": [
                {"id": r.id, "category": r.category, "passed": r.passed,
                 "duration_s": round(r.duration_s, 2), "reason": r.reason,
                 "answer": r.answer, "tool_calls": r.tool_calls}
                for r in results
            ],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Bericht geschrieben: {args.json}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
