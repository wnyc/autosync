from gevent import queue, spawn, join
from gevent.queue import Queue, QueueEmpty
from autosync.files import File

import gflags
FLAGS = gflags.FLAGS

gflags.DEFINE_string('target_container', None, 'The remote bucket to write into.  This would be an S3 bucket, rackspace container, rsync host and module or maybe Drive letter in Windows')

gflags.DEFINE_string('target_prefix', '', 'The "directory" within the target to write files into')

gflags.DEFINE_string('source_prefix', None, 'The path to strip from the local file name\' absolute path.   This works like s3cmd\'s -P flag or acts like the current directory would when rsyncing, scping or taring non-absolute paths')

gflags.DEFINE_string('actor', 's3', 'The full name of the module and class use to generate a connection to the target.  So if you created a connection object called my.foobar.Connection yuo would type --actor=my.foobar.Connection.  Moduled included with autosync (i.e. autosync.actors.*.Connection) can be abbreviated with the base module name (i.e. --actor=s3)')

gflags.DEFINE_string('cachefile', None, 'autosync has the ability to cache md5 values and ctimes to speed the initial startup synchronization')

gflags.DEFINE_boolean('start_sync', True, 'Perform an initial scan of all local files and attempt to sync.  If this is set to false autosync will jump directly to its monitoring phase without performing an initial scan.  Setting this option to false could, in the event files are modified while autosync is not running, result in in mismatch between the local and remote files.')

gflags.DEFINE_boolean('threads', 100, 'Number of upload threads.  Most operations are I/O, not CPU bound, so feel free to make this very high')


ACTOR_CONNECTION_FACTORIES = {'s3': autosync.actor.s3.Connection}

def usage():
    print "autosync: source-file, [source-file]..."

def iterify_queue(q):
    while True:
        next = q.get()
        if not next: break
        yield next

def next(*iters):
    results = []
    for i in iters:
        try:
            results.append(i.net())
        except StopIteration():
            results.append(None)
    return results
        

def merge(iter_a, iter_b, func_a, func_b, func_both):
    next_a, next_b = next(iter_a, iter_b)
    while True:
        if not all((next_a, next_b)): 
            break
        if next_a.key < next_b.key:
            func_a(next_a)
            next_a = next(iter_a)
            continue
        if next_a.key > next_b.key:
            func_b(next_b)
            next_b = next(iter_b)
            continue
        if next_a != next_b:
            func_a(next_a))
        next_a, next_b = next(iter_a, iter_b)

    
    while next_a:
        next_a = next(iter_a)
        if next_a: func_a(next_a)
    
    while next_b:
        next_b = next(iter_b)
        if next_b: func_b(next_b)

        

class SyncState(object):

    def add_path_to_que(self, path):
        path = os.path.abspath(path)
        name = path
        if name.startswith(self.prefix):
            name = name[len(self.prefix):]
        while name.startswith('/'):
            name = name[1:]
        self.local_que.put(File(name, path))

    @staticmethod
    def walker(self, args , dirname, fnames):
        fnames.sort()
        for fname in fnames:
            fname = os.path.join(dirname, fname)
            if os.path.isfile(fname):
                self.add_path_to_que(fname)

    def walker_thread(self, sources, local_que):
        for source in sources:
            source = os.path.abspath(source)
            if os.path.isfile(source):
                self.add_path_to_que(fname)
            else:
                walker(source, self.walker, local_que)
        local_que.put(None)

    def __init__(self, actor, files, prefix, upload_que, delete_que):
        self.files = files
        self.actor = actor
        self.local_que = queue()
        self.upload_que = upload_que
        self.delete_que = delete_que
        
        
    def upload(self, key):
        self.que.put(('u', key))
        
    def delete(self, key):
        self.que.put(('d', key))

    def run(self):
        self.walker_job = spawn(walker_thread, files, self.local_que)
        merge(iterify_queue(self.local_que), 
              self.actor.list(),
              self.upload, self.delete)
        join(self.walker_job)


class Uploader(object):
    def __init__(self, actor_factory, source_prefix):
        self.actor_factory = actor_factory
        self.que = queue()

    def run(self):
        SyncState(self.actor_factory(), argv, source_prefix, que).run()
        for x in range(FLAGS.threads):
            spawn(self.uploader_thread, self.actor_factory)

    def uploader_thread(self, actor_factory):
        actor = actor_factory()
        while True:
            task, key = que.get()
            if task == 'd':
                actor.delete(key)
            elif task == 'u':
                actor.upload(key)


def main(argv = None, stdin = None, stdout=None, stderr=None):
    import sys
    argv = argv or sys.argv
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr

    try:
        FLAGS(argv)[1:]
    except gflags.FlagsError, e:
        print >>syderr, "%s\\nUsage: %s ARGS\\n%s" % (e, sys.argv[0], FLAGS)
        return 1

    Uploader(ACTOR_CONNECTION_FACTORIES[FLAGS.actor].Container(FLAGS.target_container, 
             FLAGS.source_prefix)





