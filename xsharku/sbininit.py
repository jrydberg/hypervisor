#!/usr/bin/python

import json
import os
import sys

static = {'HOME': '/app'}

if __name__ == '__main__':
    cmd = json.loads(sys.stdin.readline())
    os.chdir("/app")
    environ = os.environ.copy()
    environ.update(cmd['config'])
    environ.update(static)
    os.execve("/bin/bash", ["/bin/bash", "-l", "-c", cmd["command"]], environ)
    sys._exit(1)
