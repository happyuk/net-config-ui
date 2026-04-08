#!/bin/bash
# Stop the script if any command fails
set -e

PYINSTALLER="./.venv/bin/pyinstaller"

echo "1. Cleaning previous builds..."
rm -rf dist/ build/ deploy_staging/ *.tar.gz

echo "2. Compiling Python binary..."
$PYINSTALLER --onefile --windowed --name "RouterConfigUI" \
  --add-data "data:data" \
  --add-data "app/templates:templates" \
  --add-data "app/gui/styles:app/gui/styles" \
  --add-data "app/gui/assets:app/gui/assets" \
  --collect-all jinja2 \
  main.py

echo "3. Staging files into 'RouterConfigUI' folder..."
# Create the specific folder name you want the user to see upon extraction
mkdir -p deploy_staging/RouterConfigUI

# Copy files into that specific subfolder
cp dist/RouterConfigUI deploy_staging/RouterConfigUI/
cp app/gui/assets/router_icon.png deploy_staging/RouterConfigUI/
cp app/installer/install.sh deploy_staging/RouterConfigUI/
cp app/installer/uninstall.sh deploy_staging/RouterConfigUI/

echo "4. Creating final Tarball..."
# We still use -C deploy_staging, but we tell tar to grab the 'RouterConfigUI' folder
# This ensures that when unzipped, the user gets the folder, not loose files.
tar -czvf "RouterInstaller_$(date +%Y%m%d).tar.gz" -C deploy_staging RouterConfigUI

echo "5. Final Cleanup..."
rm -rf deploy_staging dist/ build/

echo "------------------------------------------------"
echo "SUCCESS: Installer package created."
echo "Extraction will now result in a 'RouterConfigUI/' folder."