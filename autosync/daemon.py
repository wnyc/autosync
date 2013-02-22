import select 
from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent
import gevent
from gevent import queue, spawn, joinall
from gevent.queue import Queue
from gevent.monkey import patch_all
import autosync
import autosync.actors
import autosync.actors.s3
from autosync.files import File
import os.path

import gflags

patch_all(select=False)

FLAGS = gflags.FLAGS

gflags.DEFINE_string('target_container', None, 'The remote bucket to write into.  This would be an S3 bucket, rackspace container, rsync host and module or maybe Drive letter in Windows')

gflags.DEFINE_string('target_prefix', '', 'The "directory" within the target to write files into')

gflags.DEFINE_string('source_prefix', None, 'The path to strip from the local file name\' absolute path.   This works like s3cmd\'s -P flag or acts like the current directory would when rsyncing, scping or taring non-absolute paths')

gflags.DEFINE_string('actor', 's3', 'The full name of the module and class use to generate a connection to the target.  So if you created a connection object called my.foobar.Connection yuo would type --actor=my.foobar.Connection.  Moduled included with autosync (i.e. autosync.actors.*.Connection) can be abbreviated with the base module name (i.e. --actor=s3)')

gflags.DEFINE_string('cachefile', None, 'autosync has the ability to cache md5 values and ctimes to speed the initial startup synchronization')

gflags.DEFINE_boolean('start_sync', True, 'Perform an initial scan of all local files and attempt to sync.  If this is set to false autosync will jump directly to its monitoring phase without performing an initial scan.  Setting this option to false could, in the event files are modified while autosync is not running, result in in mismatch between the local and remote files.')

gflags.DEFINE_integer('threads', 100, 'Number of upload threads.  Most operations are I/O, not CPU bound, so feel free to make this very high')


ACTOR_CONNECTION_FACTORIES = {'s3': autosync.actors.s3.Connection}

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
            results.append(i.next())
        except StopIteration:
            results.append(None)
    return results
        

def merge(iter_a, iter_b, func_a, func_b, func_both):
    next_a, next_b = next(iter_a, iter_b)
    while True:
        if not all((next_a, next_b)): 
            break
        if next_a.key < next_b.key:
            func_a(next_a)
            next_a = next(iter_a)[0]
            continue
        if next_a.key > next_b.key:
            func_b(next_b)
            next_b = next(iter_b)[0]
            continue
        if next_a.size != next_b.size:
            if next_a.md5 != next_b.md5:
                func_both(next_a)
        next_a, next_b = next(iter_a, iter_b)

    
    while next_a:
        next_a = next(iter_a)[0]
        if next_a: func_a(next_a)
    
    while next_b:
        next_b = next(iter_b)[0]
        if next_b: func_b(next_b)



class State(object):
    def __init__(self, actor, files, prefix, que):
        self.files = files
        self.actor = actor
        self.local_que = Queue()
        self.que = que
        self.prefix = prefix

    def upload(self, key):
        self.que.put(('u', key))
        
    def delete(self, key):
        self.que.put(('d', key))
                
    def filename_to_File(self, path):
        path = os.path.abspath(path)
        name = path
        if name.startswith(self.prefix):
            name = name[len(self.prefix):]
        while name.startswith('/'):
            name = name[1:]
        return File(name, path)


class SyncState(State):

    def add_path_to_que(self, path):
        self.local_que.put(self.filename_to_File(path))
        
    def walker(self,_ , dirname, fnames):
        fnames.sort()
        for fname in fnames:
            fname = os.path.join(dirname, fname)
            if os.path.isfile(fname):
                self.add_path_to_que(fname)

    def walker_thread(self, sources):
        for source in sources:
            source = os.path.abspath(source)
            if os.path.isfile(source):
                self.add_path_to_que(fname)
            else:
                os.path.walk(source, self.walker, None)
        self.local_que.put(None)

    def run(self):
        self.walker_job = spawn(self.walker_thread, self.files)
        merge(iter(sorted(iterify_queue(self.local_que))), 
              iter(sorted(self.actor.list())),
              self.upload, self.delete, self.upload)
        joinall((self.walker_job,))


class TrackState(State, ProcessEvent):
    mask = EventsCodes.OP_FLAGS['IN_DELETE'] | EventsCodes.OP_FLAGS['IN_CREATE'] | EventsCodes.OP_FLAGS['IN_MODIFY']

    def __init__(self, *args, **kwargs):
        State.__init__(self, *args, **kwargs)
        self.wm = WatchManager()
        self.notifier = Notifier(self.wm, self)

    def process_IN_CREATE(self, event):
        path = os.path.join(event.path, event.name)
        if os.path.isfile(path):
            self.upload(self.filename_to_File(path))
        elif os.path.isdir(path):
            self.wm.add_watch(path, self.mask, rec=True)

    def process_IN_MODIFY(self, event):
        path = os.path.join(event.path, event.name)
        if os.path.isfile(path):
            self.upload(self.filename_to_File(path))

    def process_IN_DELETE(self, event):
        path = os.path.join(event.path, event.name)
        self.delete(self.filename_to_File(path))
    
    def run(self):
        for f in self.files:
            f = os.path.abspath(f)
            self.wm.add_watch(f, self.mask, rec=True)
        try:
            while True:
                self.notifier.process_events()
                if self.notifier.check_events(100):
                    self.notifier.read_events()
                gevent.sleep(0)
        except KeyboardInterrupt:
            self.notifier.stop()

        
        
class Uploader(object):
    def __init__(self, actor_factory, argv, source_prefix):
        self.argv = argv
        self.source_prefix = source_prefix
        self.actor_factory = actor_factory
        self.que = Queue()
        
    def run(self):
        trackstate = TrackState(self.actor_factory(), self.argv, self.source_prefix, self.que)
        syncstate = SyncState(self.actor_factory(), self.argv, self.source_prefix, self.que)

        for x in range(FLAGS.threads):
            yield spawn(self.uploader_thread, self.actor_factory)

        syncstate.run()
        trackstate.run()
            
    def uploader_thread(self, actor_factory):
        actor = actor_factory()
        while True:
            task, key = self.que.get()
            if task == 'd':
                try:
                    actor.delete(key)
                except (OSError, IOError):
                    pass
            elif task == 'u':
                try:
                    actor.upload(key)
                except (OSError, IOError):
                    pass


def main(argv = None, stdin = None, stdout=None, stderr=None):
    import sys
    argv = argv or sys.argv
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    
    try:
        argv = FLAGS(argv)[1:]
    except gflags.FlagsError, e:
        print >>stderr, "%s\\nUsage: %s ARGS\\n%s" % (e, sys.argv[0], FLAGS)
        return 1

    def actor_factory():

        actor = ACTOR_CONNECTION_FACTORIES[FLAGS.actor]
        actor = actor(FLAGS.target_container, FLAGS.target_prefix)
        return actor.get_container()

    uploader = Uploader(actor_factory, argv, FLAGS.source_prefix)
    threads = list(uploader.run())

    joinall(threads)
        
    





