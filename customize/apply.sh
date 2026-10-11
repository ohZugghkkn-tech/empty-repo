#!/usr/bin/env bash
# Installiert die getunte "Nanobot von Alex"-Konfiguration in eine nanobot-Instanz.
#
# Verwendung:
#   ./customize/apply.sh                    # Variante automatisch waehlen (empfohlen)
#   ./customize/apply.sh --variant anthropic   # Key-Variante erzwingen
#   ./customize/apply.sh --variant ollama      # schluesselfreie Variante erzwingen
#   ./customize/apply.sh --home /pfad       # eigenes Instanzverzeichnis
#   ./customize/apply.sh --dry-run          # Plan zeigen, nichts schreiben
#   ./customize/apply.sh --no-validate      # Konfigurationspruefung ueberspringen
#   ./customize/apply.sh --quiet            # weniger Ausgabe
#
# Vorhandene Dateien werden gesichert (*.bak-<zeitstempel>), nicht ueberschrieben.
# Exit-Codes: 0 = installiert, 1 = Pruefung fehlgeschlagen, 2 = Aufruf/Variante.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
VALIDATOR="${HERE}/validate_config.py"
HOME_DIR="${HOME}/.nanobot"
DRY_RUN=0
VARIANT="auto"
NO_VALIDATE=0
QUIET=0
STAMP="$(date +%Y%m%d-%H%M%S)"

usage() {
  # Kopfkommentar ausgeben, bis die erste Codezeile kommt.
  awk 'NR > 1 { if (!/^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
  cat <<'TXT'

Optionen:
  --home DIR         Ziel-Instanzverzeichnis (Default: ~/.nanobot)
  --variant NAME     auto | anthropic | ollama (Default: auto)
  --dry-run          Nur den Plan ausgeben, nichts schreiben
  --no-validate      Pruefung der Quelldatei ueberspringen
  --quiet            Keine Hinweise, nur Aktionen
  -h, --help         Diese Hilfe

Variante "auto":
  1. Ist die Umgebungsvariable der Key-Variante gesetzt, wird sie installiert.
  2. Sonst: laeuft Ollama lokal, wird die schluesselfreie Variante installiert.
  3. Sonst: Key-Variante mit deutlicher Warnung - sie startet erst nach dem Export.

Danach:
  nanobot --home DIR status
  python customize/eval/run_eval.py --home DIR
TXT
}

say()  { [[ $QUIET -eq 1 ]] || printf '  %s\n' "$*"; }
step() { printf '%s\n' "$*"; }
die()  { printf '\nFEHLER: %s\n\n' "$*" >&2; exit 2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) HOME_DIR="${2:?--home braucht einen Pfad}"; shift 2 ;;
    --variant) VARIANT="${2:?--variant braucht einen Namen}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-validate) NO_VALIDATE=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unbekannte Option: $1 (siehe --help)" ;;
  esac
done

case "$VARIANT" in
  auto|anthropic|ollama) ;;
  *) die "Unbekannte Variante: ${VARIANT} (erlaubt: auto, anthropic, ollama)" ;;
esac

CONFIG_KEY="${HERE}/config.json"
CONFIG_OLLAMA="${HERE}/config.ollama.json"

# --- Umgebungsvariablen, die die Key-Variante wirklich braucht -----------------
required_vars() {
  [[ -f "$1" ]] || return 0
  # Das Muster muss woertlich bleiben - grep sucht den Platzhalter, die Shell
  # soll ihn nicht expandieren.
  # shellcheck disable=SC2016
  grep -o '\${[A-Za-z_][A-Za-z0-9_]*}' "$1" 2>/dev/null \
    | sed 's/[\${}]//g' | sort -u || true
}

missing_vars() { # gibt fehlende Variablen aus, Exit 0 wenn keine fehlt
  local name missing=""
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if [[ -z "${!name:-}" ]]; then
      missing="${missing} ${name}"
    fi
  done <<< "$(required_vars "$1")"
  printf '%s' "${missing# }"
}

ollama_reachable() {
  local base="${OLLAMA_HOST:-http://127.0.0.1:11434}"
  case "$base" in *://*) ;; *) base="http://${base}" ;; esac
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "${base}/api/tags" >/dev/null 2>&1 && return 0
  fi
  command -v ollama >/dev/null 2>&1
}

