# Truth Lens — UI Redesign Master Plan

## 1. Overview & Vision
This document outlines the phased redesign for the Truth Lens forensic application.
The design merges a high-density, forensic-grade dark interface with clear visual hierarchy, precision typography (Space Grotesk, Inter, JetBrains Mono), evidence-tag clip-path motifs, and hairline table separators.

## 2. Design System Tokens
- **--ink:** #0B0F14 (Base background)
- **--panel:** #131820 (Card and table container background)
- **--panel-raised:** #1A212B (Hover and active states)
- **--hairline:** #232B36 (Row and structural dividers)
- **--brand:** #3FC7F4 (Cyan primary actions and active states)
- **--brand-dim:** #1E4A5C (Subtle brand backing)
- **--tag-accent:** #E8B34C (Amber forensic evidence tag accents)
- **--risk-low:** #34D399 (Emerald authentic/low risk)
- **--risk-review:** #FBBF24 (Amber review required)
- **--risk-high:** #F87171 (Ruby high risk anomaly)
- **--text-primary:** #F5F7FA
- **--text-secondary:** #8B94A3

## 3. Typography Hierarchy
- **Display / Brand:** Space Grotesk (700 / 600)
- **Body / Interface:** Inter (400 / 500 / 600)
- **Data / Metrics / Hashes / IDs:** JetBrains Mono (500 / 700)

## 4. Architectural Rules
- All backend routes, schemas, models, and endpoints remain untouched.
- Vanilla JS only with zero framework lock-in.
- Full responsive support down to 375px.
- Accessibility with visible focus rings and prefers-reduced-motion support.
