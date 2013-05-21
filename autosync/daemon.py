import select 
from pyinotify import WatchManager, Notifier, ThreadedNotifier, EventsCodes, ProcessEvent
import autosync
import autosync.actors
import autosync.actors.s3
from autosync.files import File
import os.path
import re
import gflags
import signal

FLAGS = gflags.FLAGS

gflags.DEFINE_string('target_container', None, 'The remote bucket to write into.  This would be an S3 bucket, rackspace container, rsync host and module or maybe Drive letter in Windows')

gflags.DEFINE_string('target_prefix', '', 'The "directory" within the target to write files into')

gflags.DEFINE_string('encoding', 'utf-8', 'Encoding to use for filenames')

gflags.DEFINE_string('source_filter', '^.*$', 'Only accept files that match this regex')

gflags.DEFINE_string('source_exclude', None, 'Reject files that match this regex')

gflags.DEFINE_string('source_prefix', None, 'The path to strip from the local file name\' absolute path.   This works like s3cmd\'s -P flag or acts like the current directory would when rsyncing, scping or taring non-absolute paths')

gflags.DEFINE_string('actor', 's3', 'The full name of the module and class use to generate a connection to the target.  So if you created a connection object called my.foobar.Connection yuo would type --actor=my.foobar.Connection.  Moduled included with autosync (i.e. autosync.actors.*.Connection) can be abbreviated with the base module name (i.e. --actor=s3)')

gflags.DEFINE_string('cachefile', None, 'autosync has the ability to cache md5 values and ctimes to speed the initial startup synchronization')

gflags.DEFINE_boolean('start_sync', True, 'Perform an initial scan of all local files and attempt to sync.  If this is set to false autosync will jump directly to its monitoring phase without performing an initial scan.  Setting this option to false could, in the event files are modified while autosync is not running, result in in mismatch between the local and remote files.')

gflags.DEFINE_integer('threads', 100, 'Number of upload threads.  Most operations are I/O, not CPU bound, so feel free to make this very high')

gflags.DEFINE_enum('threader', 'gevent', ['thread', 'gevent'], "Select threading module")


ACTOR_CONNECTION_FACTORIES = {'s3': autosync.actors.s3.Connection}

def spawn(func, *args, **kwargs):
    if FLAGS.threader=='gevent':
        import gevent
        return gevent.spawn(func, *args, **kwargs)
    if FLAGS.threader=='thread':
        import thread
        lock = thread.allocate_lock()
        def join_emulator(func, lock, *args, **kwargs):
            func(*args, **kwargs)
            lock.release()

        lock.acquire(True)

        args = (func, lock) + tuple(args)
        thread.start_new_thread(join_emulator, args, kwargs)
        return lock

def sleep(seconds=0):
    if FLAGS.threader=='gevent':
        import gevent
        return gevent.sleep(seconds)
    if FLAGS.threader=='thread':
        import time
        return time.sleep(seconds)

def Queue(*args, **kwargs):
    if FLAGS.threader=='gevent':
        import gevent.queue
        return gevent.queue.Queue(*args, **kwargs)
    if FLAGS.threader=='thread':
        import Queue
        return Queue.Queue(*args, **kwargs)

def joinall(locks):
    if FLAGS.threader == 'gevent':

        import gevent
        return gevent.joinall(locks)
    if FLAGS.threader=='thread':
        for lock in locks:
            while not lock.acquire(False):
                import time
                time.sleep(1000)
            lock.release()
        return

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
    while all((next_a, next_b)):
        if next_a.key < next_b.key:
            print "Uploading: ",next_a.key
            func_a(next_a)
            next_a = next(iter_a)[0]
            continue
        if next_a.key > next_b.key:
            print "Deleting: ", next_b.key
            func_b(next_b)
            next_b = next(iter_b)[0]
            continue
        if next_a.size != next_b.size:
            if next_a.mtime != next_b.mtime:
                func_both(next_a)
        else:
            print "Doing nothing"
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
        self.RE = re.compile(FLAGS.source_filter)
        if FLAGS.source_exclude:
            self.EXCLUDE = re.compile(FLAGS.source_exclude)
        else:
            self.EXCLUDE = None

    def acceptable(self, s):
        if not self.RE.match(s):
            print "not acceptable:", s
            return False
        if not self.EXCLUDE:
            print "acceptable:", s
            return True
        ret = not self.EXCLUDE.match(s)
        if ret:
            print "acceptable:", s
        else:
            print "not acceptable:", s
        return ret

    def upload(self, key):
        item = ('u', key)
        print "Queing: ", item
        self.que.put(item)
        
    def delete(self, key):
        item = ('d', key)
        print "Queing: ", item
        self.que.put(item)
                
    def filename_to_File(self, path):
        path = os.path.abspath(path)
        name = path
        if self.prefix:
            if name.startswith(self.prefix):
                name = name[len(self.prefix):]
        f = File(name, path)
        return f


