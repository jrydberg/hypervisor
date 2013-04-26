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

import uuid
from functools import partial
from routes import Mapper, URLGenerator
from webob import Response
from webob.dec import wsgify
from webob.exc import HTTPBadRequest, HTTPNotFound
import requests
from requests.exceptions import RequestException
import gevent


def _build_proc(url, proc):
    """Build a proc representation."""
    links = dict(self=url('proc', id=proc.id))
    return dict(app=proc.app, name=proc.name,
                image=proc.image, config=proc.config,
                port=proc.port, state=proc.state,
                command=proc.command, links=links)


class ProcResource(object):
    """Resource for our processes."""

    def __init__(self, log, url, registry, factory, requests):
        self.log = log
        self.url = url
        self.registry = registry
        self.factory = factory
        self.requests = requests

    def create(self, request):
        """Create new proc."""
        id = self._create_id()
        data = self._assert_request_data(request)
        proc = self.factory(id, data['app'], data['name'],
                            data['image'], data['command'],
                            data['config'])
        self.registry.add(proc)
        proc.on('state', partial(self._state_callback, proc,
                                 data['callback']))

        # We start the processes in a separate greenlet so that we do
        # not have to wait for it to spin up.  Should we do this after
        # a while instead?
        gevent.spawn(proc.start)

        response = Response(json=_build_proc(self.url, proc), status=201)
        response.headers.add('Location', self.url('proc', id=proc.id))
        return response

    def index(self, request):
        """Return a representation of all procs."""
        collection = {}
        for id, proc in self.registry.items():
            collection[id] = _build_proc(self.url, proc)
        return Response(json=collection, status=200)

    def show(self, request, id):
        """Return a presentation of a proc."""
        proc = self._get(id)
        return Response(json=_build_proc(self.url, proc), status=200)

    def delete(self, request, id):
        """Stop and delete process."""
        proc = self._get(id)
        self.registry.remove(proc)
        proc.dispose()
        return Response(status=204)

    def _assert_request_data(self, request):
        if not request.json:
            raise HTTPBadRequest()
        return request.json

    def _get(self, id):
        """Return process with given ID or C{None}."""
        proc = self.registry.get(id)
        if proc is None:
            raise HTTPNotFound()
        return proc

    def _state_callback(self, proc, callback_url, state):
        """Send state change to remote URL."""
        params = {'name': proc.name, 'port': proc.port, 'state': state}
        self.log.info("send state update for proc %s new state %s" % (
                proc.name, state))
        try:
            response = self.requests.post(callback_url,
                params=params, timeout=10, stream=False)
        except requests.Timeout:
            self.log.error("timeout while sending state change to %s" % (
                    callback_url))
        except RequestException:
            self.log.exception("could not send state update")

    def _create_id(self):
        """Create a new ID for the proc."""
        return str(uuid.uuid4())


class API(object):
    """The REST API that we expose."""

    def __init__(self, log, registry, factory, requests):
        self.mapper = Mapper()
        self.url = URLGenerator(mapper, {})
        self.resources = {
            'proc': ProcResource(log, self.url, registry, factory,
                                 requests),
            }
        self.mapper.collection("procs", "proc", controller='proc',
            path_prefix='/proc', collection_actions=['index', 'create'],
            member_actions=['show', 'delete'], formatted=False)

    @wsgify
    def __call__(self, request):
        route = self.mapper.match(request.path, request.environ)
        if route is None:
            raise HTTPNotFound()
        resource = self.resources[route.pop('controller')]
        action = route.pop('action')
        return getattr(resource, action)(request, **route)
