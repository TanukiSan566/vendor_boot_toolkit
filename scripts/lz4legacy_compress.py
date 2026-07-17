import ctypes, struct, sys

lib = ctypes.CDLL("/usr/lib/x86_64-linux-gnu/liblz4.so.1")
lib.LZ4_compress_HC.restype = ctypes.c_int
lib.LZ4_compress_HC.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
lib.LZ4_compressBound.restype = ctypes.c_int
lib.LZ4_compressBound.argtypes = [ctypes.c_int]
HC_LEVEL = 9

LEGACY_MAGIC = 0x184C2102
BLOCK_SIZE = 8 << 20  # 8MB, matches Android's legacy lz4 ramdisk block size

def compress(data: bytes, level: int = HC_LEVEL) -> bytes:
    out = bytearray()
    out += struct.pack('<I', LEGACY_MAGIC)
    n = len(data)
    off = 0
    bound = lib.LZ4_compressBound(BLOCK_SIZE)
    outbuf = ctypes.create_string_buffer(bound)
    while off < n:
        chunk = data[off:off+BLOCK_SIZE]
        ret = lib.LZ4_compress_HC(chunk, outbuf, len(chunk), bound, HC_LEVEL)
        if ret <= 0:
            raise RuntimeError(f"compress failed at off={off}")
        out += struct.pack('<I', ret)
        out += outbuf.raw[:ret]
        off += len(chunk)
    return bytes(out)

if __name__ == '__main__':
    data = open(sys.argv[1], 'rb').read()
    out = compress(data)
    open(sys.argv[2], 'wb').write(out)
    print(f"compressed {len(data)} -> {len(out)} bytes")
