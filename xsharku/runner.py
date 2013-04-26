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
from gevent import subprocess
import json
from pyee import EventEmitter
import os
import os.path


class Container(EventEmitter):
    """The virtual machine."""

    def __init__(self, log, clock, script_path, id, app, name,
                 popen=subprocess.Popen):
        EventEmitter.__init__(self)
        self.log = log
        self.clock = clock
        self.script_path = script_path
        self.app = app
        self.name = name
        self.runner = None
        self._name = '%s-%s-%s' % (id, app, name)
        self._popen = popen
        
    def start(self, image, command, env):
        """Start container.

        @param image: Image that will populate the container.
        @type image: C{str}

        @param command: The command to execute inside the container.
        @type command: C{str}

        @param env: Environment for the command.
        @type env: C{dict}
        """
        self._provision(image)
        self._spawn(env, command)

    # FIXME: I wish there was a decorator for this in gevent.
    def stop(self):
        """Stop the container.

        Note that this method returns right away.  If you want to get
        notified of when the container is actually stopped, watch for
        state changes.
        """
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

    def _provision(self, image):
        """Provision a new container with the specified image."""
        try:
            self._set_state('boot')
            # FIXME (jrydberg): We should check returncode here.
            self._run_script('provision', self._name, self.app, self.name,
                             image).wait()
        except OSError:
            self.log.exception('fail to spawn provisioning script')
            self._set_state('fail')

    def _spawn(self, env, command):
        """Execute command inside container with the given environment."""
        self.runner = self._run_script('start', self._name, self.app, self.name)
        self.runner.rawlink(partial(gevent.spawn, self._child))
        self._set_state('running')
        self.runner.stdin.write(json.dumps({'command': command, 'env': env}))
        self.runner.stdin.close()

    def _child(self, popen):
        """Handler that gets called when our 'start' script finishes."""
        self.runner = None
        self._set_state('done' if not popen.returncode else 'fail')
        self._cleanup().wait()

    def _cleanup(self):
        """Clean up and dispose container."""
        return self._run_script('cleanup', self._name, self.app, self.name)

    def _set_state(self, state):
        self.log.info("state changed to %r" % (state,))
        self.emit('state', state)

    def _run_script(self, script, *args):
        """Run a script and return the Popen object.

        @return: a L{subprocess.Popen} object.
        """
        script_path = os.path.join(self.script_path, script)
        return self._popen([script_path] + [str(arg) for arg in args],
                           cwd=os.getcwd(), stdin=subprocess.PIPE)
