# Nanobot von Alex — Schnellstart in 3 Minuten

Du willst nur mit diesem Fork chatten und nicht die ganze Upstream-Doku lesen?
Dann bist du hier richtig. Für die englische Upstream-Dokumentation: [`docs/README.md`](./README.md).

## Was ist das hier?

Nanobot von Alex ist ein selbst gehosteter AI-Agent für dein Terminal. Er rechnet,
liest und schreibt Dateien, führt Code aus und sucht im Web. Alles läuft auf deinem
Rechner; das Denken liefert Anthropic (stark) oder Ollama (lokal, kostenlos, schwächer).

**Ohne Modell bleibt der Bot bei 0 %** — nicht der Code ist dann das Problem, sondern
die fehlende Anbindung.

## Installation

### Variante A — Anthropic API (stärker)

```bash
git clone https://github.com/ohZugghkkn-tech/empty-repo.git
cd empty-repo
uv sync                              # ohne uv: python3 -m venv .venv && .venv/bin/pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...  # Key anlegen: https://console.anthropic.com
./customize/apply.sh                 # wählt automatisch die Key-Variante
```

### Variante B — Ollama (kostenlos, lokal)

```bash
git clone https://github.com/ohZugghkkn-tech/empty-repo.git
cd empty-repo
uv sync                              # ohne uv: python3 -m venv .venv && .venv/bin/pip install -e .
./customize/apply.sh --variant ollama
ollama pull qwen3:8b                 # Ollama installieren: https://ollama.com/download
```

`apply.sh` überschreibt nichts: Vorhandenes wird nach `*.bak-<Zeitstempel>` gesichert.
Erst ansehen, dann schreiben: `./customize/apply.sh --dry-run`.

## Los geht's

```bash
.venv/bin/nanobot status                    # muss "provider/model configuration is ready" zeigen
.venv/bin/nanobot                           # Terminal-Chat: lostippen, /exit beendet
.venv/bin/nanobot agent -m "Was ist 2+2?"   # ein einzelner Befehl
```

Im Chat wechselt `/model <name>` das Preset, `/help` zeigt alle Befehle.

## Erste Messung

```bash
python customize/eval/run_eval.py           # 10 Aufgaben; Exit-Code 0 = alles bestanden
```

Ohne Modell: 0/10. Mit angebundenem Modell steigt der Wert — das ist deine Zahl,
kein Gefühl. Vorher prüfen lässt sich die Konfiguration mit:

```bash
python customize/validate_config.py --strict
```

## Wenn es klemmt

| Meldung | Ursache | Lösung |
|---|---|---|
| `Environment variable 'ANTHROPIC_API_KEY' is not set` | Ein `${VAR}`-Platzhalter hat keinen Wert | `export ANTHROPIC_API_KEY=...` oder `./customize/apply.sh --variant ollama` |
| `No provider is configured` | Keine passende Konfiguration installiert | `./customize/apply.sh` |
| `ContextWindowExceededError` | Kontextfenster zu klein für Prompt und Tool-Schemas | größeres Modell, größeres `contextWindowTokens` oder Variante B |
| Antwort ist nur ein Setup-Text | Es ist kein Modell angebunden | `./customize/apply.sh`, dann Key prüfen |

## Weiterlesen

| Thema | Datei |
|---|---|
| Presets, Messwerte, Denk-Budgets | [`customize/README.md`](../customize/README.md) |
| Änderungen an diesem Fork | [`CHANGELOG.md`](../CHANGELOG.md) |
| Browser-Oberfläche | [`docs/webui.md`](./webui.md) (Quell-Checkout baut das Frontend beim ersten Start) |
| Upstream-Themen | [`docs/README.md`](./README.md), [nanobot.wiki](https://nanobot.wiki) |
