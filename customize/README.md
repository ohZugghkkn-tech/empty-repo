# customize — nanobot auf maximale Leistung bringen

Dieses Verzeichnis enthält eine getunte, verifizierte Konfiguration für nanobot,
eine Prompt-Ebene mit Tool-Disziplin und eine Eval-Suite, die „der Bot ist zu dumm"
in eine Zahl verwandelt.

Alles hier wurde **gemessen**, nicht geraten. Die Zahlen unten stammen aus Läufen
gegen dieses Repository.

---

## Der wichtigste Punkt zuerst

nanobot ist ein **Agent-Runtime**, kein Modell. Ohne konfiguriertes Modell antwortet
kein Denken, sondern ein Stub. Messergebnis gegen dieselbe Eval-Suite:

| Zustand | Ergebnis | Was passiert |
|---|---|---|
| Kein Modell konfiguriert | **0 / 10 (0 %)** | `UnconfiguredProvider` gibt auf *jede* Frage denselben Setup-Text zurück |
| Modell konfiguriert | **10 / 10 (100 %)** | Voller Agent-Loop inklusive Tool-Ausführung |

Der Unterschied zwischen „dumm" und „kompetent" liegt in diesem Projekt **nicht am Code**.
Er liegt daran, ob ein Modell angeschlossen ist. Diese Konfiguration holt aus einem
angeschlossenen Modell das Maximum heraus — sie ersetzt es nicht.

Nachweis des 0-%-Falls: zehn verschiedene Fragetypen (Mathe, Smalltalk, Wissen, Code,
Logik, Meta) ergeben **einen einzigen Antwort-Hash**.

Nachweis des 100-%-Falls (Mock-Provider, siehe unten):

```
🐈 nanobot
  ↳ $ python3 -c "print(2481 + 837382)"
ERGEBNIS: 839863
```

Das ist die komplette Kette: `config.json` → Provider-Route → Agent-Loop →
`exec`-Tool → Antwort.

---

## Schnellstart

Ein Befehl reicht — `apply.sh` wählt die Variante selbst:

```bash
./customize/apply.sh
```

Die Auswahl (`--variant auto`, Standard) folgt drei Regeln: Ist die
Umgebungsvariable der Key-Variante gesetzt, wird `config.json` installiert. Sonst:
antwortet Ollama lokal, wird die schlüsselfreie Variante installiert. Sonst wird
die Key-Variante installiert — mit deutlicher Warnung, dass sie erst nach dem
Export startet.

Erzwingen lässt sich jede Variante:

```bash
# A) Mit API-Key (starkstes Denken)
export ANTHROPIC_API_KEY=sk-ant-...
./customize/apply.sh --variant anthropic   # installiert config.json

# B) Schlüsselfrei über lokales Ollama (kostenlos, schwächer)
./customize/apply.sh --variant ollama      # installiert config.ollama.json
ollama pull qwen3:8b

# Immer danach:
nanobot status                             # muss "provider/model configuration is ready" zeigen
python customize/eval/run_eval.py          # deine Zahl
```

Erst ansehen, ohne zu schreiben — der Dry Run zeigt den echten Plan inklusive
Prüfergebnis, Sicherungen und Schreibrechten:

```bash
./customize/apply.sh --home /pfad --dry-run
```

`apply.sh` überschreibt nichts ungefragt: vorhandene Dateien werden nach
`*.bak-<zeitstempel>` gesichert, identische Dateien bleiben unangetastet. Vor dem
Schreiben läuft der Konfigurationsprüfer (`validate_config.py`); erst bei Fehlern
bricht die Installation ab (`--no-validate` überspringt die Prüfung).

---

## Prüfen statt starten: `validate_config.py`

Der Prüfer findet die Fehler, die sonst erst beim Start auffallen — allen voran
die drei Fallen weiter unten. Er braucht **keine** Bibliotheken außer der
Standardbibliothek und keinen API-Key:

```bash
python customize/validate_config.py                 # beide Varianten
python customize/validate_config.py --strict        # Warnungen zählen als Fehler
python customize/validate_config.py --self-test     # 9 eingebaute Fallen
python customize/validate_config.py --json bericht.json
```

Geprüft wird:

