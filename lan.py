"""Temporary guest HTTP access on one directly connected Windows IPv4 network."""
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Interface, IPv4Network
import ctypes
import os
import secrets
import struct
import threading
import time


PRIVATE_NETWORKS = tuple(map(IPv4Network, ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')))
SHARE_SECONDS = 30 * 60
REQUEST_LIMITS = dict(threads=4, max_request_body_size=26 * 1024**2, inbuf_overflow=28 * 1024**2)


def interfaces():
    if os.name != 'nt':
        return []
    get_table = ctypes.windll.iphlpapi.GetIpAddrTable
    size = ctypes.c_uint32()
    if get_table(None, ctypes.byref(size), False) != 122:
        return []
    raw = ctypes.create_string_buffer(size.value)
    if get_table(raw, ctypes.byref(size), False) != 0:
        return []
    count, = struct.unpack_from('=I', raw)
    result = set()
    for offset in range(4, 4 + 24 * count, 24):
        ip = IPv4Address(raw[offset:offset+4])
        mask = IPv4Address(raw[offset+8:offset+12])
        try:
            interface = IPv4Interface(f'{ip}/{mask}')
        except ValueError:
            continue
        if any(interface.network.subnet_of(network) for network in PRIVATE_NETWORKS):
            result.add(interface)
    return sorted(result)


@dataclass(frozen=True)
class Share:
    event_id: str
    version: int
    interface: IPv4Interface
    key: str
    identity: str
    expires: float
    port: int

    @property
    def host(self):
        return f'{self.interface.ip}:{self.port}'

    def as_json(self):
        return {
            'url': f'http://{self.host}/e/{self.event_id}#g={self.key}',
            'expires_in': max(0, round(self.expires - time.monotonic())),
        }

    def admits(self, environ):
        try:
            peer = IPv4Address(environ.get('REMOTE_ADDR', ''))
        except ValueError:
            return False
        return peer in self.interface.network and environ.get('HTTP_HOST') == self.host


class GuestListener:
    def __init__(self):
        self.lock = threading.Lock()
        self.share = self.server = self.timer = None

    def current(self, event_id):
        with self.lock:
            share = self.share
            if share and share.event_id == event_id and share.expires > time.monotonic():
                return share
            return None

    def start(self, application, interface, event_id, version):
        from waitress import create_server

        with self.lock:
            if self.share:
                raise ValueError('Сначала завершите действующий доступ с телефона.')
            share = None

            def guest_only(environ, start_response):
                if share and self.current(event_id) is share and share.admits(environ):
                    environ['faceflow.guest_share'] = share
                    return application(environ, start_response)
                start_response('403 Forbidden', [('Content-Length', '0')])
                return []

            server = create_server(guest_only, host=str(interface.ip), port=0, **REQUEST_LIMITS)
            share = Share(event_id, version, interface, secrets.token_urlsafe(24),
                          secrets.token_hex(16), time.monotonic() + SHARE_SECONDS, int(server.effective_port))
            self.share, self.server = share, server
            self.timer = threading.Timer(SHARE_SECONDS, self.stop, args=(event_id, share.identity))
            self.timer.daemon = True
            self.timer.start()
            threading.Thread(target=server.run, daemon=True, name='guest-http').start()
            return share

    def stop(self, event_id=None, identity=None):
        with self.lock:
            if not self.share or (event_id and self.share.event_id != event_id):
                return
            if identity and self.share.identity != identity:
                return
            server, timer = self.server, self.timer
            self.share = self.server = self.timer = None
        timer.cancel()
        server.close()
        server.task_dispatcher.shutdown(timeout=1)
