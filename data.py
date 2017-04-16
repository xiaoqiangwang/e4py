from __future__ import print_function
import enum
import pprint


class ArrayFlag(enum.IntEnum):
    Scalar = 0x00
    VarSizeArray = 0x01
    BoundSizeArray = 0x02
    FixedSizeArray = 0x03

    def __str__(self):
        return self.name


class DataFlag(enum.IntEnum):
    # Boolean
    Boolean = 0
    # Integer
    Byte = 1
    UByte = 2
    Short = 3
    UShort = 4
    Int = 5
    UInt = 6
    Long = 7
    ULong = 8
    # float-point
    Float = 9
    Double = 10
    # string
    String = 11
    # Complex
    Structure = 12
    Union = 13
    VariantUnion = 14
    BoundedString = 15

    def __str__(self):
        return self.name


class FieldEncoding(enum.IntEnum):
    No = 0xFF
    Only_ID = 0xFE
    Full_ID = 0xFD
    Full_Tagged_ID = 0xFC


class DataRegistry(object):
    def __init__(self):
        self.registry = {}

    def register_type(self, id_, object_):
        self.registry[id_] = object_

    def get_type(self, id_):
        return self.registry[id_]

# singleton
registry = DataRegistry()


class DataType(object):
    """
    Field data type.

    Each Field introspection description (FieldDesc) MUST be encoded as a byte.

    +---+-------+---------------------------+
    |bit| Value | Description               |
    +===+=======+===========================+
    |   | 110   | reserved                  |
    |   +-------+                           |
    |   | 110   |                           |
    |   +-------+                           |
    |   | 101   |                           |
    |   +-------+---------------------------+
    |   | 100   | complex                   |
    |7-5+-------+---------------------------+
    |   | 011   | string                    |
    |   +-------+---------------------------+
    |   | 010   | floating-point            |
    |   +-------+---------------------------+
    |   | 001   | integer                   |
    |   +-------+---------------------------+
    |   | 000   | boolean                   |
    +---+-------+---------------------------+
    |   | 11    | fixed-size array          |
    |   +-------+---------------------------+
    |   | 10    | bounded-size array        |
    |4-3+-------+---------------------------+
    |   | 01    | variable-size array       |
    |   +-------+---------------------------+
    |   | 00    | scalar                    |
    +---+-------+---------------------------+
    |2-0|       | type (bits 7-5) dependant |
    +---+-------+---------------------------+

    * integer type

    +---+-------+-----------+
    |bit| Value | Type Name |
    +===+=======+===========+
    |   | 1     | unsigned  |
    | 2 +-------+-----------|
    |   | 0     | signed    |
    +---+-------+-----------+
    |   | 11    | long      |
    |   +-------+-----------+
    |   | 10    | int       |
    |1-0+-------+-----------+
    |   | 01    | short     |
    |   +-------+-----------+
    |   | 00    | byte      |
    +---+-------+-----------+

    * floating-point type

    +---+-------+-----------+-----------------------+
    |bit| Value | Type Name | IEEE 754-2008 Name    |
    +===+=======+===========+=======================+
    |   | 111   |                                   |
    |   +-------+                                   |
    |   | 110   |     reserved                      |
    |   +-------+                                   |
    |   | 101   |                                   |
    |   +-------+-----------+-----------------------+
    |   | 100   | reserved  | binary128 (Quadruple) |
    |2-0+-------+-----------+-----------------------+
    |   | 011   | double    | binary64 (Double)     |
    |   +-------+-----------+-----------------------+
    |   | 010   | float     | binary32 (Single)     |
    |   +-------+-----------+-----------------------+
    |   | 001   | reserved  | binary16 (Half)       |
    |   +-------+-----------+-----------------------+
    |   | 000   | reserved                          |
    +---+-------+-----------------------------------+

    * complex type

    +---+-------+----------------+
    |bit| Value | Type Name      |
    +===+=======+================+
    |   | 111   |                |
    |   +-------+                |
    |   | 110   |                |
    |   +-------+ reserved       |
    |   | 101   |                |
    |   +-------+                |
    |   | 100   |                |
    |2-0+-------+----------------+
    |   | 011   | bounded string |
    |   +-------+----------------+
    |   | 010   | variant union  |
    |   +-------+----------------+
    |   | 001   | union          |
    |   +-------+----------------+
    |   | 000   | structure      |
    +---+-------+----------------+
    """

    def __init__(self, *args):
        self.type_code, self.array_flag = args

    def __str__(self):
        if self.array_flag == ArrayFlag.Scalar:
            return '%s' % self.type_code
        elif self.array_flag == ArrayFlag.VarSizeArray:
            return '%s[]' % self.type_code
        elif self.array_flag == ArrayFlag.FixedSizeArray:
            return '%s[]' % self.type_code
        elif self.array_flag == ArrayFlag.BoundSizeArray:
            return  '%s<>' % self.type_code

    def to_field_desc(self):
        array_bits = self.array_flag << 3
        subtype_bits = 0
        if self.type_code == DataFlag.Boolean:
            major_bits = 0b000

        elif self.type_code <= DataFlag.ULong and self.type_code >= DataFlag.Byte:
            major_bits = 0b001
            if (self.type_code - DataFlag.Byte) % 2 == 0:
                subtype_bits = (self.type_code - DataFlag.Byte) / 2
            elif (self.type_code - DataFlag.UByte) % 2 == 0:
                subtype_bits = (self.type_code - DataFlag.UByte) / 2
                subtype_bits |= 0b100

        elif self.type_code == DataFlag.Float:
            major_bits = 0b010
            subtype_bits = 0b010

        elif self.type_code == DataFlag.Double:
            major_bits = 0b010
            subtype_bits = 0b011

        elif self.type_code == DataFlag.String:
            major_bits = 0b011

        else:
            major_bits = 0b100
            subtype_bits = self.type_code - DataFlag.Structure

        return major_bits << 5 | array_bits | subtype_bits

    @staticmethod
    def from_field_desc(field_desc):
        # bit 3-4 is array flag
        array_flag = ArrayFlag((field_desc & 0x18) >> 3)
        # bit 6-7 is type selection
        major_code = (field_desc & 0xE0) >> 5
        # bit 0-2 is dependant on major type
        sub_code = field_desc & 0x07

        if major_code == 0b000:
            type_code = DataFlag.Boolean

        elif major_code == 0b001: # integer
            if sub_code & 0b100: # unsigned
                type_code = DataFlag(DataFlag.UByte + (sub_code & 0b011) * 2)
            else:
                type_code = DataFlag(DataFlag.Byte + (sub_code & 0b011) * 2)

        elif major_code == 0b010: # floating-point
            if sub_code == 0b010:
                type_code = DataFlag.Float
            elif sub_code == 0b011:
                type_code = DataFlag.Double

        elif major_code == 0b011:
            type_code = DataFlag.String

        elif major_code == 0b100:
            type_code = DataFlag(DataFlag.Structure + sub_code)

        return DataType(type_code, array_flag)


