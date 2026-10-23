"""Text geometry measured against the live pixel widget's rendering layout.

Character/range boxes include logical layout positions outside the viewport;
point queries hit only displayed text inside its clipping area. Offsets are
Unicode code points, and masked fields use their displayed bullets exclusively.
"""
import math

import theme as T
import widgets as W


class TextGeometry:
    def __init__(self, widget, origin):
        self.widget, self.origin = widget, origin
        self.field = isinstance(widget, W.TextField)
        self.lines = [widget._disp()] if self.field else widget.lines
        self.font = T.FONT if self.field else widget.font
        self.height = 13 if self.field else widget.LH
        self.length = sum(map(len, self.lines)) + len(self.lines) - 1

    def context(self):
        w = self.widget
        return [*self.origin, w.x, w.y, w.w, w.h,
                *w.text_origin(), *w.text_viewport(), self.height]

    def point(self, offset):
        if type(offset) is not int or not 0 <= offset <= self.length:
            raise ValueError('Invalid text offset')
        for row, line in enumerate(self.lines):
            if offset <= len(line):
                return row, offset
            offset -= len(line) + 1
        raise ValueError('Invalid text offset')

    def box(self, row, start, end):
        w = self.widget
        x, y = w.text_origin() if self.field else w.text_origin(row)
        line = self.lines[row]
        left = T.text_w(self.font, line[:start])
        right = T.text_w(self.font, line[:end])
        if end > start:
            # A glyph can overhang its advance (including a missing-glyph box).
            # Keep the logical cell while enclosing the same font's drawn ink.
            ink_left, _, ink_right, _ = self.font.getbbox(line[start:end])
            # PIL keeps fractional advances while rendering the whole string.
            # Prefix integer widths alone can miss its final rasterized pixel.
            advance = self.font.getlength if hasattr(self.font, 'getlength') else lambda s: T.text_w(self.font, s)
            prefix = advance(line[:start])
            contextual = advance(line[:end]) - advance(line[start:end])
            right = max(right, math.ceil(max(prefix, contextual) + ink_right))
            left = min(left, math.floor(min(prefix, contextual) + ink_left))
        return [self.origin[0] + x + left, self.origin[1] + y,
                max(0, right - left), self.height]

    def character(self, offset):
        row, col = self.point(offset)
        # End-of-document and newline positions are zero-width caret boxes.
        return self.box(row, col, min(col + 1, len(self.lines[row])))

    def extent(self, start, end):
        first, col = self.point(start)
        last, final = self.point(end)
        if end < start:
            raise ValueError('Reversed text range')
        if first == last:
            return self.box(first, col, final)
        boxes = [self.box(first, col, len(self.lines[first]))]
        boxes.extend(self.box(row, 0, len(self.lines[row])) for row in range(first + 1, last))
        # The exclusive end at the next line's start includes no character there.
        if final:
            boxes.append(self.box(last, 0, final))
        left = min(b[0] for b in boxes); top = min(b[1] for b in boxes)
        right = max(b[0] + b[2] for b in boxes); bottom = max(b[1] + b[3] for b in boxes)
        return [left, top, right - left, bottom - top]

    def offset_at(self, x, y):
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in (x, y)):
            raise ValueError('Invalid text point')
        x -= self.origin[0]; y -= self.origin[1]
        vx, vy, width, height = self.widget.text_viewport()
        if not vx <= x < vx + width or not vy <= y < vy + height:
            return -1
        row = 0 if self.field else self.widget.sb.pos + int((y - vy) // self.height)
        if not 0 <= row < len(self.lines):
            return -1
        tx, ty = self.widget.text_origin() if self.field else self.widget.text_origin(row)
        px = x - tx
        line = self.lines[row]
        if not ty <= y < ty + self.height or not line:
            return -1
        if not 0 <= px < T.text_w(self.font, line):
            # First/last glyph ink may extend beyond the logical advance.
            col = 0 if px < 0 else len(line) - 1
            bx, _, bw, _ = self.box(row, col, col + 1)
            if bx <= x + self.origin[0] < bx + bw:
                return sum(len(s) + 1 for s in self.lines[:row]) + col
            return -1
        lo, hi = 0, len(line)
        while lo < hi:
            mid = (lo + hi) // 2
            if T.text_w(self.font, line[:mid + 1]) <= px:
                lo = mid + 1
            else:
                hi = mid
        return sum(len(line) + 1 for line in self.lines[:row]) + lo

    def query(self, kind, args):
        count = 1 if kind == 'character_rect' else 2
        if len(args) != count:
            raise ValueError('Invalid text geometry request')
        return {'character_rect': self.character, 'range_rect': self.extent,
                'offset_at_point': self.offset_at}[kind](*args)