| Prüfung | Warum |
|---|---|
| `${VAR}`-Platzhalter, global über alle Strings | Ein nicht gesetzter Wert blockiert den Start komplett |
| `${VAR:-fallback}` | Diese Syntax gibt es nicht — nanobot kennt nur `${VAR}` |
| Platzhalter in `config.ollama.json` | Die schlüsselfreie Variante muss ohne Umgebung starten |
| `modelPreset` / `fallbackModels` ohne Ziel | Preset-Tippfehler fallen sonst erst im Betrieb auf |
| Preset-Provider ohne `apiKey` | Häufigster Konfigurationsfehler nach dem Umbau auf einen anderen Anbieter |
| `maxTokens` ≥ `contextWindowTokens` | Kann nie funktionieren |
| `xhigh` / `max` bei manuellen Denk-Budgets | Sind dort **schlechter** als `high` (siehe Messwerte) |
| Klartext-Schlüssel (`sk-…`) in der Datei | Die Config liegt im Git — Keys gehören dort nicht hinein |

Exit-Codes: `0` = startklar, `1` = Befund, `2` = Aufruf- oder Dateifehler. Die
Fork-CI (`.github/workflows/customize-ci.yml`) lässt den Prüfer samt Selbsttest
bei jeder Änderung an `customize/` laufen.

---

## Stolperfalle: `${VAR}` ist strikt **und global**

nanobot prüft **jeden String** in der Config auf das Muster `${NAME}` und bricht mit
`ConfigLoadError` ab, wenn die Variable nicht gesetzt ist
(`nanobot/config/loader.py:194` und `:295`). Zwei Konsequenzen, die man nicht erwartet:

1. **Es gibt keine Default-Syntax.** `${VAR:-fallback}` funktioniert nicht. Das Muster
   ist `\$\{([A-Za-z_][A-Za-z0-9_]*)\}` — entweder die Variable ist gesetzt oder es
   gibt einen Fehler.

2. **Die Prüfung ist global, nicht pro Preset.** Ein Eintrag
   `providers.anthropic.apiKey = "${ANTHROPIC_API_KEY}"` blockiert den Start **auch
   dann**, wenn das aktive Preset Ollama ist und gar keinen Key braucht.

3. **Auch Kommentar-Felder werden geprüft.** Ein Hinweistext, der wörtlich
   `${MEINE_VAR}` enthält, löst denselben Fehler aus. Getestet und verifiziert.

Deshalb enthält `config.json` **genau einen** Platzhalter (`ANTHROPIC_API_KEY`) und
`config.ollama.json` **keinen einzigen**. Wer einen anderen Anbieter nutzt, ersetzt den
`providers`-Block — nicht ergänzt ihn.

**Provider-Keys kommen nicht aus der Umgebung.** nanobot liest `ANTHROPIC_API_KEY` /
`OPENAI_API_KEY` **nicht** automatisch; das `env_key`-Feld in der Provider-Registry wird
nur für Sprachtranskription verwendet. Der Key muss in der Config stehen — wörtlich oder
als `${...}`-Platzhalter. Verifiziert: `ANTHROPIC_API_KEY=... nanobot status` meldet ohne
Config-Eintrag weiterhin „No API key configured".

---

## Kontext-Budget (gemessen)

Der System-Prompt ist nicht kostenlos. Gemessen für einen CLI-Turn:

| Bestandteil | Bytes |
|---|---|
| System-Prompt mit Upstream-Defaults | 3 979 |
| System-Prompt mit `customize/SOUL.md` + `AGENTS.md` | 11 309 |
| Zuwachs durch diese Prompts | **+7 330 (+184 %)** |
| Tool-Schemas (13–25 Tools, je nach Konfiguration) | ~12 000–20 000 |

Die Tool-Schemas sind also **teurer als der Prompt** — mit Abstand. Das ist der
eigentliche Grund, warum kleine Kontextfenster überlaufen.

### Achtung: der Schätzer zählt Bytes, nicht Tokens

Wenn `tiktoken` nicht verfügbar ist (z. B. offline, denn das Encoding wird von einem
OpenAI-Host nachgeladen), fällt nanobot auf eine **Byte-Heuristik** zurück
(`nanobot/utils/helpers.py:828`). Die zählt 1 „Token" pro Byte und überschätzt damit
grob. Folge: ein nominelles 32k-Fenster kann rechnerisch bei ~23 500 „Tokens"
Eingabebudget landen, während der echte Tokenverbrauch viel niedriger wäre.

