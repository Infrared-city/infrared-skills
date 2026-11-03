"""A small PNG decoder for the images the SDK renderer writes (no extra library).

Dynamo's Python has no Pillow; the SDK renderer returns PNG bytes. This reads
8-bit RGB or RGBA, not interlaced, with all five row filters.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> np.ndarray:
    out = np.zeros((height, stride), dtype=np.uint8)
    pos = 0
    for y in range(height):
        kind = raw[pos]
        line = np.frombuffer(raw, dtype=np.uint8, count=stride, offset=pos + 1)
        pos += stride + 1
        prev = out[y - 1] if y else np.zeros(stride, dtype=np.uint8)
        if kind == 0:
            out[y] = line
        elif kind == 2:  # Up
            out[y] = (line.astype(np.uint16) + prev) & 255
        else:  # Sub, Average, Paeth depend on the pixel to the left: a loop
            row = out[y]
            for i in range(stride):
                left = int(row[i - bpp]) if i >= bpp else 0
                if kind == 1:
                    add = left
                elif kind == 3:
                    add = (left + int(prev[i])) >> 1
                elif kind == 4:
                    up_left = int(prev[i - bpp]) if i >= bpp else 0
                    add = _paeth(left, int(prev[i]), up_left)
                else:
                    raise ValueError("PNG: unknown filter type %d." % kind)
                row[i] = (int(line[i]) + add) & 255
    return out


def decode_png(data: bytes) -> np.ndarray:
    """Decode the PNG the kernel writes: 8-bit RGB or RGBA, not interlaced.

    Returns an array ``(height, width, 3 or 4)`` of ``uint8``.

    Raises
    ------
    ValueError
        For anything else (other colour type or bit depth, interlacing, a bad
        chunk or checksum, truncated data).
    """
    if data[:8] != _PNG_SIGNATURE:
        raise ValueError("PNG: bad signature, this is not a PNG file.")
    pos, header, idat = 8, None, []
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        body = data[pos + 8 : pos + 8 + length]
        crc = data[pos + 8 + length : pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            raise ValueError("PNG: the data is cut off in a %r chunk." % kind)
        if struct.unpack(">I", crc)[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            raise ValueError("PNG: bad checksum in a %r chunk." % kind)
        pos += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if header is None or not idat:
        raise ValueError("PNG: no header or no image data.")
    width, height, depth, color, _compression, _filter, interlace = header
    if depth != 8 or color not in (2, 6) or interlace != 0:
        raise ValueError(
            "PNG: only 8-bit RGB or RGBA without interlacing is supported "
            "(got depth %d, colour type %d, interlace %d)." % (depth, color, interlace)
        )
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(b"".join(idat))
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG: the image data has the wrong size.")
    return _unfilter(raw, height, stride, channels).reshape(height, width, channels)
