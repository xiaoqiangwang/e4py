import array
import struct
import ipaddress
import itertools
import enum
import sys

import constants

if sys.hexversion < 0x03000000:
    def int_from_bytes(s, byteorder):
        if byteorder == 'little':
            return sum(ord(b) << (8*i) for i, b in enumerate(s))
        else:
            return sum(ord(b) << (8*i) for i, b in enumerate(s[::-1]))

    def int_to_bytes(s, length, byteorder):
        v = b''.join(chr(s >> (8*i) & 0xff) for i in range(length))
        if byteorder == 'big':
            v = v[::-1]
        return v
else:
    int_from_bytes = int.from_bytes
    int_to_bytes = int.to_bytes


__all__ =['MessageHeader', 'BeaconMessage', 'SearchRequest', 'SearchResponse', 'ConnectionValidationRequest',
          'ConnectionValidationResponse', 'ConnectionValidatedResponse',
          'CreateChannelRequest', 'CreateChannelResponse',
          'ChannelGetRequestInit', 'ChannelGetResponseInit',
          'ApplicationMessageCode',
          'BufferReader', 'ClientMessageDispatcher', 'ServerMessageDispatcher']


class BufferWriter(object):
    """
    Wrap write access to a bytearray
    """
    def __init__(self):
        self.buffer = bytearray()
        self.index = 0

    def get_buffer(self):
        return self.buffer

    def put_padding(self, n):
        self.buffer.extend(b'\x00' * n)

    def put_raw(self, value):
        self.buffer.extend(value)

    def put_byte(self, value):
        self.buffer.append(value)

    def put_short(self, value):
        self.buffer.extend(struct.pack('H', value))

    def put_integer(self, value):
        self.buffer.extend(struct.pack('I', value))

    def put_integer_array(self, value):
        self._put_size(len(value))
        for v in value:
            self.put_integer(v)

    def put_string(self, value):
        self._put_size(len(value))
        self.buffer.extend(value)

    def put_string_array(self, value):
        self._put_size(len(value))
        for v in value:
            self.put_string(v)

    def _put_size(self, size):
        if size < 0xff:
            self.buffer.append(size)
        elif size < 0x7fffffff:
            self.buffer.append(255)
            self.buffer.extend(struct.pack('I', size))
        else:
            self.buffer.append(255)
            self.buffer.extend(struct.pack('I', 0x7fffffff))
            self.buffer.extend(struct.pack('Q', size))

    def __len__(self):
        return len(self.buffer)


class BufferReader(object):
    """
    Wrap read access to a bytes object
    """
    def __init__(self, source):
        self.source = source
        self.index = 0

    def skip_bytes(self, n):
        """
        skip *n* bytes.
        :param n: number of bytes to skip
        """
        self.index += n

    def get_raw(self, n):
        """
        return *n* bytes
        :param n: number of bytes to read
        :return:
        """
        v = self.source[self.index:self.index + n]
        self.index += n
        return v

    def get_byte(self):
        v = ord(self.source[self.index])
        self.index += 1
        return v

    def get_short(self):
        v = struct.unpack('H', self.source[self.index:self.index + 2])[0]
        self.index += 2
        return v

    def get_integer(self):
        v = struct.unpack('I', self.source[self.index:self.index + 4])[0]
        self.index += 4
        return v

    def get_integer_array(self):
        size = self._get_size()
        v = struct.unpack('%dI'%size, self.source[self.index:self.index + 4*size])
        self.index += size*4
        return v

    def get_long(self):
        v = struct.unpack('Q', self.source[self.index:self.index + 8])[0]
        self.index += 8
        return v

    def get_string(self):
        size = self._get_size()
        v = self.source[self.index:self.index + size]
        self.index += size
        return v

    def get_string_array(self):
        size = self._get_size()
        v = []
        for i in range(size):
            v.append(self.get_string())
        return v

    def _get_size(self):
        size = self.get_byte()
        if size == 255:
            size = self.get_integer()
            if size == 2 ** 31 - 1:
                size = self.get_long()
        return size

    def __len__(self):
        return len(self.source) - self.index


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


class MessageType(enum.IntEnum):
    Application = 0x00
    Control = 0x01


