"""Auto-detect and (de)compress a vendor_boot ramdisk fragment.
Supports the two codecs Android actually uses for these: legacy-framed LZ4
(what AOSP's build system produces by default) and raw zstd frames (what
newer/GKI-ish kernels increasingly support, and what this whole project
ended up using because it compresses far better).
"""
import struct
import lz4legacy
import lz4legacy_compress
import zstd_wrap

LZ4_LEGACY_MAGIC = 0x184C2102
ZSTD_MAGIC = 0xFD2FB528  # bytes on disk: 28 B5 2F FD (little-endian frame magic)


def detect_codec(data: bytes) -> str:
    if len(data) < 4:
        return "raw"
    magic = struct.unpack_from("<I", data, 0)[0]
    if magic == LZ4_LEGACY_MAGIC:
        return "lz4legacy"
    if magic == ZSTD_MAGIC:
        return "zstd"
    return "raw"


def decompress(data: bytes) -> tuple[bytes, str]:
    """Returns (decompressed_bytes, codec_name_used)."""
    codec = detect_codec(data)
    if codec == "lz4legacy":
        return lz4legacy.decompress(data), codec
    if codec == "zstd":
        return zstd_wrap.decompress(data), codec
    # Not a recognized compressed stream - assume it's already raw cpio.
    return data, "raw"


def compress(data: bytes, codec: str, level: int = 19) -> bytes:
    if codec == "lz4legacy":
        return lz4legacy_compress.compress(data, 12)
    if codec == "zstd":
        return zstd_wrap.compress(data, level)
    if codec == "raw":
        return data
    raise ValueError(f"unknown codec: {codec}")