class DataObject(object):
    """
    Generic introspectional data object.

    :data:`DataObject.type_` describes the basic data type, boolean, string, byte, ubyte, structure, union or array of them.
    :data:`DataObject.size` designates the size of the data type. For structure, it is the number of fields.
    For fixed or bounded array, it is the number of elements. For scalar type, it is always 0.
    :data:`DataObject.fields` is a list of fields. Each field is a (*name*, :class:`DataObject`) tuple.

    """
    def __init__(self, *args):
        self.type_, self.size, self.fields = args
        self.name = b''

    @staticmethod
    def from_buffer(buffer):
        field_enc = buffer.get_byte()
        if field_enc == FieldEncoding.No:
            return None
        elif field_enc == FieldEncoding.Only_ID:
            id_ = buffer.get_short()
            return registry.get_type(id_)
        elif field_enc == FieldEncoding.Full_ID or field_enc == FieldEncoding.Full_Tagged_ID:
            id_ = buffer.get_short()
            tag = b''
            if field_enc == FieldEncoding.Full_Tagged_ID:
                tag = buffer.get_string()
            data_type = DataType.from_field_desc(buffer.get_byte())
            if data_type.type_code == DataFlag.Structure or data_type.type_code == DataFlag.Union:
                if data_type.array_flag == ArrayFlag.Scalar:
                    name_ = buffer.get_string()
                    size = buffer._get_size()
                    fields = []
                    for i in range(size):
                        name = buffer.get_string()
                        object_ = DataObject.from_buffer(buffer)
                        fields.append((name, object_))
                    object_ = DataObject(data_type, size, fields)
                    object_.name = name_
                    registry.register_type(id_, object_)
                    return object_
                else:
                    object_ = DataObject.from_buffer(buffer)
                    return object_
            elif data_type.type_code == DataFlag.VariantUnion:
                object_ = DataObject(data_type, 0, [])
                registry.register_type(id_, object_)
                return object_
            elif data_type.type_code == DataFlag.BoundedString:
                name = buffer.get_string()
                size = buffer._get_size()
                object_ = DataObject(data_type, size, [])
                object_.name = name
                registry.register_type(id_, object_)
                return object_
        else:
            data_type = DataType.from_field_desc(field_enc)
            size = 0
            if data_type.array_flag == ArrayFlag.FixedSizeArray or data_type.array_flag == ArrayFlag.BoundSizeArray:
                size = buffer._get_size()
            return DataObject(data_type, size, [])


    def __str__(self):
        output = '%s %s %d' % (self.name, self.type_, self.size)
        for name, object_ in self.fields:
            output += '\n  %s: %s' % (name, object_)
        return output

