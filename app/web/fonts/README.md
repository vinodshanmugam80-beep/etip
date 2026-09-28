# Fonts

ETIP self-hosts its fonts here (no external CDN needed — works fully offline).

## What's bundled (open-source, free for commercial use)

- **Inter** — body / data / numbers. SIL Open Font License (`Inter-OFL.txt`).
- **Montserrat** — the display / heading face (uppercase, letter-spaced). SIL Open
  Font License (`Montserrat-OFL.txt`). Used as the **Engravers-Gothic-style**
  fallback so the product looks right on every machine and offline.

Both are free to use, embed and redistribute in a commercial product under the OFL.

## Using your licensed Engravers Gothic (optional, recommended)

Engravers Gothic is a **commercial** typeface — it is not, and legally cannot be,
bundled here. If your organization owns a license (e.g. via Monotype / MyFonts, or
it shipped with your OS / Adobe), you can drop it in and it will be used
automatically, with **no code changes**:

1. Convert your licensed `.otf` / `.ttf` to WOFF2 (best size/quality). Either:
   - Online: any "OTF to WOFF2" converter, **or**
   - Locally: `pip install fonttools brotli` then
     `python -c "from fontTools.ttLib import TTFont; f=TTFont('EngraversGothic.otf'); f.flavor='woff2'; f.save('engravers-gothic.woff2')"`
2. Save the file **exactly** as `engravers-gothic.woff2` in this folder.
3. Restart the server (or just reload). The dashboard's `@font-face` already points
   here; the display type will switch to true Engravers Gothic wherever it renders.

> Check your license permits **web embedding / @font-face self-hosting** before
> deploying publicly — most desktop licenses require a separate webfont license.

If the file is absent, ETIP falls back to Montserrat (bundled) — nothing breaks.
