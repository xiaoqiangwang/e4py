import socket
import struct
import ipaddress
import enum
import socketserver
import threading
import netifaces


class Networks(object):
    @staticmethod
    def broadcast_list():
        addresses = []
        for iface in netifaces.interfaces():
            addresses.append(netifaces.ifaddresses(iface)[netifaces.AF_INET]['broadcast'])
        return addresses


def popout(buffer, size):
    if size == 1:
        m = buffer[0]
    else:
        m = buffer[:size]
    del buffer[:size]
    return m


def pack_size(size):
    if size < 255:
        return struct.pack('B', size)
    elif size < 2**31 - 1:
        return b'\xff' + struct.pack('I', size)
    else:
        return b'\xff' + b'\x7fffffff' + struct.pack('Q', size)


def pack_string(string):
    return pack_size(len(string)) + string


def pack_string_array(strings):
    return pack_size(len(strings)) + b''.join([pack_string(string) for string in strings])


def unpack_size(buffer):
    size = popout(buffer, 1)
    if size == 255:
        size = struct.unpack('I', popout(buffer, 4))[0]
        if size == 2**31-1:
            size = struct.unpack('Q', popout(buffer, 8))[0]
    return size


def unpack_string(buffer):
    size = unpack_size(buffer)
    return bytes(popout(buffer, size))


def unpack_string_array(buffer):
    size = unpack_size(buffer)
    array = []
    for i in range(size):
        array.append(unpack_string(buffer))
    return array


class StatusType(enum.IntEnum):
    OK = 0
    WARNING = 1
    ERROR = 2
    FATAL = 3
    DEFAULT = 0xFF

class TypeCode(enum.IntEnum):
    NULL = 0xFF
    ONLY = 0xFE
    FULL_TAGGED = 0xFC

class MessageCode(enum.IntEnum):
    Beacon = 0x00
    ConnectionValidation = 0x01
    Echo = 0x02
    Search = 0x03
    SearchResponse = 0x04
    CreateChannel = 0x07
    Validated = 0x09

class MessageHeader(object):
    """
    Each protocol message has a fixed 8-byte header

    struct pvAccessHeader {
        byte magic;
        byte version;
        byte flags;
        byte messageCommand;
        int payloadSize;
    };
    """
    def __init__(self, magic=0xCA, version=1, flags=0, messageCommand=0, payloadSize=0):
        self.magic = magic
        self.version = version
        self.flags = flags
        self.messageCommand = messageCommand
        self.payloadSize = payloadSize

    @staticmethod
    def from_buffer(buffer):
        data = popout(buffer, 8)
        magic, version, flags, messageCommand, payloadSize = struct.unpack('BBBBI', data)
        return MessageHeader(magic, version, flags, messageCommand, payloadSize)

    def to_buffer(self):
        return struct.pack('BBBBI', self.magic, self.version, self.flags, self.messageCommand, self.payloadSize)

    def __str__(self):
        return \
            'MessageHeader\n'\
            '  magic:          %x\n'\
            '  version:        %d\n'\
            '  flags:          %x\n'\
            '  messageCommand: %x\n'\
            '  payloadSize:    %d' % \
            (self.magic, self.version, self.flags, self.messageCommand, self.payloadSize)


class Status(object):
    """
    struct Status {
        byte type;      // enum { OK = 0, WARNING = 1, ERROR = 2, FATAL = 3 }
        string message;
        string callTree;   // optional (provides more context data about the error), can be empty
    };
    In practice, since the majority of Status instances would be OK with no message and no callTree, 
    a special definition of Status SHOULD be used in the common case that all three of these conditions are met; 
    if Status is OK and no message and no callTree would be sent, then the special type value of -1 MAY be used,
    and in this case the string fields are omitted:

    """
    def __init__(self, type_, message, callTree):
        self.type_ = type_
        self.message = message
        self.callTree = callTree

    @staticmethod
    def from_buffer(buffer):
        type_ = popout(buffer, 1)
        message = b''
        callTree = b''
        if type_ != 0xFF:
            message = unpack_string(buffer)
            callTree = unpack_string(buffer)

        return Status(type_, message, callTree)

    def __str__(self):
        return '%s' % self.type_


UDP_ADDR = "0.0.0.0"
UDP_PORT = 5076


class BeaconMessage(object):
    def __init__(self, *args):
        self.guid, self.flags, self.sequenceId, self.changeCount, self.serverAddress, self.serverPort, self.protocol = args
        self.status = None

    @staticmethod
    def from_buffer(buffer):
        guid = int.from_bytes(popout(buffer, 12), 'big')
        flags, sequenceId, changeCount = struct.unpack('BBH', popout(buffer, 4))
        serverAddress  = ipaddress.IPv6Address(bytes(popout(buffer, 16)))
        serverPort = struct.unpack('H', popout(buffer, 2))[0]
        protocol = unpack_string(buffer)

        message = BeaconMessage(guid, flags, sequenceId, changeCount, serverAddress, serverPort, protocol)

        serverStatusIF = popout(buffer, 1)
        # TODO: unpack server status
        if serverStatusIF != TypeCode.NULL:
            message.status = Status.from_buffer(buffer)
     
        return message

    def __str__(self):
        return \
            'BeaconMessage\n'\
            '  guid:          %x\n'\
            '  flags:         %x\n'\
            '  sequenceId:    %d\n'\
            '  changeCount:   %d\n'\
            '  serverAddress: %s\n'\
            '  serverPort:    %d\n'\
            '  protocol:      %s\n' %\
            (self.guid, self.flags, self.sequenceId, self.changeCount, self.serverAddress, self.serverPort, self.protocol)



