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
from urlparse import urlparse
import procname
import socket
import time
import uuid


class Container(EventEmitter):
    """The virtual machine."""

    def __init__(self, log, clock, script_path, id, app, name):
        EventEmitter.__init__(self)
        self.log = log
        self.clock = clock
        self.script_path = script_path
        self.app = app
        self.name = name
        self.state = 'init'
        self.runner = None
        self._name = '%s-%s-%s' % (id, app, name)
        
    def start(self, image, config, command):
        self._provision(image)
        self._spawn(config, command)

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

    def _run_script(self, script, *args):
        """Run a script and return the Popen object."""
        script_path = os.path.join(self.script_path, script)
        return subprocess.Popen([script_path] + [str(arg) for arg in args],
                                cwd=os.getcwd(), stdin=subprocess.PIPE)

    def _spawn(self, config, command):
        self.runner = self._run_script('start', self._name, self.app, self.name)
        self.runner.rawlink(partial(gevent.spawn, self._child))
        self._set_state('running')
        cmd = {'command': command, 'config': config,
               'app': self.app, 'name': self.name}
        self.runner.stdin.write(json.dumps(cmd) + '\n')
        self.runner.stdin.close()

    def _set_state(self, state):
        self.log.info("state changed to %r" % (state,))
        self.state = state
        self.emit('state', state)

    def _child(self, popen):
        self.runner = None
        self._set_state('done' if not popen.returncode else 'fail')
        self._cleanup().wait()

    def _provision(self, image):
        self._set_state('boot')
        try:
            popen = self._run_script('provision', self._name, self.app, self.name,
                                     image)
            popen.wait()
            # FIXME: xxx, resultcode
        except OSError:
            self.log.exception('fail to spawn provisioning script')
            self._finish('fail')

    def _cleanup(self):
        return self._run_script('cleanup', self._name, self.app, self.name)