Praktisch heißt das: **lokale Modelle brauchen ein größeres Fenster als man denkt.**
Bei Ollama muss das Fenster zusätzlich serverseitig gesetzt werden
(`OLLAMA_CONTEXT_LENGTH` bzw. `num_ctx`) — `contextWindowTokens` in der Config
beschreibt nur, was nanobot annimmt.

Wenn der Start mit `ContextWindowExceededError` abbricht, ist der Weg nach vorn:
`contextWindowTokens` erhöhen **oder** den Tool-Umfang verkleinern. Die
Keyless-Variante deaktiviert deshalb `cliApps` und `my` (`tools.cliApps.enable: false`,
`tools.my.enable: false`) — bei kleinen Modellen zählt jedes Kilobyte Schema.

Aus demselben Grund deckelt die Keyless-Variante einzelne Tool-Ergebnisse auf
`maxToolResultChars: 8192`. Vorher (40000) konnte **ein einziger** Befehl wie
`cat große-datei` das 32k-Fenster allein sprengen — der Lauf brach dann mit
`ContextWindowExceededError` ab, obwohl die Konfiguration sonst stimmte. Der
Prüfer meldet diese Kombination als Warnung (`--strict` macht sie zum Fehler).

---

## Messwerte: `reasoningEffort` — hier geht naive Einstellung schief

Verifiziert durch direkte Payload-Erzeugung über
`AnthropicProvider._build_kwargs` (siehe `nanobot/providers/anthropic_provider.py:651`).

Für Modelle mit **manuellen Denk-Budgets** (Klasse `claude-opus-4-5`):

| `reasoningEffort` | Denk-Budget (Tokens) | effektive `max_tokens` |
|---|---|---|
| `low` | 1 024 | 8 192 |
| `medium` | 4 096 | 8 192 |
| **`high`** | **8 192** | 12 288 |
| **`xhigh`** | **4 096** ← schlechter als `high` | 8 192 |
| **`max`** | **4 096** ← schlechter als `high` | 8 192 |
| `adaptive` | adaptiv (Modell entscheidet) | 8 192 |
| `none` | aus | 8 192 |

**Kernaussage:** `budget_map = {"low": 1024, "medium": 4096, "high": max(8192, max_tokens)}`.
Unbekannte Werte fallen auf `budget_map.get(wert, 4096)` zurück. Wer „möglichst schlau"
will und `xhigh` oder `max` einträgt, bekommt auf diesen Modellen **die Hälfte** des
Budgets von `high`. Die intuitive Einstellung ist die falsche.

### `maxTokens` steuert das Denk-Budget mit

Bei `effort=high` gilt `budget = max(8192, maxTokens)`:

| `maxTokens` | Denk-Budget | effektive `max_tokens` |
|---|---|---|
| 4 096 | 8 192 | 12 288 |
| 8 192 | 8 192 | 12 288 |
| **16 384** | **16 384** | 20 480 |
| 32 768 | 32 768 | 36 864 |

Deshalb setzt diese Konfiguration `maxTokens: 16384` bei `effort: "high"` — das
verdoppelt das Denk-Budget gegenüber dem Standard, ohne das Ausgabelimit zu sprengen.

### Neuere Modelle verhalten sich anders

Ab `opus 4.7` / `sonnet 5.0` (`_ADAPTIVE_ONLY_MIN_VERSIONS`) entfallen manuelle Budgets.
Dort wird `effort` unverändert als `output_config.effort` durchgereicht:

| `reasoningEffort` | Wirkung |
|---|---|
| `low` / `high` / `xhigh` / `max` | wird 1:1 übergeben — hier funktioniert `xhigh`/`max` |

### Temperatur wird überschrieben

Sobald Denken aktiv ist, setzt der Anthropic-Provider `temperature = 1.0` und ignoriert
den konfigurierten Wert. Das `temperature: 0.1` in der Config wirkt also **nur** ohne
Denken. Wer deterministische Ausgaben braucht, darf Denken nicht anschalten — für
Rechen- und Analyseaufgaben ist Denken aber der größere Hebel.

---

## Warum `SOUL.md` und `AGENTS.md` den größten praktischen Effekt haben

