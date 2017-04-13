import enum
from messages import BufferReader

class ArrayFlag(enum.IntEnum):
    Scalar = 0x00
    VarSizeArray = 0x01
    BoundSizeArray = 0x02
    FixedSizeArray = 0x03


class DataFlag(enum.IntEnum):
    # boolean
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


class FieldEncoding(enum.IntEnum):
    No = 0xFF
    Only_ID = 0xFE
    Full_ID = 0xFD
    Full_Tagged_ID = 0xFC


class DataRegistry(object):
    def __init__(self):
        self.registry = {}

    def register_type(self, id_, object_):
        self.registry[id_] = object

    def get_type(self, id_):
        return self.registry[id_]


registry = DataRegistry()


class DataType(object):
    fields = []

    def __init(self, id_, type_code, ):
        self.id_ = id_

    @staticmethod
    def from_field_desc(field_desc):
        array_flag = ArrayFlag((field_desc & 0x18) >> 3)

        major_code = (field_desc & 0xE0) >> 5
        subtype_code = field_desc & 0x07

        if major_code == 0b000:
            type_code = DataFlag.Boolean

        elif major_code == 0b001: # integer
            if subtype_code & 0b100: # unsigned
                type_code = DataFlag(DataFlag.UByte + (subtype_code & 0b011) * 2)
            else:
                type_code = DataFlag(DataFlag.Byte + (subtype_code & 0b011) * 2)

        elif major_code == 0b010: # floating-point
            if subtype_code == 0b010:
                type_code = DataFlag.Float
            elif subtype_code == 0b011:
                type_code = DataFlag.Double

        elif major_code == 0b011:
            type_code = DataFlag.String

        elif major_code == 0b100:
            type_code = DataFlag(DataFlag.Structure + subtype_code)

        return type_code, array_flag


class DataObject(object):
    def __init__(self, *args):
        self.id_, self.name, self.fields = args

    @staticmethod
    def from_buffer(buffer):
        field_enc = buffer.get_byte()
        if field_enc == FieldEncoding.No:
            return None
        elif field_enc == FieldEncoding.Only_ID:
            id_ = buffer.get_short()
            return registry.get_type(id_)
        elif field_enc == FieldEncoding.Full_ID:
            id_ = buffer.get_short()
            type_code, array_flag = DataType.from_field_desc(buffer.get_byte())
            name = buffer.get_string()
            if type_code == DataFlag.Structure:
                size = buffer._get_size()
                fields = []
                for i in range(size):
                    object_ = DataObject.from_buffer(buffer)
                    fields.append((name, object_))
                return DataObject(id_, name, fields)
            elif type_code == DataFlag.Union:
                pass
            elif type_code == DataFlag.VariantUnion:
                pass
            elif type_code == DataFlag.BoundedString:
                pass
            else:
                name = buffer.get_string()
                type_code, array_flag = DataType.from_field_desc(buffer.get_byte())
                print(name, type_code, array_flag)
                return DataObject(field_enc, name, [])

        elif field_enc == FieldEncoding.Full_Tagged_ID:
            pass
        else:
            buffer.index -= 1
            name = buffer.get_string()
            type_code, array_flag = DataType.from_field_desc(buffer.get_byte())
            size = 0
            if array_flag == ArrayFlag.FixedSizeArray or array_flag == ArrayFlag.BoundSizeArray:
                size = buffer._get_size()
            return DataObject(field_enc, name, [])

        return

    def __str__(self):
        for name, object_ in self.fields:
            print(name)
            if object_ is not None:
                print(object_)

if __name__ == '__main__':
    import codecs
    import sys

    desc = \
    b"FD 00 01 80  0B 74 69 6D  65 53 74 61  6D 70 5F 74 03 10 73 65  63 6F 6E 64  73 50 61 73  74 45 70 6F"\
    b"63 68 23 0B  6E 61 6E 6F  53 65 63 6F  6E 64 73 22 07 75 73 65  72 54 61 67  22"

    desc = \
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

    if len(sys.argv) == 1:
        print(DataObject.from_buffer(BufferReader(codecs.decode(desc.replace(b' ', b''), 'hex'))))

    else:
        for desc in sys.argv[1:]:
            base = 10
            if desc.startswith('0x'):
                base = 16
            print(DataType.from_field_desc(int(desc, base)))