class MessageSegment(enum.IntEnum):
    No = 0x00
    First = 0x01
    Last = 0x02
    Middle = 0x03


class MessageDirection(enum.IntEnum):
    Client = 0x00
    Server = 0x01


class MessageEndianess(enum.IntEnum):
    Little = 0x00
    Big = 0x01


class ApplicationMessageCode(enum.IntEnum):
    Beacon = 0x00
    ConnectionValidation = 0x01
    Echo = 0x02
    SearchRequest = 0x03
    SearchResponse = 0x04
    AuthNZ = 0x05
    AccessRights = 0x06
    CreateChannel = 0x07
    DestroyChannel = 0x08
    ConnectionValidated = 0x09
    ChannelGet = 0x0A
    ChannelPut = 0x0B
    ChannelPutGet = 0x0C
    ChannelMonitor = 0x0D
    ChannelArray = 0x0E
    DestroyRequest = 0x0F
    ChannelProcess = 0x10
    ChannelIF = 0x11
    Message = 0x012
    MultipleDataResponse = 0x13
    ChannelRPC = 0x14
    CancelRequest = 0x15


class ControlMessageCode(enum.IntEnum):
    MarkSent = 0x00
    AcknowledgeSent = 0x01
    ByteOrder = 0x02
    EchoRequest = 0x03
    EchoResponse = 0x04


class HeaderFlag(object):
    def __init__(self, *args, **kws):
        if len(args) == 1:
            flag = args[0]
            self.type_ = MessageType(flag & 0x01)
            self.segment = MessageSegment((flag & 0x30) >> 4)
            self.direction = MessageDirection((flag & 0x40) >> 6)
            self.endianess = MessageEndianess((flag & 0x80) >> 7)
        else:
            self.type_ = kws.get('type', MessageType.Application)
            self.segment = kws.get('segment', MessageSegment.No)
            self.direction = kws.get('direction', MessageDirection.Client)
            self.endianess = kws.get('endianess', MessageEndianess.Little)

    def __int__(self):
        return self.type_ | (self.segment << 4) | (self.direction << 6) | (self.endianess << 7)

    def __str__(self):
        return '%s %s %s %s' % (self.type_, self.segment, self.direction, self.endianess)


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
    def __init__(self, type_=StatusType.DEFAULT, message=b'', callTree=b''):
        self.type_ = type_
        self.message = message
        self.callTree = callTree

    @staticmethod
    def from_buffer(buffer):
        type_ = StatusType(buffer.get_byte())
        message = b''
        callTree = b''
        if type_ != StatusType.DEFAULT:
            message = buffer.get_string()
            callTree = buffer.get_string()

        return Status(type_, message, callTree)

    def to_buffer(self):
        buffer = BufferWriter()
        buffer.put_byte(self.type_)
        if self.type_ != StatusType.DEFAULT:
            buffer.put_string(self.message)
            buffer.put_string(self.callTree)

        return buffer.get_buffer()

    def is_ok(self):
        return self.type_ == StatusType.DEFAULT or self.type_ == StatusType.OK

    def __str__(self):
        return '%s %s %s' % (self.type_, self.message, self.callTree)


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
    def __init__(self, magic=constants.PVA_MAGIC, version=constants.PVA_VERSION, flags=HeaderFlag(), messageCommand=0, payloadSize=0):
        self.magic = magic
        self.version = version
        self.flags = flags
        self.messageCommand = messageCommand
        self.payloadSize = payloadSize

    def is_valid(self):
        """
        True if magic byte equals :data:`constants.PVA_MAGIC`
        """
        return self.magic == constants.PVA_MAGIC

    @staticmethod
    def from_buffer(buffer):
        magic, version, flags, messageCommand, payloadSize = struct.unpack('BBBBI', buffer.get_raw(8))
        flags = HeaderFlag(flags)
        if flags.type_ == MessageType.Application:
            messageCommand = ApplicationMessageCode(messageCommand)
        else:
            messageCommand = ApplicationMessageCode(messageCommand)

        return MessageHeader(magic, version, flags, messageCommand, payloadSize)

    def to_buffer(self):
        return struct.pack('BBBBI', self.magic, self.version, int(self.flags), self.messageCommand, self.payloadSize)

    def __str__(self):
        return \
            'MessageHeader\n'\
            '  magic:          %x\n'\
            '  version:        %d\n'\
            '  flags:          %s\n'\
            '  messageCommand: %s\n'\
            '  payloadSize:    %d\n' % \
            (self.magic, self.version, str(self.flags), self.messageCommand, self.payloadSize)


