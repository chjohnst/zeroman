import os
import time
import zmq
import random

TIMEOUT = 5000
SERVER_DEAD_TIME = 10

class worker:
    def __init__(self, servers, timeout=TIMEOUT, server_dead_time=SERVER_DEAD_TIME):
        self.context = zmq.Context()
        self.sockets = {}
        self.last_heartbeats={}
        self.functions = {}

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
        socks = dict(poll.poll(self.TIMEOUT))
        if socks.get(s) == zmq.POLLIN:
            reply = s.recv()
            print 'got reply from', h
        else:
            print 'no reply from', h
            reply = None
            s.setsockopt(zmq.LINGER, 0)
            s.close()
            del self.sockets[h]
            self.dead[h] = time.time()
        poll.unregister(s)

        return reply

    def register(self, h):
        s = self.get_socket(h)
        s.send_multipart(["register"] + self.functions.keys())

    def close(self, h):
        s = self.get_socket(h)
        s.setsockopt(zmq.LINGER, 0)
        s.close()
        del self.sockets[h]

    def reconnect_if_needed(self):
        for h, s in self.sockets.items():
            if time.time() -  self.last_heartbeats.get(s, 0) > self.server_dead_time:
                print h, 'is dead'
                self.close(h)
                self.register(h)
        

    def handle(self, s, msg):
        command = msg.pop(0)
        func = getattr(self, "handle_%s" % command)
        if func:
            return func(s, *msg)
        else:
            return "eh?"

    def handle_heartbeat(self, s):
        print 'heartbeat from', s
        self.last_heartbeats[s] = time.time()
        s.send_multipart(["alive"])

    def handle_call(self, s, client, func, msg):
        f = self.functions.get(func)
        ret = f(msg)
        s.send_multipart(['ret', client, func, ret])

    def run(self):
        for h in self.servers:
            self.register(h)
        
        time.sleep(1)
        while True:
            poll = zmq.Poller()
            for s in self.sockets.values():
                poll.register(s, zmq.POLLIN)
            socks = dict(poll.poll(self.timeout))
            for s in socks:
                msg = s.recv_multipart()
                self.handle(s, msg)

            self.reconnect_if_needed()
            
    def register_handler(self, name, func):
        self.functions[name] = func

if __name__ == "__main__":

    def hello(data):
        print 'returning', data.upper()
        return data.upper()

    w = worker()
    w.register_handler('hello', hello)
    w.run()