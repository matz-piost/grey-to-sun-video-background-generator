# Project rules (always apply)

## Overlay placement: top third only

The presenter (Mila) occupies the middle and lower two-thirds of the
frame. **Every overlay, of every type** (`text`, `teaser`, `image`,
`screenshot`, `rect`, `arrow`, `circle`, `sticky`, or any future type) must
be positioned in the **top third of the frame only** — never in the middle
or bottom two-thirds, regardless of what `"position"` is set in the
project JSON.

This is enforced in code, not just convention: `compute_placement()` and
`caption_placement()` in `generate_background.py` both hard-clamp to the
top third (`TOP_THIRD = 1/3`, minus the top 10% platform-UI band). The
named positions (`left_side`, `lower_left`, `lower_center`, etc.) are rows
*within* that top third, not regions of the whole frame.

When adding a new overlay type, style, or position preset: keep it inside
this same top-third clamp. Don't add a position or style that places
content in the middle/lower frame — check with
`python3 generate_background.py <project> --debug-safe-zones` before
calling any new placement "done".
