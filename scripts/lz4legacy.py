import ctypes, struct, sys

lib = ctypes.CDLL("/usr/lib/x86_64-linux-gnu/liblz4.so.1")
lib.LZ4_decompress_safe.restype = ctypes.c_int
lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]

LEGACY_MAGIC = 0x184C2102
BLOCK_SIZE = 8 << 20  # 8MB uncompressed block size used by legacy lz4 format

def decompress(data: bytes) -> bytes:
    magic = struct.unpack_from('<I', data, 0)[0]
    if magic != LEGACY_MAGIC:
        raise ValueError(f"not legacy lz4 magic: {hex(magic)}")
    off = 4
    out = bytearray()
    n = len(data)
    outbuf = ctypes.create_string_buffer(BLOCK_SIZE + 4096)
    while off + 4 <= n:
        block_size = struct.unpack_from('<I', data, off)[0]
        off += 4
        if block_size == 0:
            break
        # sanity: sometimes next magic can appear (concatenated frames) - handle simple case only
        block = data[off:off+block_size]
        if len(block) < block_size:
            break
        ret = lib.LZ4_decompress_safe(block, outbuf, block_size, BLOCK_SIZE + 4096)
        if ret < 0:
            raise RuntimeError(f"LZ4_decompress_safe failed ret={ret} at off={off}")
        out += outbuf.raw[:ret]
        off += block_size
    return bytes(out)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    out = decompress(data)
    open(sys.argv[2], 'wb').write(out)
    print(f"decompressed {len(data)} -> {len(out)} bytes")