# --- Variante bestimmen --------------------------------------------------------
VARIANT_REASON=""
if [[ "$VARIANT" == "auto" ]]; then
  MISSING_KEY="$(missing_vars "$CONFIG_KEY")"
  if [[ -z "$MISSING_KEY" ]]; then
    VARIANT="anthropic"
    VARIANT_REASON="weil die noetigen Umgebungsvariablen gesetzt sind"
  elif ollama_reachable; then
    VARIANT="ollama"
    VARIANT_REASON="weil Ollama lokal erreichbar ist (kein API-Key noetig)"
  else
    VARIANT="anthropic"
    VARIANT_REASON="weil kein Ollama gefunden wurde - Key-Variante, startet erst nach dem Export"
  fi
fi

case "$VARIANT" in
  anthropic) CONFIG_SRC="$CONFIG_KEY";    VARIANT_LABEL="mit API-Key (stark)" ;;
  ollama)    CONFIG_SRC="$CONFIG_OLLAMA"; VARIANT_LABEL="schluesselfrei ueber Ollama" ;;
esac

[[ -f "$CONFIG_SRC" ]] || die "Konfigurationsdatei fehlt: ${CONFIG_SRC}"

WORKSPACE="${HOME_DIR}/workspace"
MISSING_KEY_VARS="$(missing_vars "$CONFIG_SRC")"

# --- Konfiguration pruefen -----------------------------------------------------
VALIDATION_LINE="uebersprungen"
if [[ $NO_VALIDATE -eq 0 ]]; then
  if [[ ! -f "$VALIDATOR" ]]; then
    VALIDATION_LINE="nicht verfuegbar (validate_config.py fehlt)"
  elif ! command -v "$PYTHON" >/dev/null 2>&1; then
    VALIDATION_LINE="nicht verfuegbar (${PYTHON} fehlt)"
  else
    set +e
    VALIDATION_OUT="$("$PYTHON" "$VALIDATOR" "$CONFIG_SRC" 2>&1)"
    VALIDATION_STATUS=$?
    set -e
    VALIDATION_LINE="$(printf '%s\n' "$VALIDATION_OUT" | grep '^Ergebnis:' || true)"
    [[ -n "$VALIDATION_LINE" ]] || VALIDATION_LINE="kein Ergebnis gelesen"
    if [[ $VALIDATION_STATUS -ne 0 ]]; then
      printf '\n%s\n' "$VALIDATION_OUT" >&2
      printf '\nFEHLER: Die Konfiguration hat Befunde (siehe oben).\n' >&2
      printf '        Erst korrigieren - oder mit --no-validate bewusst ueberspringen.\n\n' >&2
      exit 1
    fi
  fi
fi

# --- Zielpruefungen ------------------------------------------------------------
if [[ -d "$HOME_DIR" ]]; then
  TARGET_STATE="vorhanden"
else
  TARGET_STATE="wird erstellt"
fi

# Schreibrechte am Ziel oder am naechsten vorhandenen Elternverzeichnis pruefen.
WRITE_CHECK_DIR="$HOME_DIR"
while [[ ! -d "$WRITE_CHECK_DIR" ]]; do
  PARENT_OF="$(dirname "$WRITE_CHECK_DIR")"
  [[ "$PARENT_OF" == "$WRITE_CHECK_DIR" ]] && break
  WRITE_CHECK_DIR="$PARENT_OF"
done
if [[ ! -w "$WRITE_CHECK_DIR" ]]; then
  die "Keine Schreibrechte in ${WRITE_CHECK_DIR} - Rechte pruefen oder --home nutzen."
fi

NANOBOT_BIN="$(command -v nanobot || true)"

# --- Kopf ----------------------------------------------------------------------
printf '\n'
step "Nanobot von Alex - Installation"
say "Ziel-Instanz:   ${HOME_DIR}  (${TARGET_STATE})"
say "Variante:       ${VARIANT} - ${VARIANT_LABEL}  (${CONFIG_SRC##*/})"
if [[ -n "$VARIANT_REASON" ]]; then
  say "Begruendung:    automatisch, ${VARIANT_REASON}"
fi
say "Konfigpruefung: ${VALIDATION_LINE}"
if [[ -n "$MISSING_KEY_VARS" ]]; then
  say "Achtung:        nicht gesetzt: ${MISSING_KEY_VARS} - der Start scheitert,"
  say "                bis die Variable exportiert ist."
elif [[ "$VARIANT" == "ollama" ]]; then
  say "Umgebung:       keine Platzhalter, laeuft ohne API-Key."
fi