class BeaconMessage(object):
    def __init__(self, *args):
        self.guid, self.flags, self.sequenceId, self.changeCount, self.serverAddress, self.serverPort, self.protocol = args
        self.status = None

    @staticmethod
    def from_buffer(buffer):
        """
        Create BeaconMessage from *buffer*

        :param buffer:
        :type buffer: :class:`BufferReader`
        :return: :class:`BeacondaMessage` instance
        """
        guid = int_from_bytes(buffer.get_raw(12), 'little')
        flags, sequenceId, changeCount = struct.unpack('BBH', buffer.get_raw(4))
        serverAddress  = ipaddress.IPv6Address(buffer.get_raw(16))
        serverPort = buffer.get_short()
        protocol = buffer.get_string()

        message = BeaconMessage(guid, flags, sequenceId, changeCount, serverAddress, serverPort, protocol)

        serverStatusIF = buffer.get_byte()
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
        self.sequenceId, self.flags, self.responseAddress, self.responsePort, self.protocols, self.channels = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create SearchRequest from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`SearchRequestMessage` instance
        """
        sequenceId = buffer.get_integer()

        flags = buffer.get_byte()
        buffer.skip_bytes(3)
        responseAddress = ipaddress.IPv6Address(buffer.get_raw(16))
        responsePort = buffer.get_short()
        protocols = buffer.get_string_array()
        size = buffer.get_short()
        channels = []
        for i in range(size):
            instanceId = buffer.get_integer()
            name = buffer.get_string()
            channels.append((instanceId, name))
        request = SearchRequest(sequenceId, flags, responseAddress, responsePort, protocols, channels)
        return request
        
    def to_buffer(self):
        header = MessageHeader(
            flags=HeaderFlag(),
            messageCommand=ApplicationMessageCode.SearchRequest
        )

        buffer = BufferWriter()
        buffer.put_integer(self.sequenceId)
        buffer.put_byte(self.flags)
        buffer.put_padding(3)
        buffer.put_raw(ipaddress.ip_address(self.responseAddress).packed)
        buffer.put_short(self.responsePort)
        buffer.put_string_array([b'tcp'])
        
        buffer.put_short(len(self.channels))
        for instanceId, name in self.channels:
            buffer.put_integer(instanceId)
            buffer.put_string(name)

        header.payloadSize = len(buffer)

        return header.to_buffer() + buffer.get_buffer()

    def __str__(self):
        output = \
            'SearchRequest\n'\
            '  sequenceId:    %d\n'\
            '  flags:         %x\n'\
            '  responseAddress: %s\n'\
            '  responsePort:    %d\n'\
            '  protocols:     %s\n' % \
            (self.sequenceId, self.flags, self.responseAddress, self.responsePort, self.protocols)
        if len(self.channels) > 0:
            output += '  channels:\n'
        for instanceId, name in self.channels:
            output += '    %d %s\n' % (instanceId, bytes(name))
  
        return output


class SearchResponse(object):
    """
    A "search response" message MUST be sent as the response to a search request (0x03) message.
    """

    def __init__(self, *args):
        self.guid, self.sequenceId, self.serverAddress, self.serverPort, self.protocol, self.found, self.instanceIds = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create SearchResponse from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`SearchResponse` instance
        """
        guid = int_from_bytes(buffer.get_raw(12), 'little')
        sequenceId = buffer.get_integer()
        serverAddress = ipaddress.IPv6Address(buffer.get_raw(16))
        serverPort = buffer.get_short()
        protocol = buffer.get_string()
        found = buffer.get_short() != 0
        instanceIds = buffer.get_integer_array()

        return SearchResponse(guid, sequenceId, serverAddress, serverPort, protocol, found, instanceIds)

    def to_buffer(self):
        header = MessageHeader(
            flags=HeaderFlag(direction=MessageDirection.Server),
            messageCommand=ApplicationMessageCode.SearchResponse
        )

        buffer = BufferWriter()
        buffer.put_raw(int_to_bytes(self.guid, 12, 'little'))
        buffer.put_integer(self.sequenceId)
        buffer.put_raw(self.serverAddress.packed)
        buffer.put_short(self.serverPort)
        buffer.put_string(self.protocol)
        buffer.put_short(self.found)
        buffer.put_integer_array(self.instanceIds)

        header.payloadSize = len(buffer)
        print(header)
        return header.to_buffer() + buffer.get_buffer()

    def __str__(self):
        output = \
            'SearchResponse\n' \
            '  guid:          %x\n' \
            '  sequenceId:    %d\n' \
            '  serverAddress: %s\n' \
            '  serverPort:    %d\n' \
            '  protocol:      %s\n' \
            '  found:         %s\n' % \
            (self.guid, self.sequenceId, self.serverAddress, self.serverPort, self.protocol, self.found)
        if len(self.instanceIds) > 0:
            output += '  channels:\n'
        for instanceId in self.instanceIds:
            output += '    %d\n' % instanceId

        return output


