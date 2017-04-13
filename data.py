import enum


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


class DataType(object):
    fields = []

    def __init(self, id_, type_code, ):
        self.id_ = id_

    @staticmethod
    def from_field_desc(field_desc):
        array_flag = ArrayFlag((field_desc & 0x18) >> 3)

        major_code = (field_desc & 0xE0) >> 5
        subtype_code = field_desc & 0x07

        print(major_code, subtype_code)

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

    @staticmethod
    def from_buffer(buffer):
        pass


if __name__ == '__main__':
    import sys
    for desc in sys.argv[1:]:
        base = 10
        if desc.startswith('0x'):
            base = 16
        print(DataType.from_field_desc(int(desc, base)))