#!/usr/bin/env bash
# Installiert die getunte nanobot-Konfiguration in eine nanobot-Instanz.
#
# Verwendung:
#   ./customize/apply.sh                 # Ziel: ~/.nanobot
#   ./customize/apply.sh --home /pfad    # eigenes Instanzverzeichnis
#   ./customize/apply.sh --dry-run       # nur zeigen, nichts schreiben
#   ./customize/apply.sh --variant ollama  # schluesselfrei, ohne API-Key
#
# Vorhandene Dateien werden gesichert, nicht ueberschrieben.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HOME}/.nanobot"
DRY_RUN=0
VARIANT="anthropic"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) HOME_DIR="$2"; shift 2 ;;
    --variant) VARIANT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; exit 2 ;;
  esac
done

case "$VARIANT" in
  anthropic) CONFIG_SRC="${HERE}/config.json" ;;
  ollama)    CONFIG_SRC="${HERE}/config.ollama.json" ;;
  *) echo "Unbekannte Variante: ${VARIANT} (erlaubt: anthropic, ollama)" >&2; exit 2 ;;
esac

WORKSPACE="${HOME_DIR}/workspace"
STAMP="$(date +%Y%m%d-%H%M%S)"

say() { printf '  %s\n' "$*"; }

install_file() {
  local src="$1" dst="$2"
  if [[ -f "$dst" ]]; then
    if diff -q "$src" "$dst" >/dev/null 2>&1; then
      say "unveraendert: $dst"
      return
    fi
    say "Sicherung:    $dst -> ${dst}.bak-${STAMP}"
    [[ $DRY_RUN -eq 1 ]] || cp "$dst" "${dst}.bak-${STAMP}"
  fi
  say "schreibe:     $dst"
  [[ $DRY_RUN -eq 1 ]] || { mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; }
}

echo
echo "nanobot customize - Installation"
echo "  Ziel-Instanz: ${HOME_DIR}"
echo "  Variante:     ${VARIANT}  (${CONFIG_SRC##*/})"
[[ $DRY_RUN -eq 1 ]] && echo "  Modus: DRY RUN (es wird nichts geschrieben)"
echo

install_file "${CONFIG_SRC}" "${HOME_DIR}/config.json"
install_file "${HERE}/SOUL.md"     "${WORKSPACE}/SOUL.md"
install_file "${HERE}/AGENTS.md"   "${WORKSPACE}/AGENTS.md"

echo
say "Fertig."
echo
echo "Naechste Schritte:"
if [[ "$VARIANT" == "anthropic" ]]; then
  echo "  1. API-Key in die Umgebung setzen, z. B.:"
  echo "       export ANTHROPIC_API_KEY=...       # wird von config.json referenziert"
else
  echo "  1. Ollama starten und ein Modell laden:"
  echo "       ollama pull qwen3:8b"
fi
echo "  2. Pruefen, ob ein Modell erkannt wird:"
echo "       nanobot --home \"${HOME_DIR}\" status"
echo "  3. Eval laufen lassen und den Wert notieren:"
echo "       python ${HERE}/eval/run_eval.py --home \"${HOME_DIR}\""
echo
echo "  Ohne Key bleibt das Ergebnis bei 0 %. Das ist erwartet -"
echo "  ohne Modell kann der Bot nicht denken."
echo
