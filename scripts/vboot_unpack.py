"""Unpack an Android vendor_boot header-v4 image into editable folders.

Usage:
    python3 vboot_unpack.py <vendor_boot.img> <output_dir>

Produces, under <output_dir>:
    metadata.json          - every header field + per-fragment codec, needed
                              to rebuild a byte-faithful image later
    dtb.bin                - the device tree blob, as-is
    bootconfig.bin          - the (often tiny) bootconfig block, as-is
    fragments/<name>/       - one folder per vendor ramdisk fragment
                               (e.g. fragments/platform/, fragments/recovery/),
                               already un-cpio'd into a real directory tree
                               you can edit file-by-file
"""
import json
import os
import struct
import sys

import codec
import cpio_extract
import cpio_pack  # noqa: F401  (imported for parity/documentation; unpack doesn't call pack)

PAGE_SIZE_DEFAULT = 4096


def pagealign(n, page_size):
    rem = n % page_size
    return n if rem == 0 else n + page_size - rem


def unpack(img_path, outdir):
    with open(img_path, "rb") as f:
        data = f.read()
    assert data[0:8] == b"VNDRBOOT", "not a vendor_boot image (bad magic)"

    header_version, page_size = struct.unpack_from("<II", data, 8)
    kernel_addr, ramdisk_addr, vendor_ramdisk_size = struct.unpack_from("<III", data, 16)
    cmdline = data[28:28 + 2048].split(b"\x00")[0].decode(errors="replace")
    tags_addr = struct.unpack_from("<I", data, 2076)[0]
    name = data[2080:2080 + 16].split(b"\x00")[0].decode(errors="replace")
    header_size, dtb_size = struct.unpack_from("<II", data, 2096)
    dtb_addr = struct.unpack_from("<Q", data, 2104)[0]

    vendor_ramdisk_table_size = vendor_ramdisk_table_entry_num = 0
    vendor_ramdisk_table_entry_size = bootconfig_size = 0
    if header_version >= 4:
        (vendor_ramdisk_table_size, vendor_ramdisk_table_entry_num,
         vendor_ramdisk_table_entry_size, bootconfig_size) = struct.unpack_from("<IIII", data, 2112)

    pos = pagealign(header_size, page_size)
    ramdisk_blob = data[pos:pos + vendor_ramdisk_size]
    pos += pagealign(vendor_ramdisk_size, page_size)
    dtb_data = data[pos:pos + dtb_size]
    pos += pagealign(dtb_size, page_size)
    table_data = data[pos:pos + vendor_ramdisk_table_size]
    pos += pagealign(vendor_ramdisk_table_size, page_size)
    bootconfig_data = data[pos:pos + bootconfig_size]

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "dtb.bin"), "wb") as f:
        f.write(dtb_data)
    with open(os.path.join(outdir, "bootconfig.bin"), "wb") as f:
        f.write(bootconfig_data)

    fragments_meta = []
    frag_dir = os.path.join(outdir, "fragments")
    os.makedirs(frag_dir, exist_ok=True)

    entry_size = 108
    RTYPE_NAMES = {0: "none", 1: "platform", 2: "recovery", 3: "dlkm"}
    for i in range(vendor_ramdisk_table_entry_num):
        entry = table_data[i * entry_size:(i + 1) * entry_size]
        rsize, roffset, rtype = struct.unpack_from("<III", entry, 0)
        rname = entry[12:12 + 32].split(b"\x00")[0].decode(errors="replace")
        raw = ramdisk_blob[roffset:roffset + rsize]
        cpio_bytes, used_codec = codec.decompress(raw)

        folder_label = rname if rname else RTYPE_NAMES.get(rtype, f"type{rtype}")
        folder_label = folder_label or f"fragment{i}"
        out_folder = os.path.join(frag_dir, folder_label)
        cpio_tmp = os.path.join(outdir, f"_tmp_{folder_label}.cpio")
        with open(cpio_tmp, "wb") as f:
            f.write(cpio_bytes)
        cpio_extract.extract(cpio_tmp, out_folder)
        os.remove(cpio_tmp)

        fragments_meta.append({
            "index": i,
            "ramdisk_type": rtype,
            "ramdisk_type_name": RTYPE_NAMES.get(rtype, f"type{rtype}"),
            "name": rname,
            "folder": folder_label,
            "codec": used_codec,
        })
        print(f"fragment {i}: type={RTYPE_NAMES.get(rtype)} name={rname!r} "
              f"codec={used_codec} -> fragments/{folder_label}/")

    metadata = {
        "header_version": header_version,
        "page_size": page_size,
        "kernel_addr": kernel_addr,
        "ramdisk_addr": ramdisk_addr,
        "tags_addr": tags_addr,
        "dtb_addr": dtb_addr,
        "board_name": name,
        "cmdline": cmdline,
        "header_size": header_size,
        "vendor_ramdisk_table_entry_size": entry_size,
        "fragments": fragments_meta,
    }
    with open(os.path.join(outdir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"\ndone. Edit files under {frag_dir}/<fragment>/ then run vboot_repack.py "
          f"against this same output directory to rebuild the image.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 vboot_unpack.py <vendor_boot.img> <output_dir>")
        sys.exit(1)
    unpack(sys.argv[1], sys.argv[2])
