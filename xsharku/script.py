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
from functools import partial
from glock.clock import Clock

from xsharku.api import API
from xsharku.image import ImageCache
from xsharku.proc import ProcRegistry, Proc
from xsharku.runner import Container, Runner


def main():
    # get logging running
    format = '%(levelname)-8s %(name)s: %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=format)
    # setup config
    options = os.environ
    cache_dir = os.path.join(os.getcwd(), options['IMAGE_DIR'])
    script_dir = os.path.join(os.getcwd(), options['SCRIPT_DIR'])
    proc_dir = os.path.join(os.getcwd(), options['PROC_DIR'])
    base_port = int(options['BASE_PORT'])
    exports = options.get('EXPORTS', '').split(',')
    max_procs = int(options.get('MAX_PROCS', '8'))
    # default config
    default_config = {}
    for var in exports:
        if var in os.environ:
            default_config[var] = os.environ[var]
    # wiring
    clock = Clock()
    image_cache = ImageCache(cache_dir)

    def container_factory(id, app, name):
        logname = 'container.%s' % (id,)
        return Container(logging.getLogger(logname), clock,
            script_dir, os.path.join(proc_dir, id), app, name,
            'gilliam')

    def proc_factory(id, app, name, image, command, app_config, port):
        config = default_config.copy()
        config.update(app_config)
        config.update({'PORT': str(port), 'HOST': socket.getfqdn()})
        return Proc(logging.getLogger('proc.%s' % (id,)),
            clock, image_cache, container_factory(id, app, name),
            id, app, name, image, command, config, port)

    ports = [(base_port + i) for i in range(max_procs)]
    proc_registry = ProcRegistry(proc_factory, ports)
    app = API(logging.getLogger('api'), proc_registry, requests.Session())
    # serve
    logging.info("Start serving requests on %d" % (int(options['PORT']),))
    pywsgi.WSGIServer(('', int(options['PORT'])), app).serve_forever()


if __name__ == '__main__':
    main()
