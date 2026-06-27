---
version: alpha
name: PIO-demand-intelligence-platform
description: Enterprise analytics design system for a modern automotive parts planning tool. The structure borrows IBM-like clarity, the data surfaces borrow Linear-like restraint, and the chrome uses a dark automotive cockpit sidebar with a single disciplined blue accent. The result should feel operational, credible, and quietly premium.
---

## Visual Theme & Atmosphere

- Main canvas: light control-room workspace with soft blue-gray wash
- Sidebar: deep graphite cockpit panel for file loading, filters, and chart controls
- Accent: one electric enterprise blue used intentionally for calls to action and analytic highlights
- Personality: operational, precise, technical, calm

## Color Palette & Roles

- `#0f62fe`: primary action and active state
- `#08111f`: sidebar canvas
- `#101820`: primary ink
- `#5b6b7d`: muted ink
- `#f4f7fb`: page canvas
- `#ffffff`: card surface
- `#d7e0ea`: hairline border
- `#dce9ff`: highlight wash
- `#16a34a`: positive KPI accent
- `#dc2626`: negative or caution accent

## Typography Rules

- Headings: IBM Plex Sans, 600
- Body: IBM Plex Sans, 400
- Metadata and codes: IBM Plex Mono
- KPI values should be large, tight, and highly legible

## Component Styling

- Cards use 14px radius, thin borders, no harsh shadows
- Controls favor dense but breathable spacing
- Navigation and badges are uppercase with subtle tracking
- Charts should use clean grids, muted axes, and one strong accent series

## Layout Principles

- Left rail owns inputs and configuration
- Main area is a reporting surface: hero, KPIs, insights, charts, then data tables
- Keep generous spacing between sections to avoid dashboard fatigue

## Do's and Don'ts

- Do keep visual noise low and data legibility high
- Do let accents indicate focus, not decoration
- Do make empty and missing-data states feel intentional
- Don't use rainbow palettes
- Don't rely on generic default Streamlit styling

## Responsive Behavior

- Sidebar remains scrollable and self-contained
- KPI cards collapse gracefully on narrower screens
- Tables and charts should fill the width of their container
