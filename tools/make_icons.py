"""Draw the toolbar icons (a point on a curved surface). Pure Python PNG.

    py -3.10 tools/make_icons.py
"""

import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'resources', 'FacePoint')
INK = (60, 60, 60)
ORANGE = (255, 120, 0)


def png(path, size, px):
    raw = b''.join(b'\x00' + bytes(c for p in row for c in p) for row in px)

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    with open(path, 'wb') as fh:
        fh.write(b'\x89PNG\r\n\x1a\n')
        fh.write(chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)))
        fh.write(chunk(b'IDAT', zlib.compress(raw, 9)))
        fh.write(chunk(b'IEND', b''))


def draw(size):
    ss = 4
    n = size * ss
    w = max(1.2, n / 14.0)
    # surface: an arc (bump) across the lower half; point: a dot on top of it
    cx, cy, r = n * 0.5, n * 1.25, n * 0.7
    px_, py_ = n * 0.5, cy - r
    dot = n * 0.13
    cov = [[None] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            fx, fy = x + 0.5, y + 0.5
            if abs(math.hypot(fx - cx, fy - cy) - r) < w / 2 and fy < n * 0.95:
                cov[y][x] = INK
            if math.hypot(fx - px_, fy - py_) < dot:
                cov[y][x] = ORANGE
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = cov[y * ss + sy][x * ss + sx]
                    if c:
                        acc[0] += c[0]
                        acc[1] += c[1]
                        acc[2] += c[2]
                        acc[3] += 1
            k = acc[3]
            row.append((acc[0] // k, acc[1] // k, acc[2] // k, 255 * k // (ss * ss))
                       if k else (0, 0, 0, 0))
        rows.append(row)
    return rows


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for s in (16, 32, 64):
        png(os.path.join(OUT, '%dx%d.png' % (s, s)), s, draw(s))
    print('icons written to', OUT)
