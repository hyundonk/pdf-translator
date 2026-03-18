#!/bin/bash
# Download and prepare Korean fonts for pdf-translate
set -e
cd "$(dirname "$0")"
mkdir -p fonts

VARFONT=fonts/NotoSansKR-Regular.ttf
if [ ! -f "$VARFONT" ]; then
    echo "Downloading Noto Sans KR variable font..."
    curl -sL -o "$VARFONT" \
        "https://github.com/google/fonts/raw/main/ofl/notosanskr/NotoSansKR%5Bwght%5D.ttf"
fi

if [ ! -f fonts/NotoSansKR-400.ttf ] || [ ! -f fonts/NotoSansKR-700.ttf ]; then
    echo "Instantiating Regular (400) and Bold (700) weights..."
    python3 -c "
from fontTools.ttLib import TTFont
from fontTools.varLib.mutator import instantiateVariableFont
for wght in [400, 700]:
    font = TTFont('$VARFONT')
    instantiateVariableFont(font, {'wght': wght})
    font.save(f'fonts/NotoSansKR-{wght}.ttf')
    font.close()
    print(f'  Created NotoSansKR-{wght}.ttf')
"
fi

echo "Fonts ready."
