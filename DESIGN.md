---
version: alpha
name: Scryne profile
description: A GitHub profile drawn as a measuring instrument. Dark is an oscilloscope screen with amber phosphor; light is graph paper with an orange plotter pen.
colors:
  # Dark: oscilloscope screen. Green-black, not pure black, so it sits apart from GitHub's blue-black page.
  scope: "#0F1210"
  scope-edge: "#262C27"
  scope-grid: "#1A1F1B"
  scope-grid-strong: "#29302A"
  scope-ink: "#ECE7DC"
  scope-ink-2: "#A3A99F"
  scope-ink-3: "#757C73"
  phosphor: "#FFB547"
  # Light: graph paper and plotter ink.
  paper: "#F7F4EC"
  paper-edge: "#DAD3C2"
  paper-grid: "#ECE6D8"
  paper-grid-strong: "#DDD5C3"
  ink: "#1C1E1C"
  ink-2: "#4F524B"
  ink-3: "#6E7068"
  pen: "#C2410C"
typography:
  display:
    fontFamily: Instrument Serif
    fontWeight: 400
    letterSpacing: -0.01em
  motto:
    fontFamily: Instrument Serif Italic
    fontWeight: 400
  readout:
    fontFamily: JetBrains Mono
    fontWeight: 600
  label:
    fontFamily: JetBrains Mono
    fontWeight: 500
    letterSpacing: 0.14em
rounded:
  panel: 18px
spacing:
  gutter: 36px
  grid: 24px
---

# Scryne profile

## Idea

The motto is "measured before it is trusted", so the profile is an instrument rather than a brochure. Every image is a
panel of the same device: the hero is the scope screen, each project is a probe card with one reading, and the toolbox
is the rating plate riveted to the back. Text is short on purpose; the readings carry the content.

## Rules

- Text is converted to outlines by `build/build.py` (Instrument Serif + JetBrains Mono, both OFL). GitHub shows SVGs
  through `<img>`, where web fonts do not load, so outlines are the only way the type looks the same everywhere.
- Every image ships as a `-dark` and a `-light` file, switched with `<picture>`. No `prefers-color-scheme` inside SVG.
- Numbers on the cards come from the project READMEs and are only ever measured values. The hero trace is the public
  contribution calendar, refreshed daily by `.github/workflows/refresh.yml`, so it matches the calendar under it.
- Amber/orange is the only accent and marks a reading or a live signal. Everything else is ink on the panel.
- Motion is limited to the hero trace, the beam, the radar sweep and the cursor; all of it stops under
  `prefers-reduced-motion`.
- No personal data: no name, school, location or email on any panel.
