import socket
import threading

from messages import *

def run_socket_client(addr, port):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((addr, port))

    dispatcher = ClientMessageDispatcher(sock)
    while True:
        chunk = sock.recv(1024)
        status = dispatcher.data_received(chunk)
        if status == 0:
            break
    sock.close()

def run_client():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    sock.bind(('0.0.0.0', 50001))

    search = SearchRequest(1, 0, u'::ffff:0:0', 50001, [b'tcp'], [(1, b'testMP')])
    sock.sendto(search.to_buffer(), ('192.168.1.255', 5076))

    chunk, addr = sock.recvfrom(1024)
    buffer = BufferReader(chunk)
    header = MessageHeader.from_buffer(buffer)
    print(header)
    if header.messageCommand == ApplicationMessageCode.SearchResponse:
        response = SearchResponse.from_buffer(buffer)
        print(response)
        tid = threading.Thread(target=run_socket_client, args=(response.serverAddress.compressed, response.serverPort))
        tid.start()


if __name__ == '__main__':
    run_client()