class ConnectionValidationRequest(object):
    def __init__(self, *args):
        self.serverReceiverBufferSize, self.serverIntrospectionRegistryMaxSize, self.authNZ = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create ConnectionValidationRequest from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ConnectionValidationRequest` instance
        """
        serverReceiverBufferSize = buffer.get_integer()
        serverIntrospectionRegistryMaxSize = buffer.get_short()
        authNZ = buffer.get_string_array()
        return ConnectionValidationRequest(serverReceiverBufferSize, serverIntrospectionRegistryMaxSize, authNZ)

    def to_buffer(self):
        header = MessageHeader(
            flags=HeaderFlag(direction=MessageDirection.Server),
            messageCommand=ApplicationMessageCode.ConnectionValidation
        )

        buffer = BufferWriter()
        buffer.put_integer(self.serverReceiverBufferSize)
        buffer.put_short(self.serverIntrospectionRegistryMaxSize)
        buffer.put_string_array(self.authNZ)

        header.payloadSize = len(buffer)
        return header.to_buffer() + buffer.get_buffer()

    def __str__(self):
        output = \
            'ConnectionValidationRequest\n'\
            '  serverReceiverBufferSize:            %d\n'\
            '  serverIntrospectionRegistryMaxSize:  %d\n' %\
            (self.serverReceiverBufferSize, self.serverIntrospectionRegistryMaxSize)
        if len(self.authNZ) > 0:
            output += '  authNZ: '
            for auth in self.authNZ:
                output += auth.decode()
            output += '\n'
        return output


class ConnectionValidationResponse(object):
    def __init__(self, *args):
        self.clientReceiveBufferSize, self.clientIntrospectionRegistryMaxSize, self.connectionQos, self.authNZ = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create ConnectionValidationResponse from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ConnectionValidationResponse` instance
        """
        clientReceiveBufferSize = buffer.get_integer()
        clientIntrospectionRegistryMaxSize = buffer.get_short()
        connectionQos = buffer.get_short()
        authNZ = buffer.get_string()

        return ConnectionValidationResponse(clientReceiveBufferSize, clientIntrospectionRegistryMaxSize, connectionQos, authNZ)

    def to_buffer(self):
        header = MessageHeader(
            messageCommand=ApplicationMessageCode.ConnectionValidation
        )
        buffer = BufferWriter()
        buffer.put_integer(self.clientReceiveBufferSize)
        buffer.put_short(self.clientIntrospectionRegistryMaxSize)
        buffer.put_short(self.connectionQos)
        buffer.put_string(self.authNZ)

        header.payloadSize = len(buffer)
        return header.to_buffer() + buffer.get_buffer()

    def __str__(self):
        return \
            'ConnectionValidationResponse\n'\
            '  clientReceiveBufferSize:            %d\n'\
            '  clientIntrospectionRegistryMaxSize: %d\n'\
            '  connectionQos:                      %d\n'\
            '  authNZ:                             %s\n'\
            % (self.clientReceiveBufferSize, self.clientIntrospectionRegistryMaxSize, self.connectionQos, self.authNZ)


class ConnectionValidatedResponse(object):
    def __init__(self, status=Status()):
        self.status = status

    @staticmethod
    def from_buffer(buffer):
        """
        Create ConnectionValidatedResponse from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ConnectionValidatedResponse` instance
        """
        status = Status.from_buffer(buffer)
        return ConnectionValidatedResponse(status)

    def to_buffer(self):
        header = MessageHeader(
            flags=HeaderFlag(direction=MessageDirection.Server),
            messageCommand=ApplicationMessageCode.ConnectionValidated,
            payloadSize=1
        )
        return header.to_buffer() + self.status.to_buffer()

    def __str__(self):
        return \
            'ConnectionValidatedResponse\n' \
            '  status: %s\n' % self.status


class CreateChannelRequest(object):
    def __init__(self, channels):
        self.channels = channels

    @staticmethod
    def from_buffer(buffer):
        """
        Create CreateChannelRequest from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`CreateChannelRequest` instance
        """
        channels = []
        for i in range(buffer.get_short()):
            id_ = buffer.get_integer()
            name = buffer.get_string()
            channels.append((id_, name))

        return CreateChannelRequest(channels)

    def to_buffer(self):
        header = MessageHeader(
            messageCommand=ApplicationMessageCode.CreateChannel
        )

        buffer = BufferWriter()
        buffer.put_short(len(self.channels))

        for id_, name in self.channels:
            buffer.put_integer(id_)
            buffer.put_string(name)

        header.payloadSize = len(buffer)
        return header.to_buffer() + buffer.get_buffer()

    def __str__(self):
        output = 'CreateChannelRequest\n'
        for id_, name in self.channels:
            output += '  %d %s\n' % (id_, name)

        return output

class CreateChannelResponse(object):
    def __init__(self, *args):
        self.clientChannelID, self.serverChannelID, self.status, self.accessRights = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create CreateChannelResponse from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`CreateChannelResponse` instance
        """
        clientChannelID = buffer.get_integer()
        serverChannelID = buffer.get_integer()
        status = Status.from_buffer(buffer)
        accessRights = 0
        if status.type_ == StatusType.OK or status.type_ == StatusType.WARNING:
            accessRights = buffer.get_short()
        
        return CreateChannelResponse(clientChannelID, serverChannelID, status, accessRights)

    def to_buffer(self):
        header = MessageHeader(
            flags=HeaderFlag(direction=MessageDirection.Server),
            messageCommand=ApplicationMessageCode.CreateChannel
        )
        buffer = BufferWriter()
        buffer.put_integer(self.clientChannelID)
        buffer.put_integer(self.serverChannelID)
        buffer.put_raw(self.status.to_buffer())
        if self.status.type_ == StatusType.OK or self.status.type_ == StatusType.WARNING:
            buffer.put_short(self.accessRights)

        header.payloadSize = len(buffer)
        return header.to_buffer() + buffer.get_buffer()

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


    @staticmethod
    def from_buffer(buffer):
        """
        Create ChannelGetRequestInit from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ChannelGetRequestInit` instance
        """
        serverChannelID = buffer.get_integer()
        requestID = buffer.get_integer()
        subcommand = buffer.get_byte()


    def to_buffer(self):
        pass


class ChannelGetResponseInit(object):
    def __init__(self, *args):
        self.requestID, self.subcommand, self.status = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create ChannelGetRequestInit from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ChannelGetRequestInit` instance
        """
        requestID = buffer.get_integer()
        subcommand = buffer.get_byte()
        status = Status.from_buffer(buffer)

        return ChannelGetResponseInit(requestID, subcommand, status)

    def to_buffer(self):
        pass


