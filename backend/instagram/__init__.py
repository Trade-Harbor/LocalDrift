"""Instagram carousel generator.

Renders weekly events for a 1080x1080 IG carousel: cover slide, one
slide per event, plus a final CTA slide. Output is a list of PIL
Images and (via the runner) a ZIP of PNGs ready to upload.

Mirrors the backend/reddit_bot/ structure:
  renderer.py  pure PIL rendering, no I/O
  fetcher.py   async DB lookup for the week's events
  runner.py    orchestrator + ZIP packaging

The admin preview page at /admin/instagram lets you pick a week,
see thumbnail previews of each slide, and download the ZIP.
"""
