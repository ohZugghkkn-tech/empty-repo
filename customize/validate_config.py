#!/usr/bin/env python3
"""Konfigurationspruefer fuer die customize-Varianten von nanobot.

Prueft die beiden ausgelieferten Konfigurationen auf die Fehler, die sonst erst
beim Start auffallen - vor allem die drei dokumentierten Fallen:

  1. ``${VAR}`` ist strikt und global. Ein einziger nicht gesetzter Platzhalter
     blockiert den Start, auch fuer Presets, die ihn gar nicht brauchen.
     ``${VAR:-fallback}`` gibt es nicht.
  2. Presets, die ins Leere zeigen: ``modelPreset`` oder ``fallbackModels``
     verweisen auf einen Namen, den ``modelPresets`` nicht kennt.
  3. Denk-Budget: ``xhigh``/``max`` sind bei Modellen mit manuellen Budgets
     schlechter als ``high`` (4 096 statt 8 192 Tokens).

Zusaetzlich: Ausgabelimit groesser als das Kontextfenster, einzelne
Tool-Ergebnisse groesser als das Kontextfenster, Klartext-Schluessel in einer
versionierten Datei.

Aufruf:
    python customize/validate_config.py                     # beide Varianten
    python customize/validate_config.py --strict             # Warnungen = Fehler
    python customize/validate_config.py customize/config.ollama.json
    python customize/validate_config.py --self-test          # prueft den Pruefer

Exit-Codes: 0 = in Ordnung, 1 = Befund, 2 = Aufruf-/Dateifehler.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIGS = ("config.json", "config.ollama.json")

#: nanobot/config/loader.py:194
ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
#: Anything that looks like a placeholder, to catch unsupported syntax too.
ANY_PLACEHOLDER = re.compile(r"\$\{[^}]*\}")
#: Bash-style defaults (${VAR:-x}) are NOT supported by nanobot.
UNSUPPORTED_DEFAULT = re.compile(r"\$\{[^}]*:[-=?+]")
#: Anthropic model families without manual thinking budgets (source line 43).
ADAPTIVE_ONLY_MIN: dict[str, tuple[int, int]] = {
    "opus": (4, 7),
    "sonnet": (5, 0),
    "fable": (5, 0),
    "mythos": (5, 0),
}
CLAUDE_VERSION = re.compile(
    r"claude-(?P<family>[a-z]+)-(?P<major>\d+)(?:-(?P<minor>\d{1,2})(?=-|$))?"
)
MANUAL_BUDGET = {"low": 1024, "medium": 4096}
KNOWN_EFFORTS = ("none", "low", "medium", "high", "xhigh", "max", "adaptive")
#: Providers that work without an apiKey and without a ``providers`` entry.
KEYLESS_PROVIDERS = frozenset({"ollama"})
SECRET_LIKE = re.compile(r"^(?:sk-|sk_|gsk_|xai-|AIza|ghp_|github_pat_)")

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"
_SEVERITY_ORDER = {ERROR: 0, WARN: 1, INFO: 2}


@dataclass(frozen=True)
class Issue:
    """One finding, with the fix that makes it go away."""

    severity: str
    where: str
    message: str
    fix: str = ""


def walk_strings(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(dotted_path, value)`` for every string in a nested structure."""
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            yield from walk_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk_strings(value, f"{path}[{index}]")
    elif isinstance(obj, str):
        yield path, obj


def _model_family(model: str) -> tuple[str, int, int] | None:
    match = CLAUDE_VERSION.search(model.lower())
    if match is None:
        return None
    return (
        match.group("family"),
        int(match.group("major")),
        int(match.group("minor") or 0),
    )


def is_adaptive_only(model: str) -> bool:
    """True for models whose thinking effort has no manual token budget."""
    parsed = _model_family(model)
    if parsed is None:
        return False
    family, major, minor = parsed
    minimum = ADAPTIVE_ONLY_MIN.get(family)
    return minimum is not None and (major, minor) >= minimum


