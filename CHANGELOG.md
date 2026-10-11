# Changelog — Nanobot von Alex

Alle nennenswerten Änderungen **dieses Forks**. Format nach
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung siehe unten.

Dieser Changelog beschreibt nur die Fork-Ebene: `customize/`, Branding, Fork-Doku
und die Fork-CI. Die Upstream-Änderungen stehen in
[`docs/release-archive.md`](./docs/release-archive.md) und in den
[HKUDS/nanobot Releases](https://github.com/HKUDS/nanobot/releases).

---

## Fork-Tracking

| Feld | Wert |
|---|---|
| Upstream | [HKUDS/nanobot](https://github.com/HKUDS/nanobot) (MIT) |
| Fork | `ohZugghkkn-tech/empty-repo` |
| Upstream-Branch | `main` |
| Upstream-Basis | Version **0.3.5** (Release 2026-09-15, siehe `docs/release-archive.md`) |
| Stand | 2026-10-11 |

> **Zur Historie:** In diesem Fork liegt die Upstream-Historie als ein
> zusammengefasster Commit vor (`33e574f`). Die Basis wird deshalb über die
> Upstream-**Version** identifiziert, nicht über einen Upstream-Commit-Hash.
> Bei jedem Upstream-Update wird die Zeile „Upstream-Basis“ oben angepasst und
> hier ein Eintrag ergänzt.

### Fork-eigene Pfade

| Pfad | Herkunft | Bei einem Upstream-Merge |
|---|---|---|
| `customize/**` | Fork | Fork-Version behalten — hier liegt der gesamte Mehrwert |
| `.github/workflows/customize-ci.yml` | Fork | behalten (kein Upstream-Pendant) |
| `docs/FORK_QUICKSTART.md`, `CHANGELOG.md` | Fork | behalten |
| `README.md` | Upstream + Fork-Banner | Banner oben (deutsch) erhalten, Rest von Upstream übernehmen |
| `.github/workflows/ci.yml` | Upstream | Upstream übernehmen, danach den `customize/*`-Zweig erneut einhängen |
| `pyproject.toml` | Upstream + Fork-Metadaten | Version und Abhängigkeiten von Upstream, `name`/`description` behalten |

### Upstream übernehmen

```bash
git remote add upstream https://github.com/HKUDS/nanobot.git   # einmalig
git fetch upstream
git merge upstream/main
python customize/validate_config.py --strict   # Fork-Konfiguration prüfen
python customize/check_version.py              # Version ↔ Changelog prüfen
```

Nach dem Merge: Upstream-Version in der Tracking-Tabelle oben aktualisieren und
einen Eintrag unter „Upstream-Basis aktualisiert“ ergänzen.

## Versionierung

- `pyproject.toml` → `project.version` folgt **exakt** der Upstream-Version
  (aktuell `0.3.5`). Grund: `docs/releasing.md` und `scripts/build_tui_wheels.py`
  prüfen diese Version, und PyPI lehnt lokale Versionszusätze wie
  `0.3.5+fork.1` ab.
- Fork-Releases erhalten Git-Tags der Form `v0.3.5-fork.1` und hier einen
  Abschnitt `## [0.3.5-fork.1] - JJJJ-MM-TT`.
- Gezählt wird pro Fork-Release: Nach dem Tag `v0.3.5-fork.1` folgt
  `v0.3.5-fork.2`; steigt die Upstream-Version, beginnt die Zählung neu
  (`v0.3.6-fork.1`).
- Prüfbar: `python customize/check_version.py` vergleicht die neueste
  freigegebene Version in dieser Datei mit `pyproject.toml` und läuft in der CI.

---

## [Unreleased]

### Hinzugefügt

- `customize/validate_config.py` — Konfigurationsprüfer für die Fallen, die sonst
  erst beim Start auffallen: nicht gesetzte `${VAR}`-Platzhalter (global, wie
  nanobot sie prüft), nicht unterstützte `${VAR:-fallback}`-Syntax,
  Platzhalter in der schlüsselfreien Variante, Presets/Fallbacks ohne Ziel,
  `maxTokens` ≥ Kontextfenster, `xhigh`/`max` bei manuellen Denk-Budgets,
  Klartext-Schlüssel in versionierten Dateien. Mit `--strict`, `--json` und
  `--self-test` (9 eingebaute Fälle).
- `.github/workflows/customize-ci.yml` — Fork-CI ohne API-Key: Selbsttest und
  Lauf des Prüfers, `bash -n` + ShellCheck, Ruff für `customize/`, Eval-Smoke-Test
  gegen den Mock-Provider (erwartet 10/10) und Installations-Smoke-Test für
  `apply.sh`.
- `customize/check_version.py` — prüft Version und Fork-Tracking in diesem
  Changelog gegen `pyproject.toml`.
- `docs/FORK_QUICKSTART.md` — Schnellstart auf Deutsch für Nutzer:innen, die nur
  diesen Fork verwenden wollen.

### Geändert

- `customize/apply.sh` — Variante `auto` (Key gesetzt → Key-Variante, sonst
  Ollama, sonst Key-Variante mit deutlicher Warnung), Prüfung der Quelldatei vor
  dem Schreiben, echter Dry-Run-Plan (Aktionen, Sicherungen, Prüfergebnis,
  Schreibrechte), verständliche Fehlermeldungen, Exit-Codes 0/1/2.
- `customize/config.ollama.json` — `maxToolResultChars` von 40000 auf 8192
  gesenkt: Ein einzelnes Tool-Ergebnis konnte das 32k-Kontextfenster sprengen
  (ohne `tiktoken` zählt nanobot Bytes als Tokens).
- `customize/eval/mock_provider.py` — ungenutzte Variable entfernt (Ruff).
- `.github/workflows/ci.yml` — die Fork-Ebene (`customize/**`, `CHANGELOG.md`,
  `docs/FORK_QUICKSTART.md`) läuft nicht mehr durch die Upstream-Jobs; sie wird
  von `customize-ci.yml` abgedeckt.
- `README.md` — Fork-Banner verlinkt Schnellstart, Prüfer und Changelog.
- `docs/README.md` — Hinweis auf den deutschen Fork-Schnellstart.
- `customize/README.md` — beschreibt `--variant auto`, den Prüfer und den
  gesenkten Tool-Ergebnis-Deckel.

## [0.3.5-fork.1] - 2026-10-11

Erste getrackte Fork-Version: die getunte Ebene auf Upstream-Basis 0.3.5.

### Hinzugefügt

- `customize/config.json` (fünf Presets, Fallback-Kette, angehobene Limits) und
  `customize/config.ollama.json` (schlüsselfrei, für lokales Ollama).
- `customize/SOUL.md` und `customize/AGENTS.md` — Tool-First-Disziplin:
  Rechnen über `exec`, Fakten über `web_search`, Dateien über `read_file`.
- `customize/apply.sh` — Installer mit Sicherung, `--dry-run` und
  `--variant anthropic|ollama`.
- `customize/eval/` — Eval-Suite (10 Aufgaben in 5 Kategorien) mit
  `mock_provider.py` als deterministischem Test-Double; Messwerte: 0/10 ohne
  Modell, 10/10 mit funktionierender Pipeline.
- `customize/README.md` — Messwerte, Stolperfallen und Grenzen der Konfiguration.
- Branding: Distributionsname `nanobot-von-alex`, Anzeigename „Nanobot von Alex“,
  deutscher Fork-Banner im README.
