#!/usr/bin/env python3
"""Draws brand/icon.png and brand/icon@2x.png: a small desktop computer with a status light.

Standard library only. Original artwork; it is not Apple's logo or a product photo.
    python3 dev/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "jarvis_host" / "brand"


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def rounded_box(x, y, cx, cy, half_w, half_h, radius):
    """Signed distance to a rounded rectangle (negative inside), in unit coordinates."""
    qx = abs(x - cx) - (half_w - radius)
    qy = abs(y - cy) - (half_h - radius)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    return outside + min(max(qx, qy), 0.0) - radius


def over(dst, color, alpha):
    """Composite color (r, g, b) with alpha over dst (r, g, b, a), all 0..1 floats."""
    da = dst[3]
    out_a = alpha + da * (1 - alpha)
    if out_a <= 0:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple((color[i] * alpha + dst[i] * da * (1 - alpha)) / out_a for i in range(3)) + (out_a,)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def pixel(x, y, px):
    """Colour of the icon at unit coordinates (x, y); px is the size of one pixel in them."""
    out = (0.0, 0.0, 0.0, 0.0)

    # Soft shadow on the surface below the box.
    r = math.hypot((x - 0.5) / 0.40, (y - 0.80) / 0.05)
    if r < 1:
        out = over(out, (0.05, 0.08, 0.12), 0.32 * (1 - r) ** 1.6)

    # Seen from slightly above: the front of the case (darker) and, over it, the top (lighter).
    front = rounded_box(x, y, 0.5, 0.545, 0.36, 0.215, 0.10)
    cover = clamp(0.5 - front / px)
    if cover > 0:
        t = clamp((y - 0.33) / 0.43)
        out = over(out, mix((0.74, 0.77, 0.83), (0.50, 0.54, 0.62), t), cover)

    top = rounded_box(x, y, 0.5, 0.45, 0.36, 0.19, 0.10)
    cover = clamp(0.5 - top / px)
    if cover > 0:
        t = clamp((y - 0.26) / 0.38)
        body = mix((0.97, 0.98, 0.99), (0.83, 0.86, 0.91), t)
        rim = clamp(1 - abs(top + 0.010) / (px * 1.6))
        body = mix(body, (1.0, 1.0, 1.0), 0.7 * rim)
        out = over(out, body, cover)
        # A faint edge where the top meets the front.
        edge = clamp(1 - abs(top) / (px * 2.0))
        out = over(out, (0.45, 0.50, 0.58), 0.25 * edge * (1 if y > 0.45 else 0))

    # Status light on the front, with a soft glow: the "reporting" light.
    lx, ly = 0.74, 0.695
    dist = math.hypot(x - lx, y - ly)
    glow = clamp(1 - dist / 0.075) ** 2
    if glow > 0 and out[3] > 0.5:
        out = over(out, (0.30, 0.85, 0.45), 0.35 * glow)
    led = clamp(0.5 - (dist - 0.026) / px)
    if led > 0:
        out = over(out, mix((0.18, 0.74, 0.38), (0.55, 0.95, 0.65), clamp(1 - dist / 0.026)), led)

    # Two small ports at the left of the front.
    for port_x in (0.265, 0.325):
        port = clamp(0.5 - rounded_box(x, y, port_x, ly, 0.020, 0.010, 0.010) / px)
        if port > 0:
            out = over(out, (0.27, 0.30, 0.37), 0.85 * port)
    return out


def write_png(size, path):
    px = 1.0 / size
    rows = []
    for j in range(size):
        row = bytearray([0])
        for i in range(size):
            r, g, b, a = pixel((i + 0.5) * px, (j + 0.5) * px, px)
            row += bytes((round(clamp(r) * 255), round(clamp(g) * 255), round(clamp(b) * 255), round(clamp(a) * 255)))
        rows.append(bytes(row))

    def chunk(tag, data):
        body = struct.pack(">I", len(data)) + tag + data
        return body + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    write_png(256, OUT / "icon.png")
    write_png(512, OUT / "icon@2x.png")
    print("wrote", OUT / "icon.png", "and", OUT / "icon@2x.png")
