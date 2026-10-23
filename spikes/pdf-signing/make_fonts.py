"""Turn the Fontsource npm packages into the TTF files the spike needs.

    npm pack @fontsource/marcellus @fontsource/ibm-plex-sans @fontsource/ibm-plex-mono
    for f in fontsource-*.tgz; do mkdir -p "${f%.tgz}" && tar -xzf "$f" -C "${f%.tgz}"; done
    python make_fonts.py <folder with the unpacked packages> fonts/

All three families are licensed under the SIL Open Font License 1.1. The spike uses the
Latin subset (which includes æ, ø and å); the real product will bundle the full fonts.
"""

import pathlib
import sys

from fontTools.ttLib import TTFont

FILES = {
    "Marcellus-Regular.ttf": "fontsource-marcellus-*/package/files/marcellus-latin-400-normal.woff2",
    "IBMPlexSans-Regular.ttf": "fontsource-ibm-plex-sans-*/package/files/ibm-plex-sans-latin-400-normal.woff2",
    "IBMPlexSans-Medium.ttf": "fontsource-ibm-plex-sans-*/package/files/ibm-plex-sans-latin-500-normal.woff2",
    "IBMPlexSans-SemiBold.ttf": "fontsource-ibm-plex-sans-*/package/files/ibm-plex-sans-latin-600-normal.woff2",
    "IBMPlexMono-Medium.ttf": "fontsource-ibm-plex-mono-*/package/files/ibm-plex-mono-latin-500-normal.woff2",
}


def main(source: pathlib.Path, target: pathlib.Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, pattern in FILES.items():
        matches = sorted(source.glob(pattern))
        if not matches:
            raise SystemExit(f"missing {pattern} under {source}")
        font = TTFont(matches[-1])
        font.flavor = None  # WOFF2 -> plain TrueType
        font.save(target / name)
        print(f"{name}  <-  {matches[-1].name}")


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]))
