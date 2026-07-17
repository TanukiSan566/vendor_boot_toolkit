"""Rebuild a vendor_boot header-v4 image from a directory produced by
vboot_unpack.py (after you've edited whatever files you wanted to under
fragments/<name>/).

Usage:
    python3 vboot_repack.py <unpacked_dir> <output.img> [--codec name=lz4legacy|zstd ...]

By default every fragment is recompressed with whatever codec it was
unpacked with (recorded in metadata.json), so a no-op unpack+repack
round-trips byte-identically. Pass --codec platform=zstd (etc) to force a
different codec for a specific fragment folder, e.g. to shrink a fragment
that's grown too big for the partition after your edits.
"""
import json
import os
import struct
import sys

import codec
import cpio_pack

PAGE_SIZE_DEFAULT = 4096


def pagealign(data: bytes, page_size: int) -> bytes:
    rem = len(data) % page_size
    if rem:
        data = data + b"\x00" * (page_size - rem)
    return data


def repack(unpacked_dir, out_path, codec_overrides=None):
    codec_overrides = codec_overrides or {}
    with open(os.path.join(unpacked_dir, "metadata.json"), encoding="utf-8") as f:
        meta = json.load(f)

    page_size = meta["page_size"]
    header_size = meta["header_size"]
    entry_size = meta["vendor_ramdisk_table_entry_size"]

    dtb_data = open(os.path.join(unpacked_dir, "dtb.bin"), "rb").read()
    bootconfig_data = open(os.path.join(unpacked_dir, "bootconfig.bin"), "rb").read()

    frag_dir = os.path.join(unpacked_dir, "fragments")
    fragments = sorted(meta["fragments"], key=lambda f: f["index"])

    compressed_fragments = []
    for frag in fragments:
        folder = os.path.join(frag_dir, frag["folder"])
        cpio_tmp = os.path.join(unpacked_dir, f"_tmp_repack_{frag['folder']}.cpio")
        cpio_pack.pack(folder, cpio_tmp)
        raw_cpio = open(cpio_tmp, "rb").read()
        os.remove(cpio_tmp)

        use_codec = codec_overrides.get(frag["folder"], frag["codec"])
        if use_codec == "raw" and frag["codec"] != "raw":
            # metadata said it was compressed originally; if user didn't
            # explicitly ask for raw, keep the original codec instead of
            # silently shipping an uncompressed (huge) fragment.
            use_codec = frag["codec"]
        compressed = codec.compress(raw_cpio, use_codec)
        compressed_fragments.append((compressed, frag["ramdisk_type"], frag["name"]))
        print(f"fragment {frag['index']} ({frag['folder']}): "
              f"{len(raw_cpio)} bytes raw -> {len(compressed)} bytes ({use_codec})")

    total_ramdisk_size = sum(len(d) for d, _, _ in compressed_fragments)
    ramdisk_blob = b"".join(d for d, _, _ in compressed_fragments)

    table_entries = b""
    offset = 0
    for data, rtype, rname in compressed_fragments:
        name_b = rname.encode()
        entry = struct.pack("<III", len(data), offset, rtype)
        entry += name_b + b"\x00" * (32 - len(name_b))
        entry += b"\x00" * 64  # board_id[16] uint32, unused
        assert len(entry) == entry_size
        table_entries += entry
        offset += len(data)

    cmdline_b = meta["cmdline"].encode()
    cmdline_field = cmdline_b + b"\x00" * (2048 - len(cmdline_b))
    name_field = meta["board_name"].encode()
    name_field = name_field + b"\x00" * (16 - len(name_field))

    header = b"VNDRBOOT"
    header += struct.pack("<II", meta["header_version"], page_size)
    header += struct.pack("<III", meta["kernel_addr"], meta["ramdisk_addr"], total_ramdisk_size)
    header += cmdline_field
    header += struct.pack("<I", meta["tags_addr"])
    header += name_field
    header += struct.pack("<II", header_size, len(dtb_data))
    header += struct.pack("<Q", meta["dtb_addr"])
    header += struct.pack("<IIII", len(table_entries), len(compressed_fragments),
                           entry_size, len(bootconfig_data))
    header += b"\x00" * (header_size - len(header))

    out = bytearray()
    out += pagealign(header, page_size)
    out += pagealign(ramdisk_blob, page_size)
    out += pagealign(dtb_data, page_size)
    out += pagealign(table_entries, page_size)
    out += pagealign(bootconfig_data, page_size)

    with open(out_path, "wb") as f:
        f.write(out)
    print(f"\nwrote {out_path}: {len(out)} bytes")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python3 vboot_repack.py <unpacked_dir> <output.img> "
              "[fragment_folder=codec ...]")
        sys.exit(1)
    overrides = {}
    for arg in sys.argv[3:]:
        k, _, v = arg.partition("=")
        overrides[k] = v
    repack(sys.argv[1], sys.argv[2], overrides)