class SearchRequest(object):
    def __init__(self, *args):
        self.sequenceId, self.flags, self.responseAddress, self.responsePort, self.protocols = args
        self.channels = []

    @staticmethod
    def from_buffer(buffer):
        sequenceId = struct.unpack('I', popout(buffer, 4))[0]
        flags = popout(buffer, 1)
        popout(buffer, 3)
        responseAddress  = ipaddress.IPv6Address(bytes(popout(buffer, 16)))
        responsePort = struct.unpack('H', popout(buffer, 2))[0]
        protocols = unpack_string_array(buffer)
        size = struct.unpack('H', popout(buffer, 2))[0]
        channels = []
        for i in range(size):
            instanceId = struct.unpack('I', popout(buffer, 4))[0]
            name = unpack_string(buffer)
            channels.append((instanceId, name))
        request = SearchRequest(sequenceId, flags, responseAddress, responsePort, protocols)
        request.channels = channels
        return request
        
    def to_buffer(self):
        message = bytearray()
        message.extend(struct.pack('IBBBB', self.sequenceId, self.flags, 0, 0, 0))
        message.extend(ipaddress.IPv6Address(self.responseAddress).packed)
        message.extend(struct.pack('H', self.responsePort))
        message.extend(pack_string_array([b'tcp']))
        
        message.extend(struct.pack('H', len(self.channels)))
        for instanceId, name in self.channels:
            message.extend(struct.pack('I', instanceId))
            message.extend(pack_string(name))
        return message

    def __str__(self):
        output = \
            'SearchRequest\n'\
            '  sequenceId:    %d\n'\
            '  flags:         %x\n'\
            '  serverAddress: %s\n'\
            '  serverPort:    %d\n'\
            '  protocols:     %s\n' % \
            (self.sequenceId, self.flags, self.responseAddress, self.responsePort, self.protocols)
        if len(self.channels) > 0:
            output += '  channels:\n'
        for instanceId, name in self.channels:
            output += '    %d %s\n' % (instanceId, bytes(name))
  
        return output

class ConnectionValidationRequest(object):
   
    def __init__(self, *args):
        self.serverReceiverBufferSize, self.serverIntrospectionRegistryMaxSize, self.authNZ = args

    @staticmethod
    def from_buffer(buffer):
        serverReceiverBufferSize = struct.unpack('I', popout(buffer, 4))[0]
        serverIntrospectionRegistryMaxSize = struct.unpack('H', popout(buffer, 2))[0]
        authNZ = []
        for i in range(unpack_size(buffer)):
            authNZ.append(unpack_string(buffer))
        return ConnectionValidationRequest(serverReceiverBufferSize, serverIntrospectionRegistryMaxSize, authNZ)

    def __str__(self):
        output = \
            'ConnectionValidationRequest\n'\
            '  serverReceiverBufferSize:            %d\n'\
            '  serverIntrospectionRegistryMaxSize:  %d\n' %\
            (self.serverReceiverBufferSize, self.serverIntrospectionRegistryMaxSize)
        if len(self.authNZ) > 0:
            output += '  authNZ: '
            for auth in authNZ:
                output += auth.decode()
        return output

class ConnectionValidationResponse(object):
    def __init__(self, *args):
        self.clientReceiveBufferSize, self.clientIntrospectionRegistryMaxSize, self.connectionQos, self.authNZ = args

    def to_buffer(self):
        message = bytearray()
        message.extend(struct.pack('I', self.clientReceiveBufferSize))
        message.extend(struct.pack('H', self.clientIntrospectionRegistryMaxSize))
        message.extend(struct.pack('H', self.connectionQos))
        message.extend(pack_string(self.authNZ))
        return message



class SearchResponse(object):
    """
    A "search response" message MUST be sent as the response to a search request (0x03) message.
    """
    def __init__(self, *args):
        self.guid, self.sequenceId, self.serverAddress, self.serverPort, self.protocol, self.found, self.instanceIds = args
        
    @staticmethod
    def from_buffer(buffer):
        guid = int.from_bytes(popout(buffer, 12), 'big')
        sequenceId = struct.unpack('I', popout(buffer, 4))[0]
        serverAddress  = ipaddress.IPv6Address(bytes(popout(buffer, 16)))
        serverPort = struct.unpack('H', popout(buffer, 2))[0]
        protocol = unpack_string(buffer)
        found = popout(buffer, 1) != 0
        instanceIds = [] 
        for i in range(struct.unpack('H', popout(buffer, 2))[0]):
            instanceIds.append(struct.unpack('I', popout(buffer, 4))[0])
    
        return SearchResponse(guid, sequenceId, serverAddress, serverPort, protocol, found, instanceIds)

    def __str__(self):
        output = \
            'SearchResponse\n'\
            '  guid:          %x\n'\
            '  sequenceId:    %d\n'\
            '  serverAddress: %s\n'\
            '  serverPort:    %d\n'\
            '  protocol:      %s\n'\
            '  found:         %s\n' %\
            (self.guid, self.sequenceId, self.serverAddress, self.serverPort, self.protocol, self.found)
        if len(self.instanceIds) > 0:
            output += '  channels:\n'
        for instanceId in self.instanceIds:
            output += '    %d\n' % instanceId
  
        return output


