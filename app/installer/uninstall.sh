#!/bin/bash

APP_NAME="RouterConfigUI"
EXEC_NAME="$APP_NAME"
BIN_DEST="$HOME/.local/bin/$EXEC_NAME"
ICON_DEST="$HOME/.local/share/icons/hicolor/48x48/apps/router_icon.png"
DESKTOP_FILE="$HOME/.local/share/applications/router_config.desktop"

echo "Uninstalling $APP_NAME..."

# 1️⃣ Remove the executable
if [ -f "$BIN_DEST" ]; then
    rm -f "$BIN_DEST"
    echo "Removed executable: $BIN_DEST"
fi

# 2️⃣ Remove the icon
if [ -f "$ICON_DEST" ]; then
    rm -f "$ICON_DEST"
    echo "Removed icon: $ICON_DEST"
fi

# 3️⃣ Remove the .desktop launcher
if [ -f "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "Removed desktop launcher: $DESKTOP_FILE"
fi

# 4️⃣ Remove from GNOME sidebar favorites
current_favs=$(gsettings get org.gnome.shell favorite-apps)
if [[ $current_favs == *"router_config.desktop"* ]]; then
    gsettings set org.gnome.shell favorite-apps "$(echo $current_favs | sed "s/, 'router_config.desktop'//; s/'router_config.desktop', //")"
    echo "Removed $APP_NAME from GNOME sidebar"
fi

# 5️⃣ Remove any residual icons from GTK caches
# Search common cache directories and remove related files
rm -f ~/.cache/icon-cache.kcache
rm -f ~/.cache/gnome-shell/*router_icon*.png
rm -rf ~/.cache/thumbnails/*

# 6️⃣ Update GTK icon cache
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" &>/dev/null

echo "-----------------------------------------------"
echo "$APP_NAME has been uninstalled completely."
echo "You may need to log out and back in to fully remove it from the sidebar and menus."
echo "-----------------------------------------------"
