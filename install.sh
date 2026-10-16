#!/bin/zsh
# Sets up BeamBar from source: a Python venv with the dependencies, the
# `beambar` command on your PATH, then starts the menu bar app.
set -e
DIR="${0:A:h}"
cd "$DIR"

PYTHON=${PYTHON:-python3}
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
  echo "BeamBar needs Python 3.10 or newer (try: brew install python@3.12)." >&2
  exit 1
fi

"$PYTHON" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

BIN=/opt/homebrew/bin
[ -w "$BIN" ] || BIN="$HOME/.local/bin"
mkdir -p "$BIN"
ln -sf "$DIR/beambar" "$BIN/beambar"
echo "Installed the beambar command in $BIN"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Add $BIN to your PATH to use it from any terminal." ;; esac

./run.sh
echo "BeamBar is running: look for the projector icon in the menu bar, then choose Pair with projector…"