class CreateChannelRequest(object):
    def __init__(self, channels):
        self.channels = channels

    def to_buffer(self):
        message = bytearray()
        #message.extend(pack_size(len(self.channels)))
        message.extend(struct.pack('H', len(self.channels)))

        for id_, name in self.channels:
            message.extend(struct.pack('I', id_))
            message.extend(pack_string(name))
    
        return message

class CreateChannelResponse(object):
    def __init__(self, *args):
        self.clientChannelID, self.serverChannelID, self.status, self.accessRights = args

    @staticmethod
    def from_buffer(buffer):
        clientChannelID = struct.unpack('I', popout(buffer, 4))[0]
        serverChannelID = struct.unpack('I', popout(buffer, 4))[0]
        status = Status.from_buffer(buffer)
        accessRights = 0
        if status.type_ == StatusType.OK or status.type_ == StatusType.WARNING:
            accessRights = struct.unpack('H', popout(buffer, 4))[0]
        
        return CreateChannelResponse(clientChannelID, serverChannelID, status, accessRights)

    def __str__(self):
        return \
            'CreateChannelResponse\n'\
            '  clientChannelID: %d\n'\
            '  serverChannelID: %d\n'\
            '  status:          %s\n'\
            '  accessRights:    %d\n' % (self.clientChannelID, self.serverChannelID, self.status, self.accessRights)


class ChannelGetRequestInit(object):
    def __init__(self, *args):
        self.serverChannelID, self.requestID = args
        self.subcommand = 0x08

    def to_buffer(self):
        pass


data = bytearray()

def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    sock.bind((UDP_ADDR, UDP_PORT))

    while True:
        chunk, addr = sock.recvfrom(1024)
        data.extend(chunk)
        header = MessageHeader.from_buffer(data)
        if header.messageCommand == MessageCode.Beacon:
            beacon = BeaconMessage.from_buffer(data)
            print(beacon)
        elif header.messageCommand == MessageCode.Search:
            print(data)
            search = SearchRequest.from_buffer(data)
            print(search)
    
def run_socket_client(addr, port):
    addr = '192.168.1.52'
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((addr, port))
    data = bytearray()
    chunk = sock.recv(1024)
    data.extend(chunk)

    header = MessageHeader.from_buffer(data)
    if header.flags & 0x41 != 0x41 or header.messageCommand != 0x02:
        return
    
    little = (header.flags & 0x80 == 0x00)
    
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == MessageCode.ConnectionValidation:
        validation = ConnectionValidationRequest.from_buffer(data)
        print(validation)
        response = ConnectionValidationResponse(0x4400, 0x7fff, 0, b'')
        messageBody = response.to_buffer()
        messageHeader = MessageHeader(messageCommand=MessageCode.ConnectionValidation, payloadSize=len(messageBody))
        sock.send(messageHeader.to_buffer() + messageBody)

    chunk = sock.recv(1024)
    data.extend(chunk)
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == MessageCode.Validated:
        status = Status.from_buffer(data)

    request = CreateChannelRequest([(1, b'testMP')])
    messageBody = request.to_buffer()
    messageHeader = MessageHeader(messageCommand=MessageCode.CreateChannel, payloadSize=len(messageBody))
    sock.send(messageHeader.to_buffer() + messageBody)

    chunk = sock.recv(1024)
    data.extend(chunk)
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == MessageCode.CreateChannel:
        response = CreateChannelResponse.from_buffer(data)
        print(response)

    sock.close()

def run_client():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

    sock.bind((UDP_ADDR, 50001))

   
    search = SearchRequest(1, 0, '::ffff:0:0', 50001, [b'tcp'])
    search.channels = [(1, b'testMP')]
    print(search)
    messageBody = search.to_buffer()
    messageHeader = MessageHeader(messageCommand=MessageCode.Search, payloadSize=len(messageBody))
    message = messageHeader.to_buffer() + messageBody
    sock.sendto(message, ('192.168.1.255', 5076))

    chunk, addr = sock.recvfrom(1024)
    data.extend(chunk)
    header = MessageHeader.from_buffer(data)
    if header.messageCommand == MessageCode.SearchResponse:
        response = SearchResponse.from_buffer(data)
        print(response)
        tid = threading.Thread(target=run_socket_client, args=(response.serverAddress.compressed, response.serverPort))
        tid.start()
 
if __name__ == '__main__':
    import sys
    if sys.argv[1] == 'client':
        run_client()
    else:
        run_server()
