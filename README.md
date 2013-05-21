
I thought I'd take a moment and share a tool I built to solve common problems faced both in the WAAA project and the datanews team.  

Copying filesystems from point A to point B is a common problem in the computer world.  Its common enough that endless tools have been created to solve this problem ... rsync, cp, tar, zip ... there are dozens if not hundreds of tools. 

When copying things from a local file system to Amazon S3 the most common tool is one of the many variations on s3cmp - there are numerous forks and translations to other languages.  

The problem with all of these tools is they all command driven - we compel them to make a single pass across the filesystem and exit.    In at least two places, datanews and WAAA, we have a workflow that looks something like this:

1. Dump the file into a file system
2. Push the file system someplace else 

In both these cases the traditional approach was to run the copy and synchronization tool from within cron.   And in both these cases we suffered the problem with doing that - long delays between invocations to cron and the risk that if the process requires more than the cron interval to execute multiple instances will pile up and bring the machine down as happened to project about two months ago. 

AUTOSYNC

To solve this problem I created an extensible tool called "autosync."   It scans a source directory, a target repository, copies the files and then hangs around and makes sure changes to the source are reflected in the target.   It a little bit like doing this:

while true; do rsync ... ;done

Kinda like.  Except way more efficient.   It uses Linux's inotify infrastructure to track changes to it doesn't need to scan your file system constantly.    It uses gevents and Queues for internal communication to ensure that the flow of data from point A to point B is unimpeded by communication latency.  

So you are probably wondering at this point why I created this when there are wonderful solutions like watchdog.  First, it's been a personal annoyance for years -  since the creation of Amazon S3 I've found myself doing the same thing over and over again.   Secondly I've never incorporated all of the things I've wished for in one place.   I want threads - when uploading files to Amazon your delays are usually round trip latency.   Keeping more files in flight at once improves your network utilization.  I also want inotify.  And configurability.   And to not write the same peice of code over and over again like I have for the last 6 or 7 years.  Lastly, I'm impatient.  Autosync gets threads right; when uploading to S3 its fast, far faster than s3cmd.  

First I'd like to share with you how autosync is configured on the command line, and then I'll share how to extend autosync.  For these examples I'm going to use real life configurations and code that we're deploying or have deployed here at WNYC.


The concepts.

One of the most important concepts to keep track of when configuring autosync is the "source_prefix".   Folks who use s3cp a lot will already know about the -P flag, but I'll review it anyway.  

Lets imagine you had a directory structure hanging off of your root directory that looks like this:

/home/adeprince/mystuff/1
/home/adeprince/mystuff/a/2
/home/adeprince/mystuff/a/b/3
/home/adeprince/mystuff/c/4

If you type this:

# cd 
# tar -cvzf mystuff.tar.gz mystuff

you will create a tar file laid out like this:

mystuff/1
mystuff/a/2
mystuff/a/b/3
mystuff/c/4

But if you type this instead:

# cd ~/mystuff
# tar -cvzf mystuff.tar.gz * 

you will create a tar file with a layout that looks like this:

1
a/2
a/b/3
c/4

With tar and zip the currect directory defines the root of your tree.


In autosync this root is made explicit.  When running autosync if you say:

autosync mystuff

the resulting tree structure will look this: 

/home/adeprince/mystuff/1
/home/adeprince/mystuff/a/2
/home/adeprince/mystuff/a/b/3
/home/adeprince/mystuff/c/4

Probably not what you want.

To stop this you add what is called a "source prefix".   So if you say:

$ autosync --source_prefix="/home/" mystuff

the resulting file system will look like this:

adeprince/mystuff/1
adeprince/mystuff/a/2
adeprince/mystuff/a/b/3
adeprince/mystuff/c/4

You can get the same automatic behavior of more traditional tools; if you are working from bash you might say:

autosync --source_prefix=$PWD/mystuff/ mystuff

which will give you a file layout that looks like this

1
a/2
a/b/3
c/4

Note the trailing slash.  If you omit the trailing slash and write: 

autosync --source_prefix=$PWD/mystuff/ mystuff

which will give you a file layout that looks like this

/1
/a/2
/a/b/3
/c/4

Depending on your backend this could mean something very different.  It doesn't matter for S3, but it does for WAAA because inside of puppy these values might be passed to os.pathjoin and used to generate urls.   If the second parameter in os.path.join starts with a /, the first parameter is omitted.   So:

>>> import os.path
>>> os.path.join('a', 'b') 
'a/b'
>>> os.path.join('a', '/b') 
'/b'

Don't accidentally convert something to an absolute path if you don't mean to. 

While you might not want your files to be in the /home/adeprince directory on S3, you might also not want them to be in the root directory.  No problem, autosync also supports target prefixes.  These are added to the front of your path, so if you said:

