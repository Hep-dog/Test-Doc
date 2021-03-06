# automatically generated by the FlatBuffers compiler, do not modify

# namespace: Detector

import flatbuffers
from flatbuffers.compat import import_numpy
np = import_numpy()

class RawData(object):
    __slots__ = ['_tab']

    @classmethod
    def GetRootAsRawData(cls, buf, offset):
        n = flatbuffers.encode.Get(flatbuffers.packer.uoffset, buf, offset)
        x = RawData()
        x.Init(buf, n + offset)
        return x

    # RawData
    def Init(self, buf, pos):
        self._tab = flatbuffers.table.Table(buf, pos)

    # RawData
    def PulseId(self):
        o = flatbuffers.number_types.UOffsetTFlags.py_type(self._tab.Offset(4))
        if o != 0:
            return self._tab.Get(flatbuffers.number_types.Uint64Flags, o + self._tab.Pos)
        return 0

    # RawData
    def RawValue(self, j):
        o = flatbuffers.number_types.UOffsetTFlags.py_type(self._tab.Offset(6))
        if o != 0:
            a = self._tab.Vector(o)
            return self._tab.Get(flatbuffers.number_types.Uint8Flags, a + flatbuffers.number_types.UOffsetTFlags.py_type(j * 1))
        return 0

    # RawData
    def RawValueAsNumpy(self):
        o = flatbuffers.number_types.UOffsetTFlags.py_type(self._tab.Offset(6))
        if o != 0:
            return self._tab.GetVectorAsNumpy(flatbuffers.number_types.Uint8Flags, o)
        return 0

    # RawData
    def RawValueLength(self):
        o = flatbuffers.number_types.UOffsetTFlags.py_type(self._tab.Offset(6))
        if o != 0:
            return self._tab.VectorLen(o)
        return 0

    # RawData
    def RawValueIsNone(self):
        o = flatbuffers.number_types.UOffsetTFlags.py_type(self._tab.Offset(6))
        return o == 0

def RawDataStart(builder): builder.StartObject(2)
def RawDataAddPulseId(builder, pulseId): builder.PrependUint64Slot(0, pulseId, 0)
def RawDataAddRawValue(builder, rawValue): builder.PrependUOffsetTRelativeSlot(1, flatbuffers.number_types.UOffsetTFlags.py_type(rawValue), 0)
def RawDataStartRawValueVector(builder, numElems): return builder.StartVector(1, numElems, 1)
def RawDataEnd(builder): return builder.EndObject()
