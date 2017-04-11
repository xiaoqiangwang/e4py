import socket

data = bytearray()

def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    sock.bind((UDP_ADDR, constants.PVA_SERVER_PORT))

    while True:
        chunk, addr = sock.recvfrom(1024)
        data.extend(chunk)
        header = MessageHeader.from_buffer(data)
        if header.messageCommand == ApplicationMessageCode.Beacon:
            beacon = BeaconMessage.from_buffer(data)
            print(beacon)
        elif header.messageCommand == ApplicationMessageCode.SearchRequest:
            print(data)
            search = SearchRequest.from_buffer(data)
            print(search)


