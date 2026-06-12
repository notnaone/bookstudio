"""Generate a 2-second silent MP3 fixture. Run once; commit the output."""
from __future__ import annotations
import struct
import sys
from pathlib import Path

# Build the smallest possible MPEG-1 Layer III silent frame.
# This is a 2-second MP3 made of repeated minimal-bitrate silent frames.
# We hand-roll the bytes so we don't need ffmpeg or pydub.
#
# Each MPEG-1 L3 frame at 32 kbps / 22050 Hz / mono is 104 bytes.
# 2 seconds at 22050 Hz ≈ 86 frames.

HEADER = bytes.fromhex("FFFB1000")  # mpeg1 L3, 32 kbps, 22050 Hz, mono, no CRC
PAYLOAD = bytes(100)                 # 100 zero bytes of silence per frame
FRAME = HEADER + PAYLOAD
NUM_FRAMES = 86

out = Path(__file__).parent / "silence.mp3"
out.write_bytes(FRAME * NUM_FRAMES)
print(f"wrote {out} ({out.stat().st_size} bytes, {NUM_FRAMES} frames)")
