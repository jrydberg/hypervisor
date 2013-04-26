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

from pyee import EventEmitter
import random


class Proc(EventEmitter):
    """Representation of a "proc" (aka process)."""

    def __init__(self, log, clock, container, id, app, name,
                 image, command, config, port_pool, port):
        EventEmitter.__init__(self)
        self.log = log
        self.clock = clock
        self.id = id
        self.app = app
        self.name = name
        self.image = image
        self.command = command
        self.config = config
        self.port_pool = port_pool
        self.port = port
        self.state = 'init'
        self._container = container

    def start(self):
        """Provision a virtual machine for this proc."""
        self._container.on('state', self._set_state)
        self._container.start(self.image, self.command, self.config)

    def dispose(self):
        """Stop the container and dispose of all its resources."""
        self._container.stop()
        # FIXME (jrydberg): Should we do this when we get the 'done'
        # or 'fail' event?
        self.port_pool.release(self.port)

    def _set_state(self, new_state):
        self.state = new_state
        self.emit('state', new_state)


class PortPoolError(Exception):
    """Port could not be allocated."""


class PortPool(object):
    """Something that is responsible for allocating ports for
    procs."""

    def __init__(self, ports, choice=random.choice):
        self.free = set(ports)
        self.busy = set()
        self.choice = choice

    def allocate(self):
        """Allocate a port from the pool.

        @return: the port or C{None} if the port could not be allocated.

        @raise PortPoolError: when a port could not be allocated.
        """
        if not self.ports:
            raise PortPoolError("out of ports")
        port = self.choice(self.free)
        self.free.remove(port)
        self.busy.add(port)
        return port

    def release(self, port):
        """Release port back to pool."""
        assert port in self.busy, "port was not allocated"
        self.busy.remove(port)
        self.free.add(port)


class ProcRegistry(dict):
    """Simple registry over processes."""

    def __init__(self, proc_factory, port_pool):
        self.proc_factory = proc_factory
        self.port_pool = port_pool
        self._store = {}

    def get(self, id):
        return self._store.get(id, None)

    def add(self, proc):
        """Add proc to the registry."""
        self._store[proc.id] = proc

    def remove(self, proc):
        """Remove proc from the registry."""
        assert proc.id in self._store, "proc not in registry"
        self._store.remove(proc.id)

    def items(self):
        """Return a sequence (id, proc) pairs representing the content
        of the registry.
        """
        return self._store.items()