# --- Installation (oder Plan) --------------------------------------------------
installed=0
unchanged=0
backups=0

install_file() {
  local src="$1" dst="$2"
  local action="neu"
  if [[ -f "$dst" ]]; then
    if cmp -s "$src" "$dst"; then
      action="unveraendert"
    else
      action="ersetzt (Sicherung: ${dst##*/}.bak-${STAMP})"
    fi
  fi
  if [[ $DRY_RUN -eq 1 ]]; then
    printf '  %-11s %s\n' "$action" "$dst"
    [[ "$action" == "neu" ]] && installed=$((installed + 1))
    [[ "$action" == "unveraendert" ]] && unchanged=$((unchanged + 1))
    return 0
  fi
  if [[ "$action" == "unveraendert" ]]; then
    printf '  %-11s %s\n' "$action" "$dst"
    unchanged=$((unchanged + 1))
    return 0
  fi
  if [[ -f "$dst" ]]; then
    if ! cp "$dst" "${dst}.bak-${STAMP}"; then
      printf '\nFEHLER: Sicherung fehlgeschlagen fuer %s\n\n' "$dst" >&2
      exit 2
    fi
    backups=$((backups + 1))
  fi
  if ! mkdir -p "$(dirname "$dst")" || ! cp "$src" "$dst"; then
    printf '\nFEHLER: Schreiben fehlgeschlagen fuer %s\n\n' "$dst" >&2
    exit 2
  fi
  printf '  %-11s %s\n' "$action" "$dst"
  installed=$((installed + 1))
}

printf '\n'
step "Aktionen:"
install_file "$CONFIG_SRC"      "${HOME_DIR}/config.json"
install_file "${HERE}/SOUL.md"  "${WORKSPACE}/SOUL.md"
install_file "${HERE}/AGENTS.md" "${WORKSPACE}/AGENTS.md"

# --- Nach dem Schreiben: installierte Datei noch einmal pruefen ----------------
if [[ $DRY_RUN -eq 0 && -f "$VALIDATOR" ]] && command -v "$PYTHON" >/dev/null 2>&1; then
  if ! "$PYTHON" "$VALIDATOR" "${HOME_DIR}/config.json" >/dev/null 2>&1; then
    say "Warnung:      die installierte Konfiguration hat Befunde -"
    say "              ${PYTHON} ${VALIDATOR} \"${HOME_DIR}/config.json\""
  fi
fi

# --- Naechste Schritte ---------------------------------------------------------
printf '\n'
if [[ $DRY_RUN -eq 1 ]]; then
  step "Dry Run: es wurde nichts geschrieben."
  say "Ausfuehren ohne --dry-run schreibt ${installed} Datei(en) neu,"
  say "${unchanged} bleiben unveraendert."
else
  step "Fertig: ${installed} Datei(en) geschrieben, ${unchanged} unveraendert, ${backups} Sicherung(en)."
fi

printf '\n'
step "Naechste Schritte:"
if [[ "$VARIANT" == "anthropic" ]]; then
  printf '  1. API-Key exportieren (nur noetig, falls noch nicht geschehen):\n'
  printf '       export ANTHROPIC_API_KEY=...\n'
else
  printf '  1. Modell laden, falls noch nicht vorhanden:\n'
  printf '       ollama pull qwen3:8b\n'
fi
printf '  2. Status pruefen - muss "provider/model configuration is ready" zeigen:\n'
if [[ -n "$NANOBOT_BIN" ]]; then
  printf '       nanobot --home "%s" status\n' "${HOME_DIR}"
else
  printf '       nanobot --home "%s" status   # nanobot ist noch nicht im PATH\n' "${HOME_DIR}"
  printf '       Installation: pip install nanobot-von-alex   (oder ./scripts/install.sh)\n'
fi
printf '  3. Messen statt raten:\n'
printf '       %s %s/eval/run_eval.py --home "%s"\n' "${PYTHON}" "${HERE}" "${HOME_DIR}"
printf '\n'
if [[ "$VARIANT" == "anthropic" && -n "$MISSING_KEY_VARS" ]]; then
  printf '  Ohne %s bleibt das Ergebnis bei 0 %% - ohne Modell kann der Bot\n' "$MISSING_KEY_VARS"
  printf '  nicht denken. Die schluesselfreie Variante installiert:\n'
  printf '       %s --variant ollama\n' "${BASH_SOURCE[0]}"
else
  printf '  Tuning, Presets und Messwerte: customize/README.md\n'
fi
printf '\n'
