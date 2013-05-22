#!/usr/bin/python

import autosync.daemon
import autosync.files
import cloudfiles
import gflags
import json
import os.path
from logging import warn, debug, info

FLAGS = gflags.FLAGS

gflags.DEFINE_string("user", None, "Your rackspace account name")
gflags.DEFINE_string("key", None, "Your rackspace API key")


class RackspaceActor(object):

    def __init__(self, container, prefix):
        debug("Creating RackspaceActor")
        self.cxn = cloudfiles.get_connection(
            FLAGS.user,
            FLAGS.key)
        self.container = self.cxn.get_container(container)
        self.prefix = prefix

    # Boto baggage that is going away in version 0.0.6
    def get_container(self):
        return self

    @staticmethod
    def validate_flags():
        if not FLAGS.user:
            "user required"
        if not FLAGS.key:
            "API key required"

    def list(self):
        # http://trac.cyberduck.ch/ticket/3950
        debug(self.container.list_objects(format='json'))
        items = json.loads(self.container.list_objects(format='json')[0])
        while items:
            for last in items:
                debug(last, last.__class__)
                yield autosync.files.RemoteFile(last['name'], last['bytes'], last['hash'])
            items = json.loads(self.container.list_objects(marker=last,
                               format='json')[0])

    @staticmethod
    def filename(s):
        filename = os.path.join(FLAGS.target_prefix, s)
        return filename

    def upload(self, key):
        o = self.container.create_object(self.filename(key.name))
        o.send(key.open())

    def delete(self, key):
        self.container.delete_object(self.filename(key.key))


if __name__ == "__main__":
    autosync.daemon.main(actor=RackspaceActor)