class SyncState(State):
    RE = None

    def add_path_to_que(self, path):
        if self.acceptable(path):
            try:
                if FLAGS.encoding:
                    path = path.encode(FLAGS.encoding)
            except:
                print "Failed to encode", FLAGS.encoding
                return 
            try:
                self.local_que.put(self.filename_to_File(path))
            except:
                print "Failed to upload ", path
        
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
                self.add_path_to_que(source)
            else:
                os.path.walk(source, self.walker, None)
        self.local_que.put(None)
        print "Walker thread done"

    def run(self):
        self.walker_job = spawn(self.walker_thread, self.files)
        # joinall((self.walker_job,))
        merge(iter(sorted(iterify_queue(self.local_que), key=lambda x:x.key)), 
              iter(sorted(self.actor.list(), key=lambda x:x.key)),
              self.upload, self.delete, self.upload)


class TrackState(State, ProcessEvent):
    mask = EventsCodes.OP_FLAGS['IN_DELETE'] | EventsCodes.OP_FLAGS['IN_CLOSE_WRITE'] 

    def __init__(self, *args, **kwargs):
        State.__init__(self, *args, **kwargs)
        self.wm = WatchManager()
        self.notifier = Notifier(self.wm, self)

    def process_IN_CLOSE_WRITE(self, event):
        print "IN_CLOSE_WRITE:", event
        path = os.path.join(event.path, event.name)
        if os.path.isfile(path) and self.acceptable(path):
            self.upload(self.filename_to_File(path))

    def process_IN_DELETE(self, event):
        print "IN_DELETE:", event
        path = os.path.join(event.path, event.name)
        if self.acceptable(path):
            self.delete(self.filename_to_File(path))
    
    def run(self):
        for f in self.files:
            f = os.path.abspath(f)
            self.wm.add_watch(f, self.mask, rec=True, auto_add=True)
        try:
            while True:
                self.notifier.process_events()
                if self.notifier.check_events(100):
                    self.notifier.read_events()
                sleep(0)
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

        yield spawn(trackstate.run)
        yield spawn(syncstate.run)
        for x in range(FLAGS.threads):
            yield spawn(self.uploader_thread, self.actor_factory)
            
    def uploader_thread(self, actor_factory):
        actor = actor_factory()
        while True:
            task, key = self.que.get()
            print "Worker thread received: ", task, key
            if task == 'd':
                try:
                    actor.delete(key)
                except (OSError, IOError):
                    pass
            elif task == 'u':
                try:
                    if actor.upload(key):
                        self.que.put((task, key))
                except (OSError, IOError):
                    pass


def main(argv = None, stdin = None, stdout=None, stderr=None, actor=None):

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
    if FLAGS.threader == 'gevent':
        import gevent.monkey
        gevent.monkey.patch_all(select=False)

    def actor_factory(actor=actor):
        error = actor.validate_flags()
        if error:
            print >>stderr, "%s\nUsage: %s ARGS\\n%s" % (error, sys.argv[0], FLAGS)
        if not actor:
            if FLAGS.actor in ACTOR_CONNECTION_FACTORIES:
                actor = ACTOR_CONNECTION_FACTORIES[FLAGS.actor]
            else:
                eval("from %s import %s as actor" % (".".join(actor.split(".")[:-1]), actor.split(".")[-1]))
        return actor(FLAGS.target_container, FLAGS.target_prefix).get_container()


    uploader = Uploader(actor_factory, argv, FLAGS.source_prefix)
    threads = list(uploader.run())


    try:
        joinall(threads)
        
    except KeyboardInterrupt:
        pass
            
        
    





