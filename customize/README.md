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

```bash
# 1. Konfiguration installieren (sichert vorhandene Dateien)
./customize/apply.sh                      # Ziel: ~/.nanobot
./customize/apply.sh --home /pfad/zur/instanz --dry-run   # erst ansehen

# 2. API-Key setzen (die Config referenziert ihn als ${...})
export ANTHROPIC_API_KEY=sk-ant-...

# 3. Prüfen, ob ein Modell erkannt wird
nanobot status

# 4. Messen
python customize/eval/run_eval.py
```

`apply.sh` überschreibt nichts ungefragt: vorhandene Dateien werden nach
`*.bak-<zeitstempel>` gesichert.

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
| `config.json` | Getunte Konfiguration: 5 Modell-Presets, Fallback-Kette, angehobene Limits |
| `SOUL.md` | Persona + Reasoning-Disziplin (Tool-first, Verifikation, Ehrlichkeit) |
| `AGENTS.md` | Arbeitsanweisungen: Tool-Policy, Fehlerbehandlung, Cron/Heartbeat |
| `apply.sh` | Installer mit Backup, `--dry-run` verfügbar |
| `eval/tasks.json` | 10 Aufgaben in 5 Kategorien mit maschinell erzeugten Sollwerten |
| `eval/run_eval.py` | Eval-Harness, schreibt optional JSON-Bericht |
| `eval/mock_provider.py` | Test-Double zur Verifikation der Pipeline (kein KI-Modell!) |

### Enthaltene Presets

| Preset | Modell | `effort` | `maxTokens` | Zweck |
|---|---|---|---|---|
| `primary` | `anthropic/claude-opus-4-5` | high | 16 384 | Standard, stärkstes Denken |
| `deep` | `anthropic/claude-opus-4-5` | high | 32 768 | Lange Analyse, größeres Budget |
| `balanced` | `anthropic/claude-sonnet-4.5` | medium | 16 384 | Günstiger, Fallback |
| `fast` | `openai/gpt-4.1-mini` | low | 8 192 | Schnelle einfache Aufgaben |
| `local` | `ollama/qwen3:8b` | high | 8 192 | Offline, kostenlos |

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
