# Fonts for Instagram carousel rendering

The renderer tries fonts in this order:

1. **Inter** (preferred — matches LocalDrift's website typography).
   Drop these files here to use it:
   - `Inter-Black.ttf`
   - `Inter-Bold.ttf`
   - `Inter-Regular.ttf`

   Get them from https://fonts.google.com/specimen/Inter (free, OFL licensed).

2. **DejaVu Sans** at `/usr/share/fonts/truetype/dejavu/` — always available on
   Linux including Render's base image. Used as a fallback so the renderer
   works out of the box without anyone needing to drop in font files.

3. **PIL default bitmap font** — last resort. Looks bad. Logs a warning.

Local dev on macOS/Windows without Inter or DejaVu? Drop any TTF file you have
here named `Inter-Bold.ttf` etc. and the renderer will pick it up.
