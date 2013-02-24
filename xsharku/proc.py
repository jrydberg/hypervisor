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
import os
from gevent import subprocess
import gevent

from pyee import EventEmitter


class Proc(EventEmitter):
    """Representation of a "proc" (aka process)."""

    def __init__(self, log, clock, image_cache, container, id, app, name,
                 image, command, config, port):
        EventEmitter.__init__(self)
        self.log = log
        self.clock = clock
        self.image_cache = image_cache
        self.id = id
        self.app = app
        self.name = name
        self.image = image
        self.command = command
        self.config = config
        self.port = port
        self.state = 'init'
        self._container = container

    def start(self):
        """Provision a virtual machine for this proc."""
        self._container.on('state', self._set_state)
        self._container.start(self._get_image(), self.config, self.command)

    def _get_image(self):
        """Retrieve the image from the cache and return an absolute
        path to it.
        """
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

    def create(self, id, app, name, image, command, config):
        if not self.ports:
            raise ValueError("OUT OF RESOURCES")
        port = self.ports.pop(self.randrange(0, len(self.ports)))
        proc = self.proc_factory(id, app, name, image, command, config, port)
        self.update({proc.id: proc})
        return proc

    def remove(self, proc):
        """Remove a process."""
        self.pop(proc.id)
        self.ports.append(proc.port)
