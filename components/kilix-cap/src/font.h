/* font.h — original 7x14 bitmap face, drawn at FONT_SCALE runtime pixels
 * per authored pixel (21x42 with a 60px line advance at the shipped 3x).
 *
 * kilix-cap. FROZEN CONTRACT. Owning .c: src/font.c (LOC ~220).
 * Spec: docs/ENGINE.md §3 and docs/FONT.md.
 *
 * The face is authored directly for this project from generic bitmap-letterform
 * practice and the written size/legibility requirement alone. It is not
 * extracted, traced, transcribed, or redrawn from any product binary, ROM,
 * screenshot, or historical font. Each glyph is a directly authored seven-row
 * source mask rendered at two vertical pixels per row.
 */
#ifndef KILIX_CAP_FONT_H
#define KILIX_CAP_FONT_H

#include "canvas.h"

enum {
    /* Runtime pixels per authored pixel. The authored masks are the source
     * of truth at any scale: raising this enlarges the face by replication,
     * never by resampling, so no glyph edge is ever interpolated. */
    FONT_SCALE = 3,
    FONT_GLYPH_W = 7,               /* authored mask width, in mask pixels */
    FONT_CAP_H = 7 * 2 * FONT_SCALE,
    FONT_ADVANCE = 8 * FONT_SCALE,
    FONT_LINE_H = 20 * FONT_SCALE
};

int  font_text_width(const char *text);
bool font_has_glyph(unsigned char ch);
void font_draw(Canvas *c, int x, int y, const char *text, uint32_t rgb);

#endif /* KILIX_CAP_FONT_H */
