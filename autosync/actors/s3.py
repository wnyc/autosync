import os.path
import boto.s3.connection
import boto.s3.key
from boto.exception import S3ResponseError
from boto.s3.key import Key
from autosync.actors import Connection, Container
from autosync.files import RemoteFile

import gflags
FLAGS = gflags.FLAGS


class S3Container(Container):
    def __init__(self, connection, container_name, prefix):
        self.connection = connection
        self.prefix = prefix
        try:
            self.container = self.connection.get_bucket(container_name)
            return
        except S3ResponseError:
            self.container = self.connection.create_bucket(container_name)
            
    def list(self):
        return (RemoteFile(obj.key, obj.size, obj.etag.replace('"', '')) for obj in self.container.list(prefix=self.prefix))

    def delete(self, key):
        self.container.delete_key(key)

    def upload(self, key):
        filename = os.path.join(FLAGS.target_prefix, key.name)
        while filename.startswith('/'):
            filename = filename[1:]
        print key
        k = Key(self.container)
        k.key = filename
        k.set_contents_from_filename(key.path)

        
class Connection(Connection):
    Container = S3Container
    def __call__(self):
        return self.get_container()

    
    def get_connection(self):
        return boto.connect_s3()
        
