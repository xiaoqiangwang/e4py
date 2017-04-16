import ipaddress
import socket
import threading

from . import constants
from .messages import *

GUID = 0xffffffff00000000ffffffff

def run_server_socket():
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.bind(('::ffff:0:0', constants.PVA_SERVER_PORT))
    sock.listen(5)

    client, addr = sock.accept()

    dispatcher = ServerMessageDispatcher(client)

    request = ConnectionValidationRequest(0x4400, 0x7fff, [])
    client.send(request.to_buffer())

    while True:
        data = client.recv(1024)
        status = dispatcher.data_received(data)
        if status == 0:
            break

    client.close()

    sock.close()

def run_server():
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    sock.bind(('', constants.PVA_BROADCAST_PORT))

    tid = threading.Thread(target=run_server_socket)
    tid.start()

    while True:
        chunk, addr = sock.recvfrom(1024)
        buffer = BufferReader(chunk)
        header = MessageHeader.from_buffer(buffer)
        print(header)
        if header.messageCommand == ApplicationMessageCode.Beacon:
            beacon = BeaconMessage.from_buffer(buffer)
            print(beacon)
        elif header.messageCommand == ApplicationMessageCode.SearchRequest:
            request = SearchRequest.from_buffer(buffer)
            print(request)

            response = SearchResponse(GUID, request.sequenceId,
                                      ipaddress.ip_address(u'::ffff:0:0'), constants.PVA_SERVER_PORT,
                                      b'tcp', 1,
                                      list(id_ for id_,name in request.channels))
            print(len(response.instanceIds))
            sock.sendto(response.to_buffer(), (request.responseAddress.exploded, request.responsePort))
            print(response)
        else:
            buffer.skip_bytes(header.payloadSize)


if __name__ == '__main__':
    run_server()
