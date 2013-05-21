import os.path
import hashlib
from collections import namedtuple


class CmpFiles:

    def __cmp__(self, other):
        if not (hasattr(self, 'mtime') and hasattr(other, 'mtime')):
            return cmp(self.key, other.key) or \
                cmp(self.size, other.size) * 2 or \
                cmp(self.md5, other.md5) * 8
        else:
            return cmp(self.key, other.key) or \
                cmp(self.size, other.size) * 2 or \
                (cmp(self.mtime, other.mtime) * 4)


class File(CmpFiles, namedtuple("File", "name path")):

    __md5 = None

    @property
    def md5(self):
        if self.__md5:
            return self.__md5
        digester = hashlib.md5()
        fh = self.open()
        while True:
            data = fh.read(1024 * 1024)
            if len(data) == 0:
                self.__md5 = digester.hexdigest()
                return self.__md5
            digester.update(data)

    @property
    def size(self):
        return os.stat(self.path).st_size

    @property
    def mtime(self):
        return os.stat(self.path).st_mtime

    def open(self, *args, **kwargs):
        return open(self.path, *args, **kwargs)

    @property
    def key(self):
        return self.name

    def __str__(self):
        return "File(key=%r, size=%r, md5=%r)" % (self.name, self.size, self.md5)


class RemoteFile(CmpFiles, namedtuple("RemoteFile", "key size md5")):
    pass


class RemoteFileWithMtime(CmpFiles, namedtuple("RemoteFileWithMtime", "key size md5 mtime")):
    pass
