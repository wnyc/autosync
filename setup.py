#!/usr/bin/env python
"""
autosync
======

A very efficent tool to maintain the one direction synchronization
from a local file system to a remote location.  Will (eventually) work with S3,
Rackspace, rsync and generic http based targets.
"""

from setuptools import setup

setup(
    name='autosync',
    version='0.0.0',
    author='Adam DePrince',
    author_email='adeprince@nypublicradio.org',
    description='Efficent syncronization of the local file system.',
    long_description=__doc__,
    py_modules = [
        "autosync/actors/s3",
        "autosync/actors",
        "autosync/scanners",
        "autosync/scanners/inotify",
        "autosync/daemon",
        ],
    packages = ["autosync"],
    zip_safe=True,
    license='GPL',
    include_package_data=True,
    classifiers=[
        ],
    scripts = [# 'scripts/autosync',
               ],
    url = "https://github.com/wnyc/autosync",
    install_requires = [
        "python-gflags",
        "python-cloudfiles",
        "boto",
        "watchdog"
        ]
)

