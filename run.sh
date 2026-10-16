#!/bin/zsh
# Restarts BeamBar: through launchd when "Start at login" is on, otherwise directly.
DIR="${0:A:h}"
for LABEL in dev.beambar.app com.manoj.xgimi-bar; do
  if [ -f "$HOME/Library/LaunchAgents/$LABEL.plist" ]; then
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
    exit
  fi
done
LOG="$HOME/Library/Logs/beambar.log"
[ -d "$HOME/.config/xgimi-bar" ] && [ ! -d "$HOME/.config/beambar" ] && LOG="$HOME/Library/Logs/xgimi-bar.log"
pkill -f "$DIR/app.py" 2>/dev/null
nohup "$DIR/.venv/bin/python" "$DIR/app.py" >> "$LOG" 2>&1 &
disown
