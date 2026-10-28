---
version: alpha
name: Scryne profile
description: A GitHub profile drawn as a measuring instrument behind silver glass. Dark is graphite glass over a cool silver mesh; light is frosted white glass over pale steel.
colors:
  # Dark: graphite glass. Silver and steel only; no warm hue anywhere.
  base: "#0B0C0F"
  surface: "#15181D"
  edge: "#23272E"
  rivet: "#2A2F37"
  blob-1: "#C9D1DC"
  blob-2: "#5B6878"
  blob-3: "#2A3442"
  ink: "#EEF1F5"
  ink-2: "#AAB1BB"
  ink-3: "#7D8590"
  accent: "#DCE2E9"
  metal-hi: "#FFFFFF"
  metal-lo: "#9AA4B0"
  # Light: frosted white glass over pale steel.
  light-base: "#DEE3E9"
  light-surface: "#F5F7F9"
  light-edge: "#C3CAD3"
  light-rivet: "#CDD3DB"
  light-blob-1: "#FFFFFF"
  light-blob-2: "#A9B4C1"
  light-blob-3: "#C7D0DA"
  light-ink: "#14171B"
  light-ink-2: "#434A53"
  light-ink-3: "#67707A"
  light-accent: "#3A4450"
  light-metal-hi: "#5D6876"
  light-metal-lo: "#1C232B"
glass:
  # Opacities: mesh = the three blobs behind the glass, sheen = frosted layer (top left, bottom right),
  # rim = light-catching edge (top left, bottom right), pane = small glass panes inside a panel,
  # surface = tint of objects drawn on the glass (receipt, pages, tiles).
  dark:
    mesh: [0.22, 0.42, 0.75]
    sheen: [0.08, 0.015]
    rim: [0.32, 0.05]
    pane: 0.05
    surface: 0.55
  light:
    mesh: [0.95, 0.55, 0.7]
    sheen: [0.6, 0.3]
    rim: [1, 0.35]
    pane: 0.45
    surface: 0.65
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
    fontWeight: 700
  label:
    fontFamily: JetBrains Mono
    fontWeight: 500
    letterSpacing: 0.14em
rounded:
  panel: 18px
  pane: 10px
spacing:
  gutter: 36px
---

# Scryne profile

## Idea

The motto is "measured before it is trusted", so the profile is an instrument rather than a brochure: the hero is a
scope screen, each project is a probe card with one reading, and the toolbox is the rating plate. The finish is dark
silver glass (Scryne, 2026-10-28: the amber "didn't look good"). Text is short on purpose; the readings carry the
content.

## Glass inside an `<img>`

GitHub shows these SVGs through `<img>`, so `backdrop-filter` has nothing to blur. The glass is built inside each file:
a heavily blurred mesh of three silver/steel blobs, a frosted sheen on top, a 1px edge and a light-catching rim
gradient (bright top left, fading bottom right). Small panes (readout box, chips) reuse the rim on a faint white fill.
Each card uses a different mesh layout so the grid does not read as one stamped tile; light always comes from the top
left.

## Rules

- Text is converted to outlines by `build/build.py` (Instrument Serif + JetBrains Mono, both OFL), because web fonts do
  not load inside `<img>`.
- Every image ships as a `-dark` and a `-light` file, switched with `<picture>`. No `prefers-color-scheme` inside SVG.
- Silver is the only accent. Readings use the vertical `metal` gradient; strokes use `accent`. No warm colours.
- Numbers on the cards come from the project READMEs and are only ever measured values. The hero trace is the public
  contribution calendar, refreshed daily by `.github/workflows/refresh.yml`, so it matches the calendar under it.
- Motion is limited to the hero trace, the beam, the radar sweep, the cursor and small draw-ins; all of it stops under
  `prefers-reduced-motion`.
- No personal data: no name, school, location or email on any panel.
