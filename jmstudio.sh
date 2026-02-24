#!/bin/bash
# Launcher script for JM Studio under Wine

export WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/jmstudio-wine"

# First-run: initialize the prefix and install the app
if [ ! -d "$WINEPREFIX" ]; then
    echo "Initializing Wine prefix..."
    wineboot --init
    # TODO: copy or install JM Studio into the prefix
    # cp -r /app/share/jmstudio/* "$WINEPREFIX/drive_c/Program Files/JMStudio/"
fi

wine "$WINEPREFIX/drive_c/Program Files/JMStudio/JMStudio.exe" "$@"
