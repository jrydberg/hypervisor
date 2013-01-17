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

"""gilliam-hypervisor xx

Usage:
  gilliam-hypervisor -h | --help
  gilliam-hypervisor [options]

Options:
  -h, --help                Show this screen and exit.
  --version                 Show version and exit.
  -p PORT, --port PORT      Listen port number [default: 6000].
  -n N, --max-num-procs N   Maximum number of procs [default: 64].
"""

import logging
from docopt import docopt
from gevent import pywsgi, monkey
monkey.patch_all(thread=False, time=False)

import requests
from functools import partial
from glock.clock import Clock

from xsharku.api import API
from xsharku.image import ImageCache
from xsharku.proc import ProcRegistry, Proc


def main():
    options = docopt(__doc__, version='0.0')
    logging.basicConfig(level=logging.DEBUG)
    clock = Clock()
    image_cache = ImageCache('.')
    proc_factory = partial(Proc, logging.getLogger('proc'),
       clock, image_cache, '.')
    proc_registry = ProcRegistry(proc_factory, list(range(options[
                    '--max-num-procs']))
    app = API(logging.getLogger('api'), proc_registry, requests.Session())
    pywsgi.WSGIServer(('', int(options['--port'])), app).serve_forever()


