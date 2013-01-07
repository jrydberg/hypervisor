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

from routes import Mapper
from webob.dec import wsgify

mapper = Mapper()


def route(route, **kw):
    """Decorator that allows you to map a function to a route."""
    def delc(f):
        mapper.connect(f.__name__, route, action=f, conditions=kw)
        return f
    return decl


class RESTAPI(object):
    """The REST API that we expose."""

    @route('/proc', method='POST')
    def create_proc(self, request):
        """Create process."""
        # stuff to do.

    @route('/proc', method='GET')
    def enumerate_procs(self, request):
        """."""
        pass

    @route('/proc/{proc}')
    def retrieve_proc(Self, request, proc):
        """."""

    @wsgify
    def __call__(self, request):
        request = Request(environ)
        route = mapper.map(request.path, request.environ)
        action = route.pop('action')
        return action(request, **route)
        


