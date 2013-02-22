from collections import namedtuple


class CmdFiles:
    def __eq__(self, other):
        return cmp((self.key, self.size), (other.key, other.size)) \
                   or cmp(self.md5, other.md5)


class File(namedtuple("File", "name path")):

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

    def open(self, mode=None, buffering=None):
        return open(self.path, mode=mode, buffering=buffering)

    @property
    def key(self):
        os.path.join(self.path, self.name)




class RemoteFile(namedtuple("RemoteFile", "key size md5")):
    pass
