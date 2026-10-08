#!/bin/bash
# Install into ~/.config/sketchybar. An existing config is moved to ~/.config/sketchybar.bak.<timestamp>.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.config/sketchybar"

command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }
command -v swiftc >/dev/null || { echo "Xcode Command Line Tools are required: xcode-select --install"; exit 1; }
command -v sketchybar >/dev/null || { brew tap FelixKratz/formulae && brew install sketchybar; }
brew list --cask font-jetbrains-mono >/dev/null 2>&1 || brew install --cask font-jetbrains-mono
brew list --cask font-jetbrains-mono-nerd-font >/dev/null 2>&1 || brew install --cask font-jetbrains-mono-nerd-font
command -v media-control >/dev/null || brew install media-control   # now-playing source for the media island

[ -d "$DEST" ] && mv "$DEST" "$DEST.bak.$(date +%Y%m%d%H%M%S)"
mkdir -p "$DEST"
cp -R "$SRC/sketchybarrc" "$SRC/colors.sh" "$SRC/config.sh" "$SRC/plugins" "$SRC/helper" "$DEST/"
chmod +x "$DEST/sketchybarrc" "$DEST"/plugins/*.sh "$DEST/helper/build.sh"
bash "$DEST/helper/build.sh"

brew services restart sketchybar
echo "done → $DEST   (edit $DEST/config.sh, then: sketchybar --reload)"
