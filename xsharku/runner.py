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

from functools import partial
import gevent
from gevent.event import Event, AsyncResult
from gevent.os import make_nonblocking, nb_read, nb_write
from gevent.hub import get_hub
from gevent import subprocess
import json
from pyee import EventEmitter
import os
import os.path
import pwd
import psutil
import re
import logging
from logging.handlers import SysLogHandler
import signal
import sys
import unshare
import procname


class Container(EventEmitter):
    """The virtual machine."""

    def __init__(self, log, clock, script_path, dir, app, name, user):
        EventEmitter.__init__(self)
        self.log = log
        self.clock = clock
        self.script_path = script_path
        self.dir = dir
        self.app = app
        self.name = name
        self.user = user
        self.state = 'init'
        self.runner = None
        
    def start(self, image, config, command):
        self._provision(image)
        self._spawn(config, command)

    def _spawn(self, config, command):
        self.runner = subprocess.Popen([sys.executable, '-m', __name__],
            stdin=subprocess.PIPE) #stdout=subprocess.PIPE,
        #    stderr=subprocess.STDOUT, cwd=self.dir)
        self.runner.rawlink(partial(gevent.spawn, self._child))
        self._set_state('running')
        cmd = {'command': command, 'config': config,
               'app': self.app, 'name': self.name, 'dir': self.dir,
               'user': self.user}
        self.runner.stdin.write(json.dumps(cmd) + '\n')
        self.runner.stdin.close()

    # FIXME: I wish there was a decorator for this in gevent.
    def stop(self):
        def _stop():
            for tosleep in [1, 3, 5]:
                if self.runner is None:
                    break
                self.runner.terminate()
                self.clock.sleep(tosleep)
            else:
                if self.runner is not None:
                    self.runner.kill()
        gevent.spawn(_stop)

    def _set_state(self, state):
        self.log.info("state changed to %r" % (state,))
        self.state = state
        self.emit('state', state)

    def _child(self, popen):
        self.runner = None
        self._set_state('done' if not popen.returncode else 'fail')
        self._cleanup().wait()

    def _provision(self, image):
        script_path = os.path.join(self.script_path, 'provision')
        self._set_state('boot')
        try:
            popen = subprocess.Popen([script_path, str(self.dir), str(image)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=os.getcwd())
            popen.wait()
            # FIXME: xxx, resultcode
        except OSError:
            self.log.exception('fail to spawn provisioning script')
            self._finish('fail')

    def _cleanup(self):
        script_path = os.path.join(self.script_path, 'cleanup')
        return subprocess.Popen([script_path, self.dir])


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


class Runner(object):
    """The runner is responsible for starting the "proc" command
    and monitoring the process.
    """

    def __init__(self, app, name, dir, user, interval=1):
        self.app = app
        self.name = name
        self.dir = dir
        self.user = user
        self._term_event = Event()
        self._process = None
        self._memlimit = None
        self._interval = interval

    def start(self, config, command):
        self.prepare()
        os.chdir(self.dir)
        os.chroot(self.dir)
        # FIXME: or should we get the name before chdir and chroot?
        # change user _after_ we change root.  we do the "getpwnam"
        # inside the jail.
        chuser(self.user)
        self.setup_signals()
        self.execute(command, config)
        return self.monitor()

    def prepare(self):
        # FIXME: we do not really need this I think.
        unshare.unshare(unshare.CLONE_NEWUTS)
        sethostname(self.name)
        dir = os.path.basename(self.dir)
        procname.setprocname("runner[%s]: %s %s" % (dir, self.app,
                                                    self.name))

    def setup_signals(self):
        gevent.signal(signal.SIGTERM, self._term_event.set)
        gevent.signal(signal.SIGINT, self._term_event.set)

    def execute(self, command, environ):
        """Execute the program."""
        environ.update(self._make_environ())
        self.popen = subprocess.Popen(['/bin/bash', '-l', '-c', command],
            env=environ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # start the reader that consumers output from the process and
        # writes it to our log.
        self._log_read = _OutputReader(logging.getLogger('output'), self.name,
                                       self.popen.stdout)

    def monitor(self):
        """Monitor the executed program."""
        while True:
            try:
                event = waitany([self.popen.result, self._term_event],
                                timeout=self._interval)
            except gevent.Timeout:
                self._monitor_usage()
            else:
                if event is self.popen.result:
                    break
                elif event is self._term_event:
                    logging.info("GOT TERM EVENT")
                    self.popen.terminate()
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
        pwnam = pwd.getpwnam(self.user)
        return {
            'TERM': os.getenv('TERM'), 'SHELL': pwnam.pw_shell,
            'USER': pwnam.pw_name, 'LOGNAME': pwnam.pw_name,
            'HOME': pwnam.pw_dir
            }


class _OutputReader(object):
    """Read output from a file."""

    def __init__(self, log, proc_name, file):
        self.log = log
        self.proc_name = proc_name
        self.file = file
        gevent.spawn(self._reader)

    def _reader(self):
        for line in self.file:
            self.log.info(line.strip())


if __name__ == '__main__':
    cmd = json.loads(sys.stdin.readline())
    # setup logging
    program = '%s[%s]' % (cmd['app'], cmd['name'])
    format = "%(asctime)sZ " + program + ": %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=format,
                        datefmt='%Y-%m-%dT%H:%M:%S')
    logging.getLogger('').addHandler(SysLogHandler())
    # fire up the program
    r = Runner(cmd['app'], cmd['name'], cmd['dir'], cmd['user'])
    r.start(cmd['config'], cmd['command'])