def _table(config: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def check_placeholders(config: Mapping[str, Any], *, keyless: bool,
                       env: Mapping[str, str]) -> list[Issue]:
    """Verify every ``${VAR}`` reference, globally, exactly like nanobot does."""
    issues: list[Issue] = []
    references: list[tuple[str, str, str]] = []  # (path, raw, var)
    malformed = 0

    for path, text in walk_strings(config):
        if "$" not in text:
            continue
        for raw in ANY_PLACEHOLDER.findall(text):
            match = ENV_REF.fullmatch(raw)
            if match is not None:
                references.append((path, raw, match.group(1)))
                continue
            malformed += 1
            if UNSUPPORTED_DEFAULT.search(raw):
                # Handled with its own explanation below.
                continue
            issues.append(Issue(
                ERROR, path,
                f"Platzhalter {raw} hat eine Form, die nanobot nicht aufloest.",
                "Nur ${NAME} mit A-Z, a-z, 0-9 und _ verwenden.",
            ))
        if UNSUPPORTED_DEFAULT.search(text):
            issues.append(Issue(
                ERROR, path,
                "Default-Syntax ${VAR:-fallback} wird nicht unterstuetzt - "
                "nanobot kennt nur ${VAR} und bricht sonst zur Laufzeit ab.",
                "Variable vorher setzen oder einen eigenen Preset-Block ohne Platzhalter nutzen.",
            ))

    unset = [ref for ref in references if ref[2] not in env]
    if keyless and references:
        names = ", ".join(sorted({ref[2] for ref in references}))
        issues.append(Issue(
            ERROR, "(global)",
            f"Die schluesselfreie Variante enthaelt {len(references)} Platzhalter ({names}).",
            "Platzhalter entfernen - diese Variante muss ohne Umgebungsvariablen starten.",
        ))
    elif unset:
        for path, raw, var in unset:
            issues.append(Issue(
                WARN, path,
                f"{var} ist in dieser Umgebung nicht gesetzt - der Start bricht mit "
                "ConfigLoadError ab, solange der Platzhalter in der Datei steht.",
                f"export {var}=...   oder schluesselfreie Variante installieren "
                "(./customize/apply.sh --variant ollama).",
            ))
    if references:
        issues.append(Issue(
            INFO, "(global)",
            f"{len(references)} Platzhalter gefunden. nanobot prueft jeden String global, "
            "also blockiert jeder nicht gesetzte Wert alle Presets.",
            "Nur Variablen referenzieren, die wirklich gesetzt sind.",
        ))
    elif not keyless and not malformed:
        issues.append(Issue(
            INFO, "(global)",
            "Keine Platzhalter - die Datei startet ohne Umgebungsvariablen.",
        ))
    return issues


def check_secrets(config: Mapping[str, Any]) -> list[Issue]:
    """Refuse to ship a literal API key inside a versioned config file."""
    issues: list[Issue] = []
    providers = _table(config, "providers")
    for name, entry in providers.items():
        if not isinstance(entry, Mapping):
            # nanobot keeps such an entry as-is (model_extra), so a plain string
            # works as a comment field - but it can never configure a provider.
            issues.append(Issue(
                INFO, f"providers.{name}",
                "Kein Provider-Objekt (z.B. ein Kommentar-Feld). nanobot duldet das, "
                "es konfiguriert aber nichts.",
            ))
            continue
        key = entry.get("apiKey")
        if isinstance(key, str) and key.startswith("${"):
            continue
        if isinstance(key, str) and SECRET_LIKE.match(key.strip()):
            issues.append(Issue(
                ERROR, f"providers.{name}.apiKey",
                "Klartext-Schluessel in einer versionierten Datei.",
                f"Platzhalter verwenden: \"${{{name.upper()}_API_KEY}}\".",
            ))
    return issues


def check_presets(config: Mapping[str, Any]) -> list[Issue]:
    """Catch presets that point nowhere and limits that cannot work."""
    issues: list[Issue] = []
    providers = _table(config, "providers")
    presets = _table(config, "modelPresets")
    defaults = _table(_table(config, "agents"), "defaults")

    if not presets:
        return [Issue(
            ERROR, "modelPresets",
            "Kein einziges Preset definiert.",
            "Presets anlegen, z.B. customize/config.json als Vorlage nutzen.",
        )]

    for name, preset in presets.items():
        where = f"modelPresets.{name}"
        if not isinstance(preset, Mapping):
            issues.append(Issue(ERROR, where, "Preset ist kein Objekt.",
                                "Preset als Objekt mit model/provider anlegen."))
            continue

        provider = preset.get("provider")
        model = preset.get("model")
        if not isinstance(provider, str) or not provider:
            issues.append(Issue(ERROR, f"{where}.provider", "Kein Provider angegeben.",
                                "Provider-Namen eintragen, z.B. \"anthropic\" oder \"ollama\"."))
        elif provider not in providers and provider not in KEYLESS_PROVIDERS:
            known = ", ".join(sorted(set(providers) | KEYLESS_PROVIDERS))
            issues.append(Issue(
                ERROR, f"{where}.provider",
                f"Provider '{provider}' ist nicht in providers definiert "
                "(und braucht dort auch keinen Key, wenn er lokal ist).",
                f"providers.{provider} anlegen oder einen vorhandenen Provider nutzen: {known}.",
            ))
        elif provider in providers:
            entry = providers.get(provider)
            if not isinstance(entry, Mapping):
                issues.append(Issue(
                    ERROR, f"{where}.provider",
                    f"providers.{provider} ist kein Objekt und kann keinen apiKey liefern.",
                    "Eintrag als Objekt anlegen, z.B. {\"apiKey\": \"${MY_KEY}\"}.",
                ))
            elif not entry.get("apiKey"):
                issues.append(Issue(
                    ERROR, f"{where}.provider",
                    f"providers.{provider} hat keinen apiKey.",
                    "apiKey als ${VAR} eintragen (Variablen werden global geprueft).",
                ))

        if isinstance(model, str) and isinstance(provider, str) and provider_prefix_mismatch(model, provider):
            issues.append(Issue(
                WARN, f"{where}.model",
                f"Modell '{model}' beginnt nicht mit dem Provider '{provider}'.",
                "Schreibweise provider/modell verwenden, damit die Route eindeutig ist.",
            ))

        issues.extend(_check_preset_limits(where, preset, model if isinstance(model, str) else ""))

    issues.extend(_check_selection(presets, defaults))
    return issues


def provider_prefix_mismatch(model: str, provider: str) -> bool:
    """Report a mismatch between the model prefix and the preset provider.

    ``custom`` providers may use arbitrary prefixes, so they are exempt.
    """
    if provider in {"custom"} or "/" not in model:
        return False
    prefix = model.split("/", 1)[0]
    return prefix != provider and prefix not in KEYLESS_PROVIDERS


def _check_preset_limits(where: str, preset: Mapping[str, Any], model: str) -> list[Issue]:
    issues: list[Issue] = []
    max_tokens = preset.get("maxTokens")
    window = preset.get("contextWindowTokens")

    if isinstance(max_tokens, int) and isinstance(window, int) and max_tokens >= window:
        issues.append(Issue(
            ERROR, f"{where}.maxTokens",
            f"maxTokens ({max_tokens}) passt nicht in contextWindowTokens ({window}).",
            f"maxTokens unter {window} setzen, z.B. {max(1024, window // 8)}.",
        ))

    effort = preset.get("reasoningEffort")
    if isinstance(effort, str) and effort.lower() not in KNOWN_EFFORTS:
        issues.append(Issue(
            WARN, f"{where}.reasoningEffort",
            f"'{effort}' ist unbekannt - der Provider faellt auf 4 096 Denk-Tokens zurueck.",
            f"Einen dieser Werte nutzen: {', '.join(KNOWN_EFFORTS)}.",
        ))
    elif isinstance(effort, str) and effort.lower() in {"xhigh", "max"} and model:
        if not is_adaptive_only(model):
            issues.append(Issue(
                WARN, f"{where}.reasoningEffort",
                f"'{effort}' ist bei {model} schlechter als 'high': "
                "das Budget-Mapping kennt nur low=1 024, medium=4 096, high=max(8 192, maxTokens) "
                "- alles andere faellt auf 4 096 zurueck.",
                "reasoningEffort auf \"high\" setzen (oder ein adaptives Modell verwenden).",
            ))
    elif isinstance(effort, str) and effort.lower() == "high" and isinstance(max_tokens, int):
        if model and not is_adaptive_only(model) and model.lower().startswith("anthropic/"):
            budget = max(8192, max_tokens)
            issues.append(Issue(
                INFO, f"{where}.reasoningEffort",
                f"effektives Denk-Budget: {budget} Tokens, effektive max_tokens: {budget + 4096}.",
            ))
    if isinstance(effort, str) and effort.lower() not in {"none", ""} and preset.get("temperature") is not None:
        issues.append(Issue(
            INFO, f"{where}.temperature",
            "Wird ignoriert, sobald Denken aktiv ist (der Provider setzt dann 1.0).",
        ))
    return issues


def _check_selection(presets: Mapping[str, Any], defaults: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    available = ", ".join(sorted(presets))

    primary = defaults.get("modelPreset")
    if isinstance(primary, str) and primary not in presets:
        issues.append(Issue(
            ERROR, "agents.defaults.modelPreset",
            f"Preset '{primary}' ist nicht in modelPresets definiert.",
            f"Auf eines dieser Presets zeigen: {available}.",
        ))

    fallbacks = defaults.get("fallbackModels")
    if isinstance(fallbacks, list):
        for index, name in enumerate(fallbacks):
            if isinstance(name, str) and name not in presets:
                issues.append(Issue(
                    ERROR, f"agents.defaults.fallbackModels[{index}]",
                    f"Preset '{name}' ist nicht in modelPresets definiert.",
                    f"Auf eines dieser Presets zeigen: {available}.",
                ))
            elif name == primary:
                issues.append(Issue(
                    WARN, f"agents.defaults.fallbackModels[{index}]",
                    f"Fallback '{name}' ist das Primaermodell - der Eintrag bewirkt nichts.",
                    "Entfernen oder auf ein anderes Preset zeigen.",
                ))
    return issues


def check_tools(config: Mapping[str, Any], defaults: Mapping[str, Any],
                presets: Mapping[str, Any]) -> list[Issue]:
    """Warn when the context window cannot hold what the tools produce."""
    issues: list[Issue] = []
    tools = _table(config, "tools")

    window: int | None = None
    primary = defaults.get("modelPreset")
    if isinstance(primary, str) and isinstance(presets.get(primary), Mapping):
        candidate = presets[primary].get("contextWindowTokens")
        if isinstance(candidate, int):
            window = candidate

    result_cap = defaults.get("maxToolResultChars")
    if isinstance(window, int) and isinstance(result_cap, int) and result_cap > window:
        issues.append(Issue(
            WARN, "agents.defaults.maxToolResultChars",
            f"Ein einzelnes Tool-Ergebnis darf {result_cap} Zeichen lang sein, "
            f"das Kontextfenster fasst aber nur {window} Tokens "
            "(ohne tiktoken zaehlt nanobot Bytes als Tokens).",
            f"Auf deutlich weniger setzen, z.B. {max(1024, window // 4)}.",
        ))

    heavy_tools = [
        name for name in ("cliApps", "my")
        if isinstance(tools.get(name), Mapping) and tools[name].get("enable") is True
    ]
    if heavy_tools and isinstance(window, int) and window <= 32768:
        issues.append(Issue(
            WARN, f"tools.{heavy_tools[0]}.enable",
            f"{' und '.join(heavy_tools)} sind aktiv, obwohl das Kontextfenster nur "
            f"{window} Tokens hat - die Tool-Schemas kosten allein ~12 000-20 000 Tokens.",
            "tools.cliApps.enable und tools.my.enable auf false setzen.",
        ))

    if tools.get("restrictToWorkspace") is False:
        exec_enabled = _table(tools, "exec").get("enable") is not False
        if exec_enabled:
            issues.append(Issue(
                INFO, "tools.restrictToWorkspace",
                "Der Agent darf ausserhalb des Workspace arbeiten (Datei- und Shell-Zugriff).",
                "Fuer mehr Isolation auf true setzen - kostet Reichweite, nicht Leistung.",
            ))
    return issues


def check_branding(defaults: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if not defaults.get("botName"):
        issues.append(Issue(
            INFO, "agents.defaults.botName",
            "Ohne botName zeigt die Oberflaeche 'nanobot' statt 'Nanobot von Alex'.",
        ))
    if not defaults.get("botIcon"):
        issues.append(Issue(
            INFO, "agents.defaults.botIcon",
            "Ohne botIcon fehlt das Symbol in den Clients.",
        ))
    return issues


def validate_config_text(
    text: str,
    *,
    name: str,
    keyless: bool = False,
    env: Mapping[str, str] | None = None,
) -> tuple[Mapping[str, Any] | None, list[Issue]]:
    """Validate one config document. Returns the parsed config (or None)."""
    environment = os.environ if env is None else env
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [Issue(
            ERROR, name,
            f"Kein gueltiges JSON: {exc.msg} (Zeile {exc.lineno}, Spalte {exc.colno}).",
            "Syntax korrigieren - eine Konfiguration mit Kommafehler startet nie.",
        )]
    if not isinstance(parsed, Mapping):
        return None, [Issue(
            ERROR, name, "Die Konfiguration ist kein JSON-Objekt.", "{} als Wurzel verwenden.",
        )]

    defaults = _table(_table(parsed, "agents"), "defaults")
    presets = _table(parsed, "modelPresets")
    issues: list[Issue] = []
    issues += check_placeholders(parsed, keyless=keyless, env=environment)
    issues += check_secrets(parsed)
    issues += check_presets(parsed)
    issues += check_tools(parsed, defaults, presets)
    issues += check_branding(defaults)
    return parsed, issues


def validate_path(path: Path, *, env: Mapping[str, str] | None = None) -> list[Issue]:
    if not path.exists():
        return [Issue(ERROR, str(path), "Datei nicht gefunden.", "Pfad pruefen.")]
    keyless = path.name.startswith("config.ollama")
    _, issues = validate_config_text(path.read_text(encoding="utf-8"), name=path.name,
                                     keyless=keyless, env=env)
    return issues


def _print_issues(issues: Sequence[Issue]) -> None:
    """Print findings, collapsing repeated notes that differ only in location."""
    grouped: dict[tuple[str, str, str], list[str]] = {}
    for issue in sorted(issues, key=lambda item: (_SEVERITY_ORDER[item.severity], item.where)):
        grouped.setdefault((issue.severity, issue.message, issue.fix), []).append(issue.where)
    for (severity, message, fix), locations in grouped.items():
        where = ", ".join(locations[:4])
        if len(locations) > 4:
            where += f", ... (+{len(locations) - 4})"
        print(f"  {severity:<5} {where}")
        print(f"        {message}")
        if fix:
            print(f"        Fix:  {fix}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prueft die customize-Konfigurationen vor dem Start.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit-Codes: 0 = in Ordnung, 1 = Befund, 2 = Aufruf-/Dateifehler.",
    )
    parser.add_argument("configs", nargs="*", type=Path,
                        help="Zu pruefende Dateien (Default: customize/config.json und config.ollama.json)")
    parser.add_argument("--strict", action="store_true",
                        help="Warnungen wie Fehler behandeln (fuer CI und Pre-Flight)")
    parser.add_argument("--json", dest="json_path", type=Path, default=None,
                        help="Bericht als JSON schreiben")
    parser.add_argument("--quiet", action="store_true",
                        help="Nur Zusammenfassung ausgeben")
    parser.add_argument("--self-test", action="store_true",
                        help="Die Pruefungen gegen eingebaute Fixtures testen")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    paths = list(args.configs) or [HERE / name for name in DEFAULT_CONFIGS]
    print()
    print("nanobot customize - Konfigurationspruefung")
    print(f"  Streng: {'ja (Warnungen zaehlen als Fehler)' if args.strict else 'nein'}")
    print()

    report: dict[str, Any] = {"strict": args.strict, "configs": [], "errors": 0,
                              "warnings": 0, "infos": 0}
    failed = False
    for path in paths:
        issues = validate_path(path)
        errors = [i for i in issues if i.severity == ERROR]
        warnings = [i for i in issues if i.severity == WARN]
        infos = [i for i in issues if i.severity == INFO]
        report["errors"] += len(errors)
        report["warnings"] += len(warnings)
        report["infos"] += len(infos)
        report["configs"].append({
            "path": str(path),
            "keyless": path.name.startswith("config.ollama"),
            "errors": len(errors),
            "warnings": len(warnings),
            "infos": len(infos),
            "issues": [
                {"severity": i.severity, "where": i.where, "message": i.message, "fix": i.fix}
                for i in issues
            ],
        })
        kind = "schluesselfrei" if path.name.startswith("config.ollama") else "mit Key"
        print(f"{path.name}  (Variante: {kind})")
        if args.quiet:
            print(f"  {len(errors)} Fehler, {len(warnings)} Warnungen, {len(infos)} Hinweise")
        elif not issues:
            print("  OK     keine Befunde")
        else:
            _print_issues(issues)
        print()
        if errors or (args.strict and warnings):
            failed = True

    report["ok"] = not failed
    print("-" * 62)
    print(f"Ergebnis: {len(paths)} Datei(en), {report['errors']} Fehler, "
          f"{report['warnings']} Warnung(en), {report['infos']} Hinweis(e)")

    if failed:
        print()
        print("Nicht installieren, solange Fehler offen sind.")
        if args.strict and not report["errors"]:
            print("(--strict: Warnungen zaehlen als Fehler.)")
    else:
        print("Konfiguration ist startklar.")
    print()

    if args.json_path:
        args.json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
        print(f"Bericht geschrieben: {args.json_path}")

    return 1 if failed else 0


# --------------------------------------------------------------------------
# Selbsttest: prueft den Pruefer gegen die dokumentierten Fallen.
# --------------------------------------------------------------------------

def _self_test_cases() -> list[tuple[str, dict[str, Any], dict[str, str], str, str, bool]]:
    """(name, config, env, erwartete_severity, erwarteter_fund, keyless)"""
    clean_keyless = {
        "modelPresets": {"local": {"model": "ollama/qwen3:8b", "provider": "ollama",
                                   "maxTokens": 8192, "contextWindowTokens": 32768,
                                   "reasoningEffort": "high"}},
        "agents": {"defaults": {"modelPreset": "local", "fallbackModels": [],
                                "maxToolResultChars": 4000, "botName": "Test",
                                "botIcon": "x"}},
        "tools": {"cliApps": {"enable": False}, "my": {"enable": False},
                  "restrictToWorkspace": True},
    }
    return [
        ("unsupported-default-syntax",
         {"providers": {"anthropic": {"apiKey": "${KEY:-fallback}"}}},
         {}, ERROR, "Default-Syntax", False),
        ("keyless-with-placeholder",
         {**clean_keyless, "providers": {"custom": {"apiKey": "${SOME_KEY}"}}},
         {}, ERROR, "schluesselfreie Variante", True),
        ("unset-placeholder-is-warning",
         {"providers": {"anthropic": {"apiKey": "${ANTHROPIC_API_KEY}"}}},
         {}, WARN, "nicht gesetzt", False),
        ("missing-preset",
         {**clean_keyless, "agents": {"defaults": {"modelPreset": "primary"}}},
         {}, ERROR, "nicht in modelPresets", False),
        ("unknown-fallback",
         {**clean_keyless, "agents": {"defaults": {"modelPreset": "local",
                                                   "fallbackModels": ["ghost"]}}},
         {}, ERROR, "nicht in modelPresets", False),
        ("maxTokens-outside-window",
         {**clean_keyless, "modelPresets": {"local": {"model": "ollama/qwen3:8b",
                                                      "provider": "ollama",
                                                      "maxTokens": 65536,
                                                      "contextWindowTokens": 32768}}},
         {}, ERROR, "passt nicht in contextWindowTokens", False),
        ("xhigh-is-worse-than-high",
         {"modelPresets": {"primary": {"model": "anthropic/claude-opus-4-5",
                                       "provider": "anthropic", "maxTokens": 16384,
                                       "reasoningEffort": "xhigh"}},
          "providers": {"anthropic": {"apiKey": "dummy"}},
          "agents": {"defaults": {"modelPreset": "primary", "botName": "T", "botIcon": "x"}}},
         {}, WARN, "schlechter als 'high'", False),
        ("literal-api-key",
         {"providers": {"anthropic": {"apiKey": "sk-ant-api03-REALKEYVALUE1234567890"}}},
         {}, ERROR, "Klartext", False),
        ("clean-keyless-config",
         clean_keyless, {}, None, "", True),
    ]


def run_self_test() -> int:
    """Prove the checks fire on the documented traps - and stay quiet when clean."""
    print()
    print("nanobot customize - Selbsttest des Pruefers")
    print()
    failures = 0
    for name, config, env, severity, needle, keyless in _self_test_cases():
        text = json.dumps(config, ensure_ascii=False)
        _, issues = validate_config_text(
            text, name=name, keyless=keyless, env={**os.environ, **env} if env else {},
        )
        if severity is None:
            bad = [i for i in issues if i.severity != INFO]
            ok = not bad
            detail = "keine Fehler, keine Warnungen" if ok else f"{bad[0].severity}: {bad[0].message}"
        else:
            hit = next((i for i in issues
                        if i.severity == severity and needle.lower() in i.message.lower()), None)
            ok = hit is not None
            detail = hit.message if hit else f"erwartet {severity} mit '{needle}'"
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:28s} {detail}")
        if not ok:
            failures += 1
    print()
    print(f"Selbsttest: {len(_self_test_cases()) - failures}/{len(_self_test_cases())} bestanden")
    print()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
