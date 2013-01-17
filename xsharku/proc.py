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
from functools import partial


class ContainerConnection(object):
    """A connection to the runner within the container."""

    def __init__(self, socket, container):
        self.socket = socket
        self.container = container
        gevent.spawn(self._reader)

    def _reader(self):
        """."""
        while True:
            data = self.socket.recv(4096)
            if not data:
                break
            lines = data.split('\n')
            for line in lines:
                command = json.loads(line)
                if 'state' in command:
                    self.container._set_state(command['state'])

    def execute(self, command, config):
        """Issue a spawn command to the container."""
        text = json.dumps({'do': 'spawn', 'command': command,
                           'config': config}) + '\n'
        self.socket.send(text)

    def terminate(self):
        text = json.dumps({'do': 'terminate'}) + '\n'
        self.socket.send(text)


class Container(EventEmitter):
    """The virtual machine."""

    def __init__(self, log, clock, name, contdir, boot_timeout=30):
        self.name = name
        self.state = 'init'
        self._connection = AsyncResult()
        self._boot_timeout = 30

    def start(self, image):
        self._set_state('boot')
        self._setup_dir()
        self._start_server()
        self._spawn()

    def _setup_dir(self):
        os.mkdir(self.contdir)

    def _set_state(self, state):
        self.state = state
        self.emit('state', state)

    def _spawn(self, image):
        # spawn the container and wait for it
        p = self._provision(image)
        try:
            p.wait(timeout=self._boot_timeout)
        except TimeoutError:
            p.kill()
            # FIXME: Also run the cleanup script here so that we do
            # not leak any 
            self._cleanup().wait()
        else:
            self._wait()

    def _provision(self, image):
        script_path = os.path.join(self.script_path, 'provision')
        return subprocess.Popen([script_path, self.name, image], shell=True)

    def _cleanup(self):
        script_path = os.path.join(self.script_path, 'cleanup')
        return subprocess.Popen([script_path, self.name], shell=True)

    def _wait(self):
        """Wait for the container to boot and to contact us."""
        return self._connection.get(timeout=self._boot_timeout)

    def _handle_connection(self, socket, *args):
        """Handle a connection from the container."""
        self._connection.set(ContainerConnection(socket, self))

    def _start_server(self):
        self._server = StreamServer(unix.bind_unix_socket(
                os.path.join(self.contdir, 'socket')),
                self._handle_connection)
        self._server.start()


class Proc(EventEmitter):
    """Representation of a "proc" (aka process)."""

    def __init__(self, log, clock, image_cache,
                 contdir, name, image, command, config, port,
                 container_boot_timeout=30):
        self.log = log
        self.clock = clock
        self.contdir = os.path.join(contdir, name)
        self.image_cache = image_cache
        self.name = name
        self.image = image
        self.command = command
        self.config = config
        self.state = 'init'
        self.port = port
        self._container = Container(log, clock, self.contdir)

    def start(self):
        """Provision a virtual machine for this proc."""
        self._container.on('state', self._container_set_state)
        self._container.start(self._get_image())
        self._container.execute(self.command, self.config)

    def _get_image(self):
        return self.image_cache.get(self.image).get()

    def stop(self):
        """Stop the container."""
        self._container.stop()

    def _set_state(self, new_state):
        self.state = new_state
        self.emit('state', new_state)

    def _container_set_state(self, new_state):
        if new_state == 'boot':
            self._set_state('boot')
        elif new_state == 'running' and self.state == 'boot':
            self._set_state('running')
        elif new_state == 'exit' and self.state == 'running':
            self._set_state('exit')


class ProcRegistry(dict):
    """Simple registry over processes."""

    def __init__(self, proc_factory, ports, randrange=random.randrange):
        self.proc_factory = proc_factory
        self.ports = list(ports)

    def create(self, name, image, command, config):
        if not self.ports:
            raise ValueError("OUT OF RESOURCES")
        port = self.ports.pop(self.randrange(0, len(self.ports)))
        proc = self.proc_factory(name, image, command, config, port)
        self.set(proc.name, proc)
        return proc

    def remove(self, proc):
        """Remove a process."""
        self.pop(proc.name)
        self.ports.append(proc.port)

        
