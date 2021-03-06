import os
import time
import zmq
import random

import logging
logger = logging.getLogger(__name__)

TIMEOUT = 1000
SERVER_DEAD_TIME = 30
class client:
    def __init__(self, servers, timeout=TIMEOUT, server_dead_time=SERVER_DEAD_TIME):
        self.context = zmq.Context()
        self.sockets = {}
        self.dead = {}

        self.servers = servers
        self.timeout = timeout
        self.server_dead_time = server_dead_time

    def get_socket(self, h):
        s = self.sockets.get(h)
        if s:
            return s
        s = self.context.socket(zmq.REQ)
        s.connect(h)
        self.sockets[h] = s
        return s

    def do_host(self, h, r):
        s = self.get_socket(h)
        if not s:
            return None
        s.send_multipart(r)

        poll = zmq.Poller()
        poll.register(s, zmq.POLLIN)
        socks = dict(poll.poll(self.timeout))
        if socks.get(s) == zmq.POLLIN:
            reply = s.recv()
            logger.debug('got reply from %r', h)
        else:
            logger.error('no reply from %r', h)
            reply = None
            s.setsockopt(zmq.LINGER, 0)
            s.close()
            del self.sockets[h]
            self.dead[h] = time.time()
        poll.unregister(s)

        return reply

    def alive_servers(self):
        for h in self.servers:
            if h in self.dead:
                if time.time() - self.dead[h] > self.server_dead_time:
                    del self.dead[h]
                    yield h
            else:
                yield h

    def do_req(self, r):
        random.shuffle(self.servers)
        if len(self.dead) == len(self.servers):
            self.dead = {}
        for h in self.alive_servers():
            resp = self.do_host(h, r)
            if resp:
                return resp

    def call(self, func, data):
        return self.do_req(["call", func, data])

    def background(self, func, data):
        return self.do_req(["background", func, data])

    def broadcast(self, func, data):
        return self.do_req(["broadcast", func, data])
