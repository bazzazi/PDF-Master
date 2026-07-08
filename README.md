# PDF Master

Modern desktop PDF viewer & toolkit built with PyQt5.

## Run
    python3 -m pip install PyQt5 PyMuPDF
    python3 pdf_master.py

## What's in this release
- **91+ hand-tuned SVG icons** in `./icons/` (feather-inspired line set, auto-tinted to the active theme — day / night / sepia).
- **Animated loading overlay** while any PDF is opening (spinner + caption, ~60fps).
- **Cleaner, modern toolbar** — duplicate / niche tools (hand-drag, auto-scroll, pin) removed from the bar.
- Prev/next page buttons now ship with dedicated arrow icons.
- Faster large-PDF loads (lazy page-dimension cache + deferred thumbnail build).
- Themed right-click menu, robust fullscreen toolbar auto-reveal, splash disabled.
