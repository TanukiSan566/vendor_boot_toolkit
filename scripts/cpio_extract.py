import sys, os, struct

def extract(cpio_path, outdir):
    data = open(cpio_path, 'rb').read()
    off = 0
    n = len(data)
    count = 0
    os.makedirs(outdir, exist_ok=True)
    while off < n:
        magic = data[off:off+6]
        if magic != b'070701':
            break
        fields = data[off+6:off+6+13*8]
        vals = [int(fields[i*8:i*8+8], 16) for i in range(13)]
        (ino, mode, uid, gid, nlink, mtime, filesize,
         devmajor, devminor, rdevmajor, rdevminor, namesize, check) = vals
        name_off = off + 6 + 13*8
        name = data[name_off:name_off+namesize-1].decode(errors='replace')
        if name == 'TRAILER!!!':
            break
        file_data_off = name_off + namesize
        # pad to 4-byte boundary from start of header
        pad = (4 - (file_data_off - off) % 4) % 4
        file_data_off += pad
        filedata = data[file_data_off:file_data_off+filesize]
        is_dir = (mode & 0o170000) == 0o040000
        is_symlink = (mode & 0o170000) == 0o120000
        target = os.path.join(outdir, name)
        if name and not name.startswith('..'):
            if is_dir:
                os.makedirs(target, exist_ok=True)
                try:
                    os.chmod(target, mode & 0o7777)
                except Exception:
                    pass
            elif is_symlink:
                os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
                try:
                    if os.path.lexists(target):
                        os.remove(target)
                    os.symlink(filedata.decode(errors='replace'), target)
                except Exception:
                    pass
            else:
                os.makedirs(os.path.dirname(target) or '.', exist_ok=True)
                with open(target, 'wb') as f:
                    f.write(filedata)
                try:
                    os.chmod(target, mode & 0o7777)
                except Exception:
                    pass
        count += 1
        next_off = file_data_off + filesize
        pad2 = (4 - next_off % 4) % 4
        off = next_off + pad2
    print(f"extracted {count} entries from {cpio_path} into {outdir}")

if __name__ == '__main__':
    extract(sys.argv[1], sys.argv[2])
