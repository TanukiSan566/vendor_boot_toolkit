"""Graft a known-good PLATFORM ramdisk fragment from a "donor" vendor_boot.img
(e.g. extracted from the stock ROM) onto a freshly-built vendor_boot.img,
keeping the fresh build's RECOVERY fragment untouched.

This is the automated version of "our whole vendor_boot saga": hovatek-style
minimal-manifest TWRP builds routinely produce a vendor_boot whose PLATFORM
fragment is a near-empty first_stage_ramdisk skeleton (there's no full
vendor source tree available at build time to generate it from), which
boots fine into TWRP (the RECOVERY fragment covers for it) but bootloops
the moment you try to boot to system. The fix has always been: keep the
freshly-built RECOVERY fragment (that's the actual TWRP you just built),
but swap in a real, complete PLATFORM fragment extracted from the device's
own stock vendor_boot.img.

Unlike vboot_unpack.py/vboot_repack.py, this script never decompresses or
touches cpio contents at all -- it operates purely on the still-compressed
fragment byte-blobs and splices them directly, so there's zero risk of a
lossy recompression round-trip changing anything.

Usage:
    python3 vboot_graft_platform.py <donor_stock.img> <fresh_build.img> <output.img>

By default: PLATFORM fragment + dtb + bootconfig come from the donor
(stock) image; RECOVERY (and any other non-platform) fragment(s) come from
the fresh build; header addrs/cmdline/page_size come from the fresh build
(so they match whatever kernel that build actually produced).
"""
import struct
import sys


def parse_header(data: bytes) -> dict:
    assert data[0:8] == b"VNDRBOOT", "not a vendor_boot image (bad magic)"
    header_version, page_size = struct.unpack_from("<II", data, 8)
    kernel_addr, ramdisk_addr, vendor_ramdisk_size = struct.unpack_from("<III", data, 16)
    cmdline = data[28:28 + 2048].split(b"\x00")[0]
    tags_addr = struct.unpack_from("<I", data, 2076)[0]
    name = data[2080:2080 + 16].split(b"\x00")[0]
    header_size, dtb_size = struct.unpack_from("<II", data, 2096)
    dtb_addr = struct.unpack_from("<Q", data, 2104)[0]
    assert header_version >= 4, "this tool only handles header_version 4 (multi-fragment) images"
    (table_size, entry_num, entry_size, bootconfig_size) = struct.unpack_from("<IIII", data, 2112)

    def pagealign(n):
        rem = n % page_size
        return n if rem == 0 else n + page_size - rem

    pos = pagealign(header_size)
    ramdisk_blob = data[pos:pos + vendor_ramdisk_size]
    pos += pagealign(vendor_ramdisk_size)
    dtb_data = data[pos:pos + dtb_size]
    pos += pagealign(dtb_size)
    table_data = data[pos:pos + table_size]
    pos += pagealign(table_size)
    bootconfig_data = data[pos:pos + bootconfig_size]

    fragments = []
    for i in range(entry_num):
        entry = table_data[i * entry_size:(i + 1) * entry_size]
        rsize, roffset, rtype = struct.unpack_from("<III", entry, 0)
        rname = entry[12:12 + 32].split(b"\x00")[0]
        fragments.append({
            "type": rtype,
            "name": rname,
            "data": ramdisk_blob[roffset:roffset + rsize],
        })

    return {
        "page_size": page_size,
        "kernel_addr": kernel_addr,
        "ramdisk_addr": ramdisk_addr,
        "cmdline": cmdline,
        "tags_addr": tags_addr,
        "board_name": name,
        "header_size": header_size,
        "dtb_addr": dtb_addr,
        "dtb_data": dtb_data,
        "bootconfig_data": bootconfig_data,
        "entry_size": entry_size,
        "fragments": fragments,
    }


def pagealign_bytes(data: bytes, page_size: int) -> bytes:
    rem = len(data) % page_size
    return data if rem == 0 else data + b"\x00" * (page_size - rem)


def graft(donor_path: str, fresh_path: str, out_path: str):
    donor = parse_header(open(donor_path, "rb").read())
    fresh = parse_header(open(fresh_path, "rb").read())

    donor_platform = [f for f in donor["fragments"] if f["type"] == 1]
    fresh_others = [f for f in fresh["fragments"] if f["type"] != 1]
    if not donor_platform:
        raise SystemExit(f"donor image {donor_path} has no PLATFORM (type=1) fragment")
    if not fresh_others:
        raise SystemExit(f"fresh image {fresh_path} has no non-PLATFORM fragment "
                          f"(nothing to keep from the fresh build?)")

    platform = donor_platform[0]
    print(f"donor PLATFORM fragment: {len(platform['data'])} bytes (from {donor_path})")
    for f in fresh_others:
        print(f"keeping fresh-build fragment: type={f['type']} name={f['name']!r} "
              f"({len(f['data'])} bytes, from {fresh_path})")

    final_fragments = [platform] + fresh_others

    # Header/cmdline/addrs come from the fresh build (matches its actual kernel).
    # dtb + bootconfig come from the donor (stock) image -- this is what carries
    # androidboot.hardware=... etc that a minimal-manifest build usually drops.
    page_size = fresh["page_size"]
    entry_size = fresh["entry_size"]

    ramdisk_blob = b"".join(f["data"] for f in final_fragments)
    table_entries = b""
    offset = 0
    for f in final_fragments:
        entry = struct.pack("<III", len(f["data"]), offset, f["type"])
        entry += f["name"] + b"\x00" * (32 - len(f["name"]))
        entry += b"\x00" * 64
        assert len(entry) == entry_size
        table_entries += entry
        offset += len(f["data"])

    cmdline_field = fresh["cmdline"] + b"\x00" * (2048 - len(fresh["cmdline"]))
    name_field = fresh["board_name"] + b"\x00" * (16 - len(fresh["board_name"]))

    header = b"VNDRBOOT"
    header += struct.pack("<II", 4, page_size)
    header += struct.pack("<III", fresh["kernel_addr"], fresh["ramdisk_addr"], len(ramdisk_blob))
    header += cmdline_field
    header += struct.pack("<I", fresh["tags_addr"])
    header += name_field
    header += struct.pack("<II", fresh["header_size"], len(donor["dtb_data"]))
    header += struct.pack("<Q", fresh["dtb_addr"])
    header += struct.pack("<IIII", len(table_entries), len(final_fragments), entry_size,
                           len(donor["bootconfig_data"]))
    header += b"\x00" * (fresh["header_size"] - len(header))

    out = bytearray()
    out += pagealign_bytes(header, page_size)
    out += pagealign_bytes(ramdisk_blob, page_size)
    out += pagealign_bytes(donor["dtb_data"], page_size)
    out += pagealign_bytes(table_entries, page_size)
    out += pagealign_bytes(donor["bootconfig_data"], page_size)

    with open(out_path, "wb") as f:
        f.write(out)
    print(f"\nwrote {out_path}: {len(out)} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: python3 vboot_graft_platform.py <donor_stock.img> <fresh_build.img> <output.img>")
        sys.exit(1)
    graft(sys.argv[1], sys.argv[2], sys.argv[3])
