#!/bin/bash

# -------------------------------
# RouterConfigUI Full Installer
# -------------------------------

APP_NAME="RouterConfigUI"
EXEC_NAME="$APP_NAME"                     # Name of executable file
ICON_SRC="./router_icon.png"            # Source icon in repo
BIN_DEST="$HOME/.local/bin"
ICON_DEST="$HOME/.local/share/icons/hicolor/48x48/apps/router_icon.png"
DESKTOP_DEST="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DEST/router_config.desktop"

echo "Installing $APP_NAME..."

# -------------------------------
# 1. Create directories if they don't exist
mkdir -p "$BIN_DEST" "$HOME/.local/share/icons/hicolor/48x48/apps" "$DESKTOP_DEST"

# -------------------------------
# 2. copy the executable
if [ -f "./$EXEC_NAME" ]; then
    cp "./$EXEC_NAME" "$BIN_DEST/"
    chmod +x "$BIN_DEST/$EXEC_NAME"
    echo "Executable installed to $BIN_DEST/$EXEC_NAME"
else
    echo "ERROR: $EXEC_NAME not found in current directory!"
    exit 1
fi

# -------------------------------
# 3. Copy and process icon
if [ -f "$ICON_SRC" ]; then
    if command -v convert >/dev/null; then
        convert "$ICON_SRC" -trim +repage "$ICON_DEST"
    else
        cp "$ICON_SRC" "$ICON_DEST"
    fi
    echo "Icon installed to $ICON_DEST"
else
    echo "Warning: Icon $ICON_SRC not found! Skipping icon installation."
fi

# -------------------------------
# 4. Update GTK icon cache & clear old caches
gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" &>/dev/null
rm -rf "$HOME/.cache/icon-cache.kcache" "$HOME/.cache/gnome-shell"

# -------------------------------
# 5. Create .desktop launcher
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Router Config Builder
Comment=Deploy Cisco configurations via Serial/SSH
Exec=$BIN_DEST/$EXEC_NAME
Icon=$ICON_DEST
Terminal=false
Categories=Network;Utility;
StartupWMClass=$APP_NAME
EOF
chmod +x "$DESKTOP_FILE"
echo "Desktop launcher created at $DESKTOP_FILE"

# -------------------------------
# 6. Pin to GNOME sidebar (favorites)
current_favs=$(gsettings get org.gnome.shell favorite-apps)
if [[ $current_favs != *"router_config.desktop"* ]]; then
    gsettings set org.gnome.shell favorite-apps "$(echo $current_favs | sed "s/]$/, 'router_config.desktop']/")"
    echo "Pinned $APP_NAME to GNOME sidebar"
else
    echo "$APP_NAME is already pinned to GNOME sidebar"
fi

# -------------------------------
# 7.  Fix serial port permissions
echo "Ensuring serial port access..."
sudo usermod -aG dialout $USER

# -------------------------------
# 8. Rollback function in case of errors
rollback() {
    echo "Rolling back installation..."
    rm -f "$BIN_DEST/$EXEC_NAME" "$ICON_DEST" "$DESKTOP_FILE"
    current_favs=$(gsettings get org.gnome.shell favorite-apps)
    if [[ $current_favs == *"router_config.desktop"* ]]; then
        gsettings set org.gnome.shell favorite-apps "$(echo $current_favs | sed "s/, 'router_config.desktop'//")"
    fi
    echo "Rollback complete."
}

# -------------------------------
echo "-----------------------------------------------"
echo "DONE! You can now find '$APP_NAME' in your Apps menu."
echo "NOTE: You may need to log out and back in once for"
echo "serial port permissions to take effect."
echo "-----------------------------------------------"
