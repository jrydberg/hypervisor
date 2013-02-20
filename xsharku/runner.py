# Copyright 2013 Johan Rydberg.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""App proc runner that takes care for isolation and possibly in the
future logging and metrics.

Usage: gilliam-runner [options] <DIR> [--] <COMMAND> [<ARGS>...]

Options:
    -h, --help         Display this help text and exit.
    --name NAME        Name of the container.
    --user USER        Change to USER before starting command.
    --env ENV          Read environment variables from ENV
    --memlimit LIMIT   Kill process if memory limit is exceeded.
"""

from docopt import docopt
import gevent
from gevent.event import Event, AsyncResult
from gevent import subprocess
import os
import pwd
import psutil
import re
import signal
import unshare


# FIXME: This is for Ubuntu only and only tested on 12.04 LTS
def sethostname(hostname):
    """Set hostname to C{hostname}."""
    from ctypes import CDLL
    libc = CDLL('libc.so.6')
    libc.sethostname(hostname, len(hostname))


def waitany(objects, timeout=None):
    """Wait for that any of the objects are triggered."""
    result = AsyncResult()
    for obj in objects:
        obj.rawlink(result.set)
    try:
        return result.get(timeout=timeout)
    finally:
        for obj in objects:
            unlink = getattr(obj, 'unlink', None)
            if unlink:
                try:
                    unlink(result.set)
                except:
                    raise


def chuser(user):
    """Change user to whatever was specified."""
    pwnam = pwd.getpwnam(user)
    os.setgid(pwnam.pw_gid)
    os.setegid(pwnam.pw_gid)
    os.setuid(pwnam.pw_uid)
    os.seteuid(pwnam.pw_uid)
    os.chdir(pwnam.pw_dir)


def parse_limit(limit):
    suffixes = {'k': 1024, 'm': 1024*1024,
                'g': 1024*1024*1024}
    m1 = re.match(r'\A([0-9]+)([mMkKgG])\Z', limit)
    return int(m1.group(1)) * suffixes[m1.group(2).lower()]


class Runner(object):
    """Runner."""

    def __init__(self, name, dir, user=None, envfile=None, memlimit=None):
        self.name = name
        self.dir = dir
        self.user = user
        self.envfile = envfile
        self._term_event = Event()
        self._process = None
        self._memlimit = parse_limit(memlimit) if memlimit else None
    
    def run(self, args):
        self.prepare()
        environ = self._read_env() if self.envfile else {}
        os.chdir(self.dir)
        os.chroot(self.dir)
        # change user _after_ we change root.  we do the "getpwnam"
        # inside the jail.
        if self.user:
            chuser(self.user)
        self.setup_signals()
        self.execute(args, environ)
        return self.monitor()

    def prepare(self):
        unshare.unshare(unshare.CLONE_NEWUTS)
        sethostname(self.name)

    def setup_signals(self):
        gevent.signal(signal.SIGTERM, self._term_event.set)
        gevent.signal(signal.SIGINT, self._term_event.set)

    def execute(self, args, environ):
        """Execute the program."""
        environ.update(self._make_environ())
        print [repr(a) for a in args]
        self.popen = subprocess.Popen(['/bin/bash', '-l', '-c',
                                       ' '.join(args)], env=environ)

    def monitor(self):
        """Monitor the executed program."""
        while True:
            try:
                event = waitany([self.popen.result, self._term_event],
                                timeout=1)
            except gevent.Timeout:
                self._monitor_usage()
            else:
                if event is self.popen.result:
                    break
                elif event is self._term_event:
                    break

    def _monitor_usage(self):
        if self._process is None:
            self._process = psutil.Process(self.popen.pid)
        meminfo = self._process.get_memory_info()
        if self._memlimit and self._memlimit > meminfo.rss:
            # Kill the proc ; it is exceeding the memory limit and we
            # do not want that do we?
            return True

    def _make_environ(self):
        """Construct an environment for the app."""
        environ = {}
        if not self.user:
            for key in ('TERM', 'SHELL', 'USER', 'LOGNAME', 'HOME'):
                environ[key] = os.getenv(key)
        else:
            pwnam = pwd.getpwnam(self.user)
            environ.update({
                'TERM': os.getenv('TERM'), 'SHELL': pwnam.pw_shell,
                'USER': pwnam.pw_name, 'LOGNAME': pwnam.pw_name,
                'HOME': pwnam.pw_dir
                })
        return environ

    def _parse_env_line(self, line):
        m1 = re.match(r'\A([A-Za-z_0-9]+)=(.*)\Z', line)
        key, val = m1.group(1), m1.group(2)
        m2 = re.match(r"\A'(.*)'\Z", val)
        if m2:
            val = m2.group(1)
        m3 = re.match(r'\A"(.*)"\Z', val)
        if m3:
            val = re.sub(r'\\(.)', r'\1', m3.group(1))
        return key, val

    def _read_env(self):
        with open(self.envfile) as fp:
            return dict(self._parse_env_line(line.rstrip())
                        for line in fp)


def main():
    options = docopt(__doc__)
    runner = Runner(options['--name'] or 'unknown',
                    options['<DIR>'], user=options['--user'],
                    envfile=options['--env'],
                    memlimit=options['--memlimit'])
    runner.run([options['<COMMAND>']] + options['<ARGS>'])


if __name__ == '__main__':
    main()