if __name__ == '__main__':
    import codecs
    import hexdump
    import sys
    from messages import BufferReader

    desc1 = \
    b"FD 00 01 80  0B 74 69 6D  65 53 74 61  6D 70 5F 74"\
    b"03 10 73 65  63 6F 6E 64  73 50 61 73  74 45 70 6F"\
    b"63 68 23 0B  6E 61 6E 6F  53 65 63 6F  6E 64 73 22"\
    b"07 75 73 65  72 54 61 67  22"

    desc2 = \
    b'FD 00 01 80  10 65 78 61  6D 70 6C 65  53 74 72 75'\
    b'63 74 75 72  65 07 05 76  61 6C 75 65  28 10 62 6F'\
    b'75 6E 64 65  64 53 69 7A  65 41 72 72  61 79 30 10'\
    b'0E 66 69 78  65 64 53 69  7A 65 41 72  72 61 79 38'\
    b'04 09 74 69  6D 65 53 74  61 6D 70 FD  00 02 80 06'\
    b'74 69 6D 65  5F 74 03 10  73 65 63 6F  6E 64 73 50'\
    b'61 73 74 45  70 6F 63 68  23 0B 6E 61  6E 6F 73 65'\
    b'63 6F 6E 64  73 22 07 75  73 65 72 54  61 67 22 05'\
    b'61 6C 61 72  6D FD 00 03  80 07 61 6C  61 72 6D 5F'\
    b'74 03 08 73  65 76 65 72  69 74 79 22  06 73 74 61'\
    b'74 75 73 22  07 6D 65 73  73 61 67 65  60 0A 76 61'\
    b'6C 75 65 55  6E 69 6F 6E  FD 00 04 81  00 03 0B 73'\
    b'74 72 69 6E  67 56 61 6C  75 65 60 08  69 6E 74 56'\
    b'61 6C 75 65  22 0B 64 6F  75 62 6C 65  56 61 6C 75'\
    b'65 43 0C 76  61 72 69 61  6E 74 55 6E  69 6F 6E FD'\
    b'00 05 82'

    desc3 = b'fd0100801665706963733a6e742f4e544e4441727261793a312e30080576616c7'\
           b'565fd020081000b0c626f6f6c65616e56616c756508096279746556616c756528'\
           b'0a73686f727456616c75652908696e7456616c75652a096c6f6e6756616c75652'\
           b'b0a756279746556616c75652c0b7573686f727456616c75652d0975696e745661'\
           b'6c75652e0a756c6f6e6756616c75652f0a666c6f617456616c75654a0b646f756'\
           b'26c6556616c75654b05636f646563fd03008007636f6465635f7402046e616d65'\
           b'600a706172616d6574657273fd0400820e636f6d7072657373656453697a65231'\
           b'0756e636f6d7072657373656453697a65230964696d656e73696f6efd050088fd'\
           b'0600800b64696d656e73696f6e5f74050473697a6522066f666673657422086675'\
           b'6c6c53697a65220762696e6e696e672207726576657273650008756e697175654'\
           b'964220d6461746154696d655374616d70fd0700800674696d655f740310736563'\
           b'6f6e64735061737445706f6368230b6e616e6f7365636f6e64732207757365725'\
           b'461672209617474726962757465fd080088fd0900801865706963733a6e742f4e'\
           b'544174747269627574653a312e3005046e616d65600576616c7565fe04000a646'\
           b'57363726970746f72600a736f75726365547970652206736f7572636560'

    if len(sys.argv) == 1:
        byte = codecs.decode(desc3.replace(b' ', b''), 'hex')
        hexdump.hexdump(byte)
        buffer = BufferReader(byte)
        object_ = DataObject.from_buffer(buffer)
        print(object_)
    else:
        for desc in sys.argv[1:]:
            base = 10
            if desc.startswith('0x'):
                base = 16
            type_ = DataType.from_field_desc(int(desc, base))
            print(type_)

            desc = type_.to_field_desc()

            print(hex(desc))
