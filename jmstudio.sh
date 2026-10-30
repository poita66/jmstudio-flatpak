#!/bin/sh
# Launcher for JM Studio under the patched Wine in this Flatpak.
#
# JM Studio is not redistributable, so it is not in the Flatpak. On first run this installs it
# into the app's private Wine prefix from the installer the user downloaded:
#   flatpak run io.github.poita66.jmstudio [/path/to/JMStudioSetup.exe]
# Without an argument, the newest JMStudio*.exe in the Downloads folder is used.
set -eu

export WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/prefix"
# JM Studio is native Qt/C++; skip the Mono and Gecko install prompts on prefix creation.
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree,mshtml=}"
launch="$WINEPREFIX/drive_c/Program Files (x86)/JMStudio/Launch.exe"
download_url="https://forum.jimumeta.com/home/help/download.html"

message() {
    # wscript shows WScript.Echo as a message box, so this needs nothing outside Wine.
    script="$WINEPREFIX/drive_c/windows/temp/jmstudio-message.js"
    printf 'WScript.Echo("%s");\n' "$1" > "$script"
    wine wscript //nologo 'C:\windows\temp\jmstudio-message.js'
}

if [ ! -f "$launch" ]; then
    wineboot --init
    if [ $# -gt 0 ] && [ -f "$1" ]; then
        installer="$1"
        shift
    else
        downloads="$(xdg-user-dir DOWNLOAD 2>/dev/null || echo "$HOME/Downloads")"
        installer="$(ls -t "$downloads"/JMStudio*.exe 2>/dev/null | head -n 1 || true)"
    fi
    if [ -z "$installer" ]; then
        message "JM Studio is not installed yet.\\n\\nDownload the JM Studio installer from\\n$download_url\\ninto your Downloads folder, then start JM Studio again."
        exit 1
    fi
    echo "Installing JM Studio from $installer" >&2
    wine "$installer"
    if [ ! -f "$launch" ]; then
        message "The JM Studio installer finished, but JM Studio was not found in the expected place.\\n\\nRun the installer again with the default install location."
        exit 1
    fi
fi

exec wine "$launch" "$@"
