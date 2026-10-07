"""Convert and push a complete RGB565 frame to the panel's VIMG TCP receiver.

The image stays in panel RAM. An ACK confirms publication for the GUI to consume,
not a measured LCD scanout. File conversion requires Pillow; --pattern and --raw
use only the Python standard library.
"""
from pathlib import Path
import argparse
import array
import json
import socket
import struct
import sys

WIDTH, HEIGHT, PORT = 480, 320, 18086
PAYLOAD_BYTES = WIDTH * HEIGHT * 2
HEADER = struct.Struct("<4sHHII")
ACK = struct.Struct("<4sI")


def checksum(payload):
    value = 2166136261
    for byte in payload:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def packed_pixels(words):
    pixels = array.array("H", words)
    if sys.byteorder != "little":
        pixels.byteswap()
    return pixels.tobytes()


def test_pattern(alternate=False):
    """Large colored blocks and a diagonal make generation/orientation visible."""
    palette = (0xf800, 0x07e0, 0x001f, 0xffe0)
    return packed_pixels(
        0xffff if abs(x - y * WIDTH // HEIGHT) < 4 else
        palette[(x // (WIDTH // 4) + int(alternate)) % 4]
        for y in range(HEIGHT) for x in range(WIDTH))


def from_image(path, fit="contain"):
    from PIL import Image, ImageOps
    with Image.open(path) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        if fit == "cover":
            canvas = ImageOps.fit(source, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        elif fit == "stretch":
            canvas = source.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        else:
            resized = ImageOps.contain(source, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (WIDTH, HEIGHT), (16, 16, 16))
            canvas.paste(resized, ((WIDTH-resized.width)//2, (HEIGHT-resized.height)//2))
        return packed_pixels(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
                             for r, g, b in canvas.getdata())


def receive_exact(connection, length):
    data = bytearray()
    while len(data) < length:
        part = connection.recv(length - len(data))
        if not part:
            raise ConnectionError("Panel closed the connection before the complete ACK")
        data.extend(part)
    return bytes(data)


def push(host, payload, port=PORT, timeout=40):
    if len(payload) != PAYLOAD_BYTES:
        raise ValueError(f"Expected {PAYLOAD_BYTES} RGB565 bytes, got {len(payload)}")
    digest = checksum(payload)
    with socket.create_connection((host, port), timeout=timeout) as connection:
        connection.settimeout(timeout)
        connection.sendall(HEADER.pack(b"VIMG", WIDTH, HEIGHT, len(payload), digest))
        connection.sendall(payload)
        magic, status = ACK.unpack(receive_exact(connection, ACK.size))
        if magic != b"VACK":
            raise ValueError("Invalid panel ACK magic")
        if status:
            raise RuntimeError(f"Panel rejected the upload (status {status})")
    return {"accepted_for_gui": True, "bytes": len(payload),
            "fnv1a32": f"{digest:08x}", "width": WIDTH, "height": HEIGHT,
            "persistent_image": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="Panel LAN IPv4 address or host name")
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--image", type=Path, help="PNG/JPEG or other Pillow-supported image")
    choice.add_argument("--raw", type=Path, help="Exactly 307200 bytes of little-endian RGB565")
    choice.add_argument("--pattern", action="store_true", help="Generate a diagnostic image without Pillow")
    parser.add_argument("--alternate", action="store_true", help="Use the second pattern palette")
    parser.add_argument("--fit", choices=("contain", "cover", "stretch"), default="contain")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    try:
        payload = (args.raw.read_bytes() if args.raw else
                   from_image(args.image, args.fit) if args.image else test_pattern(args.alternate))
        print(json.dumps(push(args.host, payload, args.port), indent=2))
    except ImportError as error:
        raise SystemExit("Image conversion requires Pillow: python -m pip install Pillow") from error
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
