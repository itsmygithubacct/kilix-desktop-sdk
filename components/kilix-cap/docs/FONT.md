# Bitmap font provenance

The kilix-cap face was authored directly in src/font.c during a
Codex-assisted implementation session on 2026-07-20. It was designed from
generic bitmap-letterform practice and these written constraints only: a 14px
cap height, 20px line advance, high legibility on a four-grey reflective-style
display, and no antialiasing.

The source masks and metrics are unchanged in version 3.0.0. The same face is
now drawn over the full-color interface; its original high-contrast design
constraint is provenance, not a runtime palette restriction.

No historical font, ROM, executable, screenshot, font dump, traced glyph, or
other product artwork was viewed or used as an authoring input. The source
table is intentionally readable as seven-bit rows so every authored pixel is
reviewable.

Runtime metrics are:

| Property | Value |
|---|---:|
| Source mask | 7×7 bits |
| Rendered glyph | 7×14 pixels |
| Horizontal advance | 8 pixels |
| Line advance | 20 pixels |
| Repertoire | printable ASCII, U+0020–U+007E |
| Unsupported fallback | ? |

Each source row is duplicated vertically. Glyph pixels are written directly
in the opaque RGB color selected by the caller. There is no frame palette
quantizer. --font-test enforces the metrics, printable-ASCII repertoire,
substantial rendered ink, and opaque output.
