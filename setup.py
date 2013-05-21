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
    version='0.0.4',
    author='Adam DePrince',
    author_email='adeprince@nypublicradio.org',
    description='Efficent synchronization of the local file system to S3',
    long_description=__doc__,
    py_modules=[
        "autosync/__init__",
        "autosync/actors/__init__",
        "autosync/actors/s3",
        "autosync/daemon",
        "autosync/files",
    ],
    packages=["autosync"],
    zip_safe=True,
    license='GPL',
    include_package_data=True,
    classifiers=[
    ],
    scripts=[
        'scripts/autosync',
    ],
    url="https://github.com/wnyc/autosync",
    install_requires=[
        "boto",
        "gevent",
        "pyinotify",
        "python-gflags",
    ]
)
