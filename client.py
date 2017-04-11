import socket

from messages import *

def run_socket_client(addr, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((addr, port))
    data = bytearray()
    chunk = sock.recv(1024)
    data.extend(chunk)

    header = MessageHeader.from_buffer(data)
    if header.flags.type_ == MessageType.Control and header.messageCommand == ControlMessageCode.ByteOrder:
        endianess = header.flags.endianess

    header = MessageHeader.from_buffer(data)
    if header.messageCommand == ApplicationMessageCode.ConnectionValidation:
        validation = ConnectionValidationRequest.from_buffer(data)
        print(validation)
        response = ConnectionValidationResponse(0x4400, 0x7fff, 0, b'')
        messageBody = response.to_buffer()
        messageHeader = MessageHeader(messageCommand=ApplicationMessageCode.ConnectionValidation, payloadSize=len(messageBody))
        sock.send(messageHeader.to_buffer() + messageBody)

    chunk = sock.recv(1024)
    data.extend(chunk)
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == ApplicationMessageCode.ConnectionValidated:
        status = Status.from_buffer(data)

    request = CreateChannelRequest([(1, b'testMP')])
    messageBody = request.to_buffer()
    messageHeader = MessageHeader(messageCommand=ApplicationMessageCode.CreateChannel, payloadSize=len(messageBody))
    sock.send(messageHeader.to_buffer() + messageBody)

    chunk = sock.recv(1024)
    data.extend(chunk)
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == ApplicationMessageCode.CreateChannel:
        response = CreateChannelResponse.from_buffer(data)
        print(response)

    sock.close()

def run_client():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    sock.bind((UDP_ADDR, 50001))

    search = SearchRequest(1, 0, '::ffff:0:0', 50001, [b'tcp'])
    search.channels = [(1, b'testMP')]
    print(search)
    messageBody = search.to_buffer()
    messageHeader = MessageHeader(messageCommand=ApplicationMessageCode.SearchRequest, payloadSize=len(messageBody))
    message = messageHeader.to_buffer() + messageBody
    sock.sendto(message, ('192.168.1.255', 5076))

    chunk, addr = sock.recvfrom(1024)
    data.extend(chunk)
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == ApplicationMessageCode.SearchResponse:
        response = SearchResponse.from_buffer(data)
        print(response)
        tid = threading.Thread(target=run_socket_client, args=(response.serverAddress.compressed, response.serverPort))
        tid.start()

