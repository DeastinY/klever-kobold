#!/bin/sh
# The app's executable. The kobold is a console program, so this opens
# Terminal on it: setup first (idempotent, seconds once done; the first time it
# pulls the models and the index), then the page. Ollama travels inside the app,
# in Resources/kobold/ollama, where the kobold looks for a bundled copy.
RES="$(cd "$(dirname "$0")/../Resources" && pwd)"
K="$RES/kobold/kobold"
CMD="clear; '$K' setup --install-ollama && exec '$K' serve"
exec osascript \
  -e 'on run argv' \
  -e '  tell application "Terminal"' \
  -e '    activate' \
  -e '    do script (item 1 of argv)' \
  -e '  end tell' \
  -e 'end run' \
  "$CMD"
