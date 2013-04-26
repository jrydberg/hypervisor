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

import logging
from gevent import pywsgi, monkey
monkey.patch_all(thread=False, time=False)
import os
import socket

import requests
from glock.clock import Clock

from xsharku.api import API
from xsharku.proc import ProcRegistry, Proc, PortPool
from xsharku.runner import Container


class App(object):
    """Class that holds functionality wiring for things together."""

    def __init__(self, clock, script_dir, base_config, port_pool,
                 proc_registry, host, httpclient):
        self.clock = clock
        self.script_dir = script_dir
        self.base_config = base_config
        self.port_pool = port_pool
        self.proc_registry = proc_registry
        self.host = host
        self.httpclient = httpclient

    def create_api(self):
        """Create and return API WSGI application."""
        return API(logging.getLogger('api'), self.proc_registry,
                   self._create_proc, self.httpclient)

    def _create_proc(id, app, name, image, command, app_config):
        """Create proc based on provided parameters."""
        port = self.port_pool.allocate()
        return Proc(clock, self._create_container(id, app, name),
                    id, app, name, image, command,
                    self._prepare_config(app_config, port),
                    port_pool, port)

    def _create_container(self, id, app, name):
        """Create container based on provided parameters."""
        logname = 'container.%s' % (id,)
        return Container(logging.getLogger(logname), self.clock,
                         self.script_dir, id, app, name)

    def _prepare_config(self, app_config, port):
        config = self.base_config.copy()
        config.update(app_config)
        config.update({'PORT': str(port), 'HOST': self.host})
        return config


def main():
    # logging
    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)

    # config
    options = os.environ
    script_dir = os.path.join(os.getcwd(), options['SCRIPT_DIR'])
    base_port = int(options.get('BASE_PORT', 10000))
    max_procs = int(options.get('MAX_PROCS', 100))
    port = int(options['PORT'])

    # wiring
    port_pool = PortPool((base_port + i) for i in range(max_procs))
    proc_registry = ProcRegistry(proc_factory, ports)
    app = App(Clock(), script_dir, {}, port_pool, proc_registry,
              socket.getfqdn(), requests.Session())
    pywsgi.WSGIServer(('', port), app.create_api()).serve_forever()


if __name__ == '__main__':
    main()