Ein Modell rechnet nicht. Es sagt wahrscheinliche Textfortsetzungen voraus. Deshalb
ist die wirksame Strategie nicht „ein schlauere Modell", sondern: **exaktes Rechnen an
ein Werkzeug abgeben.**

`customize/SOUL.md` und `customize/AGENTS.md` etablieren genau das als harte Regel:

- Arithmetik, Prozente, Datumsrechnung, Zählungen → immer über `exec` mit Python
- veränderliche Fakten → immer über `web_search` / `web_fetch`
- Dateiinhalte → immer über `read_file`, nie aus dem Gedächtnis

Der Unterschied ist messbar: dieselbe Aufgabe („2481 + 837382") scheitert bei einem
schwachen Modell aus dem Kopf und gelingt zuverlässig über das Tool.

---

## Dateien

| Datei | Zweck |
|---|---|
| `config.json` | Variante mit API-Key: 5 Presets, Fallback-Kette, angehobene Limits |
| `config.ollama.json` | Schlüsselfreie Variante für lokales Ollama, ohne jeden Platzhalter |
| `SOUL.md` | Persona + Reasoning-Disziplin (Tool-first, Verifikation, Ehrlichkeit) |
| `AGENTS.md` | Arbeitsanweisungen: Tool-Policy, Fehlerbehandlung, Cron/Heartbeat |
| `apply.sh` | Installer: `--variant auto\|anthropic\|ollama`, `--dry-run`, Backup, Prüfung vor dem Schreiben |
| `validate_config.py` | Konfigurationsprüfer mit `--strict`, `--json` und `--self-test` |
| `check_version.py` | Prüft Fork-Version und Upstream-Basis (`CHANGELOG.md` ↔ `pyproject.toml`) |
| `eval/tasks.json` | 10 Aufgaben in 5 Kategorien mit maschinell erzeugten Sollwerten |
| `eval/run_eval.py` | Eval-Harness, schreibt optional JSON-Bericht |
| `eval/mock_provider.py` | Test-Double zur Verifikation der Pipeline (kein KI-Modell!) |

Zur Fork-Ebene gehören außerdem: [`docs/FORK_QUICKSTART.md`](../docs/FORK_QUICKSTART.md)
(deutscher Schnellstart), [`CHANGELOG.md`](../CHANGELOG.md) (Fork-Tracking und
Versionierung) und [`.github/workflows/customize-ci.yml`](../.github/workflows/customize-ci.yml)
(CI-Gate ohne API-Key: Selbsttest, Prüfer, ShellCheck, Ruff, Eval-Smoke-Test
gegen den Mock-Provider, Installer-Smoke-Test).

### Name dieses Projekts

Projektname: **Nanobot von Alex via Arena.ai**.

| Ort | Wert |
|---|---|
| Distributionsname (`pip show`) | `nanobot-von-alex` |
| Anzeigename im CLI | `Nanobot von Alex` (`agents.defaults.botName`) |
| Import-Paket | `nanobot` — **bewusst unverändert** |

Warum der Distributionsname kürzer ist: PEP 508 erlaubt keine Leerzeichen und Punkte in
Paketnamen — `pip install` lehnt `Nanobot von Alex via Arena.ai` ab (getestet). Der
Anzeigename bleibt exakt wie gewünscht.

Das Import-Paket `nanobot/` wurde **absichtlich nicht** umbenannt: 855 Python-Dateien
importieren es, und jede Umbenennung würde das gesamte Projekt unbrauchbar machen und
jedes Upstream-Update zu einem Merge-Konflikt. Der Name im Code ist eine interne
Adresse, keine Marke.

### Enthaltene Presets

`config.json` (Variante mit Key):

| Preset | Modell | `effort` | `maxTokens` | Zweck |
|---|---|---|---|---|
| `primary` | `anthropic/claude-opus-4-5` | high | 16 384 | Standard, stärkstes Denken |
| `deep` | `anthropic/claude-opus-4-5` | high | 32 768 | Lange Analyse, größeres Budget |
| `balanced` | `anthropic/claude-sonnet-4.5` | medium | 16 384 | Günstiger, Fallback |
| `fast` | `anthropic/claude-sonnet-4.5` | low | 8 192 | Schnelle einfache Aufgaben |
| `local` | `ollama/qwen3:8b` | high | 8 192 | Offline, kostenlos |

Alle vier Cloud-Presets nutzen **denselben** Anbieter. Grund: die `${VAR}`-Prüfung ist
global, ein zweiter Anbieter würde einen zweiten gesetzten Key erzwingen — und damit den
Start blockieren, sobald er fehlt.

`config.ollama.json` (schlüsselfrei):

| Preset | Modell | `effort` | `contextWindowTokens` | Zweck |
|---|---|---|---|---|
| `local` | `ollama/qwen3:8b` | high | 32 768 | Standard, läuft auf 8–16 GB RAM |
| `localBig` | `ollama/qwen3:32b` | high | 65 536 | Deutlich stärker, braucht ~24 GB RAM |

Die Ollama-Tags sind Beispiele. Prüfe mit `ollama list`, welche Modelle du tatsächlich
hast, und passe `model` im Preset an.

Umschalten im Chat mit `/model <name>`. Die Fallback-Kette (`balanced`) greift, wenn
das Primärmodell nicht erreichbar ist.

---

## Eval-Suite benutzen

```bash
python customize/eval/run_eval.py                      # ~/.nanobot
python customize/eval/run_eval.py --home /pfad         # eigene Instanz
python customize/eval/run_eval.py --only rechnen       # eine Kategorie
python customize/eval/run_eval.py --json bericht.json  # maschinenlesbar
```

Exit-Code `0` = alles bestanden, `1` = mindestens ein Fehlschlag. Damit ist es in CI
oder als Vorher-Nachher-Vergleich nutzbar.

Kategorien: `rechnen`, `kontrolle`, `anweisung`, `ehrlichkeit`, `meta`.

Die Sollwerte in `tasks.json` wurden **maschinell erzeugt** (Python), nicht geschätzt:

| Aufgabe | Erwartung |
|---|---|
| 2481 + 837382 | 839863 |
| (17 × 23) − (144 / 12) | 379 |
| 987654321 × 123456789 | 121932631112635269 |
| 17,5 % von 24380 | 4266.5 |
| 2⁶⁴ | 18446744073709551616 |
| ggT(1071, 462) | 21 |

Die Aufgabe `math-large` ist bewusst so gewählt, dass sie **kein** Modell zuverlässig
im Kopf löst. Wer sie besteht, hat Werkzeuge benutzt.

---

## Die Pipeline ohne Modell verifizieren

`eval/mock_provider.py` ist ein OpenAI-kompatibles Test-Double. Es ersetzt die
Sprachmodell-Schicht durch feste Regeln und beweist damit, dass die *Mechanik*
funktioniert — unabhängig davon, ob ein Modell verfügbar ist.

```bash
# Terminal 1
python customize/eval/mock_provider.py --port 8099

# Terminal 2 - Instanz mit Mock-Provider
mkdir -p /tmp/nb-mock/workspace
cat > /tmp/nb-mock/config.json <<'JSON'
{
  "providers": { "custom": { "apiBase": "http://127.0.0.1:8099/v1" } },
  "modelPresets": { "mock": { "model": "mock/solver", "provider": "custom" } },
  "agents": { "defaults": { "modelPreset": "mock" } }
}
JSON

NANOBOT_BIN=.venv/bin/nanobot python customize/eval/run_eval.py --home /tmp/nb-mock
```

Erwartetes Ergebnis: **10 / 10 (100 %)**.

> **Klarstellung:** Der Mock ist **keine** künstliche Intelligenz. Er ist ein
> deterministisches Testinstrument. Ein hoher Wert gegen den Mock bedeutet
> „die Pipeline funktioniert", nicht „der Bot ist schlau".

---

## Grenzen — was diese Konfiguration nicht leistet

- Sie erzeugt **keine** Intelligenz. Ohne Modell bleibt es bei 0 %.
- Sie hebt die **Fähigkeitsgrenze** des gewählten Modells nicht an. Ein 3B-Modell
  bleibt ein 3B-Modell, auch mit `effort: high`.
- Die Presets enthalten Modellnamen, die sich ändern können. Prüfe mit
  `nanobot status` oder in der WebUI unter **Settings → Models**, ob sie an deinem
  Endpoint noch gültig sind.
- Die Fallbacks `balanced` und `fast` brauchen eigene Zugänge. Fehlt der Key, schlägt
  nur der Fallback fehl, nicht das Primärmodell.
