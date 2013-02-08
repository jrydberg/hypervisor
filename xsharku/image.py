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

import gevent
from gevent.event import AsyncResult
import hashlib
import os.path
from requests.exceptions import RequestException
import requests


class ImageCache(object):
    """An image cache."""
    _chunk_size = 3 * 1024 * 1024

    def __init__(self, dir, requests=requests):
        self.dir = dir
        self.requests = requests

    def _retrieve(self, full_path, image_url, result):
        """Retrive the image.

        This function itself shoudl never fail (raise an exception).
        Instead, if something goes wrong the provided async result
        will be updated with an exception.
        """
        try:
            response = self.requests.get(image_url, stream=True)
            response.raise_for_status()
        except RequestException, err:
            result.set_exception(err)
        else:
            try:
                with open(full_path, 'wb') as fp:
                    for data in response.iter_content(self._chunk_size):
                        print "GOT DATA", len(data)
                        fp.write(data)
            except (IOError, OSError), err:
                result.set_exception(err)
            else:
                result.set(full_path)
        
    def get(self, image_url):
        """Get image.

        @return: a L{AsyncResult} that will have its value set to an
            absolute path where the image can be found.
        """
        full_path = os.path.join(self.dir, hashlib.md5(image_url).hexdigest())
        result = AsyncResult()
        if os.path.exists(full_path):
            result.set(full_path)
        else:
            gevent.spawn(self._retrieve, full_path, image_url, result)
        return result