class ChannelGetFieldRequest(object):
    def __init__(self, *args):
        self.serverChannelID, self.requestID, self.subFieldName = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create ChannelGetFieldRequest from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ChannelGetFieldRequest` instance
        """
        serverChannelID = buffer.get_integer()
        requestID = buffer.get_integer()
        subFieldName = buffer.get_string()

        return ChannelGetResponseInit(serverChannelID, requestID, subFieldName)

    def to_buffer(self):
        header = MessageHeader(
            flags=HeaderFlag(direction=MessageDirection.Server),
            messageCommand=ApplicationMessageCode.ChannelIF
        )
        buffer = BufferWriter()
        buffer.put_integer(self.serverChannelID)
        buffer.put_integer(self.requestID)
        buffer.put_string(self.subFieldName)

        header.payloadSize = len(buffer)
        return header.to_buffer() + buffer.get_buffer()

    def __str__(self):
        return \
            'ChannelGetFieldRequest\n'\
            '  serverChannelID:  %d\n'\
            '  requestID:        %d\n'\
            '  subFieldName:     %s\n' \
            % (self.serverChannelID, self.requestID, self.subFieldName)


class ChannelGetFieldResponse(object):
    def __init__(self, *args):
        self.requestID, self.status, self.subFieldIF = args

    @staticmethod
    def from_buffer(buffer):
        """
        Create ChannelGetFieldResponse from *buffer*

        :param :class:`BufferReader` buffer:
        :return: :class:`ChannelGetFieldResponse` instance
        """
        requestID = buffer.get_integer()
        status = Status.from_buffer(buffer)

        return ChannelGetFieldResponse(requestID, status, None)


    def __str__(self):
        return \
            'ChannelGetFieldResponse\n'\
            '  requestID:  %d\n'\
            '  status:     %s\n'\
            % (self.requestID, self.status)


class ClientMessageDispatcher(object):

    def __init__(self, tranport):
        self.transport = tranport
        self.pending = False

    def data_received(self, data):
        buffer = BufferReader(data)

        while len(buffer) > 0:
            if len(buffer) < constants.PVA_MESSAGE_HEADER_SIZE:
                return -1

            header = MessageHeader.from_buffer(buffer)
            print(header)

            if len(buffer) < header.payloadSize:
                return -1

            if header.messageCommand == ApplicationMessageCode.ConnectionValidation:
                request = ConnectionValidationRequest.from_buffer(buffer)
                print(request)

                response = ConnectionValidationResponse(request.serverReceiverBufferSize,
                                                        request.serverIntrospectionRegistryMaxSize,
                                                        0,
                                                        b'')
                self.send_data(response.to_buffer())
                self.pending = True
            elif header.messageCommand == ApplicationMessageCode.ConnectionValidated:
                response = ConnectionValidatedResponse.from_buffer(buffer)
                print(response)

                request = CreateChannelRequest([(1, b'testMP')])
                self.send_data(request.to_buffer())
                self.pending = True
            elif header.messageCommand == ApplicationMessageCode.CreateChannel:
                response = CreateChannelResponse.from_buffer(buffer)
                print(response)

                request = ChannelGetFieldRequest(response.serverChannelID, 1, b'')
                self.send_data(request.to_buffer())
                self.pending = True
            elif header.messageCommand == ApplicationMessageCode.ChannelIF:
                response = ChannelGetFieldResponse.from_buffer(buffer)
                print(response)
                fieldDesc = buffer.get_raw(header.payloadSize - 5)
                print(fieldDesc)
                print(fieldDesc.encode('hex'))
                self.pending = False
            else:
                buffer.skip_bytes(header.payloadSize)

        return self.pending

    def send_data(self, data):
        self.transport.send(data)


class ServerMessageDispatcher(object):

    def __init__(self, transport):
        self.transport = transport
        self.pending = False

    def data_received(self, data):
        buffer = BufferReader(data)

        while len(buffer) > 0:
            if len(buffer) < constants.PVA_MESSAGE_HEADER_SIZE:
                return -1

            header = MessageHeader.from_buffer(buffer)
            print(header)

            if len(buffer) < header.payloadSize:
                return -1

            if header.messageCommand == ApplicationMessageCode.ConnectionValidation:
                response = ConnectionValidationResponse.from_buffer(buffer)
                print(response)

                response = ConnectionValidatedResponse()
                self.send_data(response.to_buffer())
                self.pending = True
            elif header.messageCommand == ApplicationMessageCode.CreateChannel:
                request = CreateChannelRequest.from_buffer(buffer)
                print(request)

                for id_, name in request.channels:
                    response = CreateChannelResponse(id_, id_, Status(), 0)
                    self.send_data(response.to_buffer())
            else:
                buffer.skip_bytes(header.payloadSize)

    def send_data(self, data):
        self.transport.send(data)