import sys, os, stat

def pad4(n):
    return (4 - n % 4) % 4

def header(name, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor,
           rdevmajor, rdevminor, ino, check=0):
    namesize = len(name.encode()) + 1
    fields = [ino, mode, uid, gid, nlink, mtime, filesize,
              devmajor, devminor, rdevmajor, rdevminor, namesize, check]
    h = b'070701' + b''.join(b'%08X' % (v & 0xFFFFFFFF) for v in fields)
    h += name.encode() + b'\x00'
    h += b'\x00' * pad4(len(h))
    return h

def walk_manual(srcdir):
    def rec(rel):
        full = os.path.join(srcdir, rel) if rel else srcdir
        names = sorted(os.listdir(full))
        for name in names:
            child_rel = name if not rel else rel + '/' + name
            child_full = os.path.join(full, name)
            st = os.lstat(child_full)
            if stat.S_ISLNK(st.st_mode):
                yield (child_rel, 'symlink', child_full)
            elif stat.S_ISDIR(st.st_mode):
                yield (child_rel, 'dir', child_full)
                yield from rec(child_rel)
            elif stat.S_ISREG(st.st_mode):
                yield (child_rel, 'file', child_full)
            else:
                continue
    yield from rec('')

def pack(srcdir, outpath):
    out = open(outpath, 'wb')
    ino = 300000
    count = 0
    for rel, kind, full in walk_manual(srcdir):
        st = os.lstat(full)
        ino += 1
        if kind == 'symlink':
            target = os.readlink(full)
            data = target.encode()
            mode = stat.S_IFLNK | 0o777
            out.write(header(rel, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, ino))
            out.write(data)
            out.write(b'\x00' * pad4(len(data)))
        elif kind == 'dir':
            mode = stat.S_IFDIR | (st.st_mode & 0o7777 or 0o755)
            out.write(header(rel, mode, 0, 0, 2, 0, 0, 0, 0, 0, 0, ino))
        elif kind == 'file':
            with open(full, 'rb') as f:
                data = f.read()
            mode = stat.S_IFREG | (st.st_mode & 0o7777 or 0o644)
            out.write(header(rel, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, ino))
            out.write(data)
            out.write(b'\x00' * pad4(len(data)))
        count += 1
    out.write(header('TRAILER!!!', 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0))
    out.close()
    print(f"packed {count} entries into {outpath}")

if __name__ == '__main__':
    pack(sys.argv[1], sys.argv[2])
