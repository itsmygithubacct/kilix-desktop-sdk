"""Private, bounded transport and AT-SPI metadata for the pixel desktop.

Only the helper imports GIO. The desktop owns every mutable widget and executes
requests on its UI thread. Neither process sends passwords or bus credentials
through this socket. Interface signatures follow the upstream AT-SPI XML API.
"""
import json
import re
import struct

PREFIX = 'org.a11y.atspi.'
ROOT = '/org/a11y/atspi/accessible/root'
NULL = '/org/a11y/atspi/null'
CACHE = '/org/a11y/atspi/cache'
LIMIT = 8 * 1024 * 1024
MAX_NODES = 20000

ROLES = {'application': 75, 'frame': 23, 'internal frame': 28, 'dialog': 16,
         'panel': 39, 'desktop icon': 13, 'label': 29, 'button': 43,
         'check box': 7, 'text': 61, 'password text': 40, 'list': 31,
         'list item': 32, 'menu bar': 34, 'menu': 33, 'menu item': 35,
         'check menu item': 8, 'separator': 50, 'page tab list': 38,
         'page tab': 37, 'combo box': 11, 'status bar': 54, 'canvas': 6}
STATES = {'active': 1, 'checked': 4, 'defunct': 6, 'editable': 7,
          'enabled': 8, 'expandable': 9, 'expanded': 10, 'focusable': 11,
          'focused': 12, 'iconified': 15, 'modal': 16, 'multi-line': 17,
          'multiselectable': 18, 'resizable': 21, 'selectable': 22,
          'selected': 23, 'sensitive': 24, 'showing': 25, 'single-line': 26,
          'visible': 30, 'selectable-text': 38, 'is-default': 39,
          'checkable': 41, 'has-popup': 42, 'read-only': 43}


def state_words(states):
    bits = sum(1 << STATES[s] for s in set(states))
    return [bits & 0xffffffff, bits >> 32]


class Channel:
    """Length-prefixed JSON over an inherited socket; partial IO stays bounded."""
    def __init__(self, sock):
        self.sock = sock
        sock.setblocking(False)
        self.input = bytearray()
        self.output = bytearray()

    def queue(self, value):
        data = json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode()
        if len(data) > LIMIT or len(self.output) + len(data) + 4 > 2 * LIMIT:
            raise ValueError('accessibility transport limit exceeded')
        self.output.extend(struct.pack('!I', len(data)))
        self.output.extend(data)
        self.flush()

    def flush(self):
        while self.output:
            try:
                n = self.sock.send(self.output)
            except BlockingIOError:
                return
            if not n:
                raise EOFError()
            del self.output[:n]

    def receive(self):
        # Limit work per UI pass, even when the helper has several requests.
        try:
            data = self.sock.recv(65536)
        except BlockingIOError:
            data = None
        if data == b'':
            raise EOFError()
        if data:
            self.input.extend(data)
        messages = []
        while len(self.input) >= 4 and len(messages) < 32:
            size = struct.unpack('!I', self.input[:4])[0]
            if size > LIMIT:
                raise ValueError('accessibility transport limit exceeded')
            if len(self.input) < size + 4:
                break
            messages.append(json.loads(self.input[4:4 + size]))
            del self.input[:4 + size]
        if len(self.input) > LIMIT + 4:
            raise ValueError('accessibility transport limit exceeded')
        return messages

    def has_message(self):
        return len(self.input) >= 4 and len(self.input) >= 4 + struct.unpack('!I', self.input[:4])[0]


def text_span(text, offset, granularity, direction=0, legacy=False):
    """Unicode offsets and AT-SPI character/word/sentence/line boundaries.

    A boundary includes following whitespace, as word/line-start queries do.
    End-boundary legacy queries instead include preceding whitespace. Empty
    terminal ranges and out-of-bounds offsets have deterministic empty replies.
    """
    if offset < 0 or offset > len(text):
        return '', -1, -1
    if legacy:
        if granularity == 0:
            boundaries = list(range(len(text) + 1))
        elif granularity in (1, 2):
            edges = [m.start() if granularity == 1 else m.end()
                     for m in re.finditer(r'\w+', text, re.UNICODE)]
            boundaries = sorted(set([0, *edges, len(text)]))
        elif granularity in (3, 4):
            ends = [m.end() for m in re.finditer(r'[.!?]+(?:\s+|$)', text)]
            boundaries = sorted(set([0, *ends, len(text)]))
        else:
            edges = [m.end() if granularity == 5 else m.start()
                     for m in re.finditer('\n', text)]
            boundaries = sorted(set([0, *edges, len(text)]))
    elif granularity == 0:
        boundaries = list(range(len(text) + 1))
    elif granularity == 1:
        boundaries = sorted(set([0, *[m.start() for m in re.finditer(r'\w+', text)], len(text)]))
    elif granularity == 2:
        boundaries = sorted(set([0, *[m.end() for m in re.finditer(r'[.!?]+(?:\s+|$)', text)], len(text)]))
    else:
        pattern = '\n' if granularity == 3 else r'\n\s*\n'
        boundaries = sorted(set([0, *[m.end() for m in re.finditer(pattern, text)], len(text)]))
    spans = list(zip(boundaries, boundaries[1:]))
    index = next((i for i, (a, b) in enumerate(spans) if a <= offset < b), len(spans))
    index += direction
    if 0 <= index < len(spans):
        a, b = spans[index]
        return text[a:b], a, b
    return '', len(text) if index >= len(spans) else 0, len(text) if index >= len(spans) else 0
