import ctypes, sys

lib = ctypes.CDLL("/usr/lib/x86_64-linux-gnu/libzstd.so.1")
lib.ZSTD_compressBound.restype = ctypes.c_size_t
lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
lib.ZSTD_compress.restype = ctypes.c_size_t
lib.ZSTD_compress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
lib.ZSTD_isError.restype = ctypes.c_uint
lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
lib.ZSTD_decompress.restype = ctypes.c_size_t
lib.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
lib.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
lib.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
lib.ZSTD_maxCLevel.restype = ctypes.c_int

def compress(data: bytes, level: int = 19) -> bytes:
    bound = lib.ZSTD_compressBound(len(data))
    out = ctypes.create_string_buffer(bound)
    ret = lib.ZSTD_compress(out, bound, data, len(data), level)
    if lib.ZSTD_isError(ret):
        raise RuntimeError("ZSTD_compress failed")
    return out.raw[:ret]

def decompress(data: bytes) -> bytes:
    size = lib.ZSTD_getFrameContentSize(data, len(data))
    out = ctypes.create_string_buffer(size)
    ret = lib.ZSTD_decompress(out, size, data, len(data))
    if lib.ZSTD_isError(ret):
        raise RuntimeError("ZSTD_decompress failed")
    return out.raw[:ret]

if __name__ == '__main__':
    mode = sys.argv[1]
    data = open(sys.argv[2], 'rb').read()
    if mode == 'c':
        level = int(sys.argv[4]) if len(sys.argv) > 4 else 19
        out = compress(data, level)
    else:
        out = decompress(data)
    open(sys.argv[3], 'wb').write(out)
    print(f"{mode}: {len(data)} -> {len(out)} bytes")
