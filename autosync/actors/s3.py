
import boto.s3.connection
import boto.s3.key
from boto.exception import S3ResponseError

from autosync.actors import Connection, Container
from autosync.files import RemoteFile


class Container(Container):
    def __init__(self, connection, container_name, prefix):
        self.connection = connection.connection
        self.prefix = prefix
        try:
            self.container = self.connection.get_bucket(container_name)
            return
        except S3ResponseError:
            self.container = self.connection.create_bucket(container_name)
            
    def join(self, name):
        if not prefix:
            return name
        while name.startswith('/'):
            name = name[1:]
        return os.path.join(prefix, name)

    def get_files(self):
        return (RemoteFile(obj.key, obj.etag.replace('"', ''), obj.size)) for obj in self.container.list(prefix=self.prefix))

    def delete(self, key):
        self.container.delete_key(key)

    def upload(self, key):
        filename = self.path.join(FILES.target_prefix, key.name)
        self.container.get_key(key).send_contents_from_filename(file.path)

        
class Connection(Connection):

    def __call__(self):
        return self.get_container()

    
    def get_connection(self):
        return boto.connect_s3()
        
