# Aurora design rules

Theme: deep-navy console with a violet/cyan/pink aurora. Dark theme is the default; a light theme must also work.

Colour tokens (CSS variables, dark / light):
--bg #0B1020 / #F6F7FB; 
--surface #121A33 / #FFFFFF; 
--surface-2 #18224A / #F0F2F8; 
--border #26335F / #E3E6F0; 
--text #F5F7FF / #0F1530; 
--text-2 #AAB4D4 / #4A5375; 
--text-3 #7C87AD / #6B7493; 
--violet #7C5CFF / #6D4AFF; 
--cyan #22D3EE / #0891B2; 
--pink #F472B6 / #DB2777; 
--aurora: linear-gradient(135deg, #7C5CFF 0%, #22D3EE 55%, #F472B6 100%).

Status colours (same in both themes, used ONLY for status): 
critical #D03B3B (shape ▲), 
warning #FAB219 (◆), 
info #38BDF8 (●), 
healthy/resolved #0CA30C (✓). 
Severity is ALWAYS colour + shape + word, never colour alone.

Service colours (fixed mapping, dark / light): 
auth #199E70 / #1BAF7A; 
gateway #9085E9 / #4A3AA7; 
orders #D55181 / #E87BA4; 
payments #3987E5 / #2A78D6; 
unknown #7C87AD / #6B7493. 
A service colour must always appear next to the service name (dot + name), never alone.

Brand colour (aurora) is decoration only: logo, active nav item, primary buttons, 2px top edge of cards, KPI icon chips, background glow. Never use the aurora or brand colours to mean severity.

Charts: one data colour per series; the error-rate line is --cyan, 2px; the learned baseline band is violet at 18% opacity; anomalous ticks are critical-red dots 4px radius with a 2px ring in --surface; gridlines faint (--border at 50%), no vertical gridlines; animations off on live-updating charts; every chart has a hover tooltip; no dual y-axes.

Fonts: Inter for UI; JetBrains Mono for logs, timestamps and big numbers (font-variant-numeric: tabular-nums).

Sizes: page title 22px/600; card title 15px/600; body 14px; small 12px. Corners: cards 16px, buttons/inputs 10px, pills round. 4px spacing grid; card padding 20px; grid gap 16px.

Cards: --surface background, 1px --border, 2px aurora line on top edge, no heavy shadows; hover lifts 2px with a soft violet glow (respect prefers-reduced-motion).

Background: --bg plus two very soft radial glows (violet top-left, cyan bottom-right, max 12% opacity) fixed behind content.

Accessibility: WCAG AA text contrast; visible focus ring (2px --cyan); all icon-only buttons have aria-label; new alerts announced in an aria-live="polite" region; respect prefers-reduced-motion.

Times: 24-hour HH:MM:SS in the user's local time zone. Percentages: 1 decimal place.

Never show raw JSON to users except in an explicit "Copy JSON" action.