autosync --source_prefix=$PWD/mystuff/ --target-prefix=/foo/bar/ mystuff

your file structure would look like this

/foo/bar/1
/foo/bar/a/2
/foo/bar/a/b/3
/foo/bar/c/4

Command line parameters

With that out of the way the rest of autosync's command line parameters are very straight forward:

The first to know is the actor parameter.   This specifies the type of target you are writing files into.  As of this time only S3 is supported (rackspace will be in version 0.0.6), but that's okay because informally extending autosync is really easy.   

 --actor: The full name of the module and class use to generate a connection to the target. So if you created a connection object called my.foobar.Connection you would type --actor=my.foobar.Connection. Moduled included with autosync (i.e. autosync.actors.*.Connection) can be abbreviated with the base module name (i.e. --actor=s3) (default: 's3')

The next parameter is source filter.  This is a python compatible regex that defines which file names are acceptable.  By default, everything in the target path is accepted. 

 --source_filter: Only accept files that match this regex  (default: '^.*$')

Next we go to target_container.   Most backend systems have some notion of drives, containers, buckets, repos - whatever its called, it goes into this parameter. 

 --target_container: The remote bucket to write into. This would be an S3 bucket, rackspace container, rsync host and module or
    maybe Drive letter in Windows

Lastly we have the number of concurrent threads you will alow the system to create.   More threads mean more opportunity to overlap communication and keep the pipe full, but they consume resources.    The default value of 100 is pretty aggressive and seems to work well. 

 --threads: Number of upload threads. Most operations are I/O, not CPU bound, so feel free to make this very high
    (default: '100')

autosync uses boto for its S3 API, so S3 credentials are stored in ~/.boto.  Eventually there will be parameters here to set this as well. 

Lastly are the file names.  Unlike cp or rsync, autosync does not have a -r flag.  It assumes you always want to recursively visit all of the sub directories.   I might change this in the future, but its how it works right now.

Now lets look at a real life installation.   The following is the exact command line used by the WAAA project:

$ python ~adeprince/media_file_actor.py --url=http://dev.wnyc.net:7654/api/v1/media_files --secret='fuzzy puppies make me smile in the sunshine' --source_prefix=/home/DAVID/audio/audioroot/main/ --threads=1 --source_filter="^.*[mM][pP]3$" /home/DAVID/audio/audioroot/main/

Whoa, wait, its different?  Yes.  That's right, this example doesn't use the s3 actor, it uses the media_file_actor which we'll walk through the process of building together in the next session.  But we can still understand most of what's happening.

--url=http://dev.wnyc.net:7654/api/v1/media_files is the url address to which files should be written.  
--secret='fuzzy puppies make me smile in the sunshine' is the hmac secret key for authenticated these requests
--source_prefix=/home/DAVID/audio/audioroot/main/ describes the prefix that should be removed from the front of the file name.  Note the trailing /, Elizabeth specifically adnomished me not to leave the leading / on the names, so I had to add this. 
--threads=1 This is our prod server, not Amazon's.  Be gentle.
--source_filter="^.*[mM][pP]3$"  We only want mp3 files.

/home/DAVID/audio/audioroot/main/ The path files are retrieved from.  

Extending autosync

Now lets look at how autosync is extended.    There there three steps to extending autosync:

Configuration parameters.

You want autosync's main method to know about any parameters that might be specific to your application.  Fortunately gflags make this really painlessly easy.  

Recall in the above example we need to add two additional parameters beyond the defaults in autosync: url and secret.  To do this we write:

import gflags

FLAGS = gflags.FLAGS

gflags.DEFINE_string('url', None, 'Base url to connect to (i.e. www.wnyc.org/api/v1/media_file')
gflags.DEFINE_string('secret', None, 'Secret API key')


Now the next step is to create a a class that implements the autosync actor interface.     This interface requires three methods:

list returns a generator that produces autosync.files.File compatible objects describing what's already in your datastore.    Recall autosync is threaded -- if this data is sorted by primary key autosync is able to perform a merge and determine which files need to be added or removed before the download of file listings is complete.   To indicate this the returned generate should have an attribute called already_sorted and it should be true. 

delete accepts a single parameter, key, that is also a File compatible object.  The primary key of the object to delete is in key.key

upload accepts a single parameter, key, that is also a File compatible object.   This is used to indicate that the file should be created or updated.  

From this email I omit the complete implementation of meda_file_actor.py's MediaFileActor class, but you are welcome to look in puppy/scripts.

Lastly you need to "register" your actor with autosync and run autosync.   You do this with the following code snippet: 

if __name__ == "__main__":
    main(actor=MediaFileActor)
