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
import random
import tempfile
import os.path
from gevent import subprocess
import gevent

from pyee import EventEmitter

class _OutputReader(object):
    """Read output from a file."""

    def __init__(self, log, proc_name, file):
        self.log = log
        self.proc_name = proc_name
        self.file = file
        gevent.spawn(self._reader)

    def _reader(self):
        for line in self.file:
            self.log.info("%s: %s" % (self.proc_name, line))


class Container(EventEmitter):
    """The virtual machine."""

    def __init__(self, log, clock, script_path, name):
        EventEmitter.__init__(self)
        self.log = log
        self.script_path = script_path
        self.name = name
        self.state = 'init'
        self._proc = None
        self._config_file = None
        
    def start(self, image, config, command):
        self._set_state('running')
        self._spawn(image, config, command)

    def stop(self):
        if self._proc is not None:
            # FIXME: do more here.
            self._proc.terminate()

    def _set_state(self, state):
        self.state = state
        self.emit('state', state)

    def _write_config(self, config):
        self._config_file = tempfile.NamedTemporaryFile()
        for key, value in config.items():
            self._config_file.write('%s=%r\n' % (key, value))
        return self._config_file.name

    def _proc_event(self, event):
        """Event from the process."""
        def execute():
            self._set_state('done' if event.get() == 0 else 'fail')
            self._config_file.close()
            del self._config_file
            self._cleanup().wait()
        gevent.spawn(execute)

    def _spawn(self, image, config, command):
        # spawn the container and wait for it
        self._proc = self._provision(image, self._write_config(config),
                                     command)
        self._proc.result.rawlink(self._proc_event)
        _OutputReader(self.log, self.name, self._proc.stdout)
        _OutputReader(self.log, self.name, self._proc.stderr)

    def _provision(self, image, config, command):
        script_path = os.path.join(self.script_path, 'provision')
        print "START", script_path, self.name, image, config, command
        return subprocess.Popen([script_path, self.name, image,
                                 config, command],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    def _cleanup(self):
        script_path = os.path.join(self.script_path, 'cleanup')
        return subprocess.Popen([script_path, self.name])


class Proc(EventEmitter):
    """Representation of a "proc" (aka process)."""

    def __init__(self, log, clock, image_cache,
                 script_dir, name, image, command, config, port):
        EventEmitter.__init__(self)
        self.log = log
        self.clock = clock
        self.image_cache = image_cache
        self.name = name
        self.image = image
        self.command = command
        self.config = config
        self.state = 'init'
        self.port = port
        self._container = Container(log, clock, script_dir, name)

    def start(self):
        """Provision a virtual machine for this proc."""
        self._container.on('state', self._set_state)
        self._container.start(self._get_image(), self.config, self.command)

    def _get_image(self):
        return self.image_cache.get(self.image).get()

    def stop(self):
        """Stop the container."""
        self._container.stop()

    def _set_state(self, new_state):
        self.state = new_state
        self.emit('state', new_state)


class ProcRegistry(dict):
    """Simple registry over processes."""

    def __init__(self, proc_factory, ports, randrange=random.randrange):
        self.proc_factory = proc_factory
        self.ports = list(ports)
        self.randrange = randrange

    def create(self, name, image, command, config):
        if not self.ports:
            raise ValueError("OUT OF RESOURCES")
        port = self.ports.pop(self.randrange(0, len(self.ports)))
        proc = self.proc_factory(name, image, command, config, port)
        self.update({proc.name: proc})
        return proc

    def remove(self, proc):
        """Remove a process."""
        self.pop(proc.name)
        self.ports.append(proc.port)
