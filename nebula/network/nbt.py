"""
NBT (Named Binary Tag) 处理模块
1.12.2简化版 - 只实现必要的NBT功能
"""

import struct
import io
from typing import Any, Dict, List, Union


class NBT_TAG:
    """NBT标签类型常量"""
    END = 0
    BYTE = 1
    SHORT = 2
    INT = 3
    LONG = 4
    FLOAT = 5
    DOUBLE = 6
    BYTE_ARRAY = 7
    STRING = 8
    LIST = 9
    COMPOUND = 10
    INT_ARRAY = 11
    LONG_ARRAY = 12


class NBTWriter:
    """NBT数据写入器"""
    
    def __init__(self):
        self.stream = io.BytesIO()
    
    def get_bytes(self) -> bytes:
        return self.stream.getvalue()
    
    def write_byte(self, value: int):
        # 处理可能超过有符号 8 位整数范围的值
        if value < 0:
            value = value & 0xFF  # 确保在 8 位范围内
        if value >= 2**7:
            value = value - 2**8  # 转换为负数
        self.stream.write(struct.pack('b', value))
    
    def write_short(self, value: int):
        # 处理可能超过有符号 16 位整数范围的值
        if value < 0:
            value = value & 0xFFFF  # 确保在 16 位范围内
        if value >= 2**15:
            value = value - 2**16  # 转换为负数
        self.stream.write(struct.pack('>h', value))
    
    def write_int(self, value: int):
        # 处理可能超过有符号 32 位整数范围的值
        if value < 0:
            value = value & 0xFFFFFFFF  # 确保在 32 位范围内
        if value >= 2**31:
            value = value - 2**32  # 转换为负数
        self.stream.write(struct.pack('>i', value))
    
    def write_long(self, value: int):
        # 处理可能超过有符号 64 位整数范围的值
        # 将无符号 64 位整数转换为有符号格式
        if value < 0:
            value = value & 0xFFFFFFFFFFFFFFFF  # 确保在 64 位范围内
        if value >= 2**63:
            value = value - 2**64  # 转换为负数
        self.stream.write(struct.pack('>q', value))
    
    def write_float(self, value: float):
        self.stream.write(struct.pack('>f', value))
    
    def write_double(self, value: float):
        self.stream.write(struct.pack('>d', value))
    
    def write_string(self, value: str):
        encoded = value.encode('utf-8')
        self.write_short(len(encoded))
        self.stream.write(encoded)
    
    def write_byte_array(self, value: bytes):
        self.write_int(len(value))
        self.stream.write(value)
    
    def write_int_array(self, value: List[int]):
        self.write_int(len(value))
        for v in value:
            self.write_int(v)
    
    def write_long_array(self, value: List[int]):
        self.write_int(len(value))
        for v in value:
            self.write_long(v)
    
    def write_tag_header(self, tag_type: int, name: str = ""):
        self.write_byte(tag_type)
        if tag_type != NBT_TAG.END:
            self.write_string(name)
    
    def write_compound(self, data: Dict[str, Any], name: str = ""):
        """写入复合标签"""
        self.write_tag_header(NBT_TAG.COMPOUND, name)
        for key, value in data.items():
            self._write_named_tag(key, value)
        self.write_byte(NBT_TAG.END)
    
    def _write_named_tag(self, name: str, value: Any):
        """根据值的类型写入命名标签"""
        if isinstance(value, bool):
            self.write_tag_header(NBT_TAG.BYTE, name)
            self.write_byte(1 if value else 0)
        elif isinstance(value, int):
            # 默认使用INT类型
            if -128 <= value <= 127:
                self.write_tag_header(NBT_TAG.BYTE, name)
                self.write_byte(value)
            elif -32768 <= value <= 32767:
                self.write_tag_header(NBT_TAG.SHORT, name)
                self.write_short(value)
            elif -2147483648 <= value <= 2147483647:
                self.write_tag_header(NBT_TAG.INT, name)
                self.write_int(value)
            else:
                self.write_tag_header(NBT_TAG.LONG, name)
                self.write_long(value)
        elif isinstance(value, float):
            self.write_tag_header(NBT_TAG.DOUBLE, name)
            self.write_double(value)
        elif isinstance(value, str):
            self.write_tag_header(NBT_TAG.STRING, name)
            self.write_string(value)
        elif isinstance(value, bytes):
            self.write_tag_header(NBT_TAG.BYTE_ARRAY, name)
            self.write_byte_array(value)
        elif isinstance(value, list):
            if value and isinstance(value[0], int):
                # 检查是否需要使用 LONG_ARRAY（值超出 INT 范围）
                needs_long = any(v < -2147483648 or v > 2147483647 for v in value)
                if needs_long:
                    self.write_tag_header(NBT_TAG.LONG_ARRAY, name)
                    self.write_long_array(value)
                else:
                    self.write_tag_header(NBT_TAG.INT_ARRAY, name)
                    self.write_int_array(value)
            else:
                self.write_tag_header(NBT_TAG.LIST, name)
                self._write_list(value)
        elif isinstance(value, dict):
            self.write_tag_header(NBT_TAG.COMPOUND, name)
            for k, v in value.items():
                self._write_named_tag(k, v)
            self.write_byte(NBT_TAG.END)
    
    def _write_list(self, items: List[Any]):
        """写入列表标签"""
        if not items:
            self.write_byte(NBT_TAG.END)
            self.write_int(0)
            return
        
        # 推断元素类型
        first = items[0]
        if isinstance(first, bool):
            elem_type = NBT_TAG.BYTE
        elif isinstance(first, int):
            elem_type = NBT_TAG.INT
        elif isinstance(first, float):
            elem_type = NBT_TAG.DOUBLE
        elif isinstance(first, str):
            elem_type = NBT_TAG.STRING
        elif isinstance(first, dict):
            elem_type = NBT_TAG.COMPOUND
        else:
            elem_type = NBT_TAG.STRING
        
        self.write_byte(elem_type)
        self.write_int(len(items))
        
        for item in items:
            if elem_type == NBT_TAG.BYTE:
                self.write_byte(1 if item else 0)
            elif elem_type == NBT_TAG.SHORT:
                self.write_short(item)
            elif elem_type == NBT_TAG.INT:
                self.write_int(item)
            elif elem_type == NBT_TAG.LONG:
                self.write_long(item)
            elif elem_type == NBT_TAG.FLOAT:
                self.write_float(item)
            elif elem_type == NBT_TAG.DOUBLE:
                self.write_double(item)
            elif elem_type == NBT_TAG.STRING:
                self.write_string(item)
            elif elem_type == NBT_TAG.COMPOUND:
                for k, v in item.items():
                    self._write_named_tag(k, v)
                self.write_byte(NBT_TAG.END)


def write_nbt(data: Dict[str, Any]) -> bytes:
    """
    将字典数据写入NBT格式
    返回完整的NBT字节数据
    """
    writer = NBTWriter()
    # 根标签必须是Compound
    if data:
        first_key = list(data.keys())[0]
        writer.write_compound(data[first_key], first_key)
    else:
        writer.write_compound({}, "")
    return writer.get_bytes()


def write_nbt_to_bytes(data: Dict[str, Any]) -> bytes:
    """写入NBT数据，根标签包含所有键"""
    writer = NBTWriter()
    # 根标签是包含所有数据的Compound
    writer.write_byte(NBT_TAG.COMPOUND)
    writer.write_string("")  # 根标签名称为空
    for key, value in data.items():
        writer._write_named_tag(key, value)
    writer.write_byte(NBT_TAG.END)
    return writer.get_bytes()


class NBTReader:
    """NBT数据读取器"""
    
    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)
    
    def read_byte(self) -> int:
        return struct.unpack('b', self.stream.read(1))[0]
    
    def read_ubyte(self) -> int:
        return struct.unpack('B', self.stream.read(1))[0]
    
    def read_short(self) -> int:
        return struct.unpack('>h', self.stream.read(2))[0]
    
    def read_int(self) -> int:
        return struct.unpack('>i', self.stream.read(4))[0]
    
    def read_long(self) -> int:
        return struct.unpack('>q', self.stream.read(8))[0]
    
    def read_float(self) -> float:
        return struct.unpack('>f', self.stream.read(4))[0]
    
    def read_double(self) -> float:
        return struct.unpack('>d', self.stream.read(8))[0]
    
    def read_string(self) -> str:
        length = self.read_short()
        return self.stream.read(length).decode('utf-8')
    
    def read_byte_array(self) -> bytes:
        length = self.read_int()
        return self.stream.read(length)
    
    def read_int_array(self) -> List[int]:
        length = self.read_int()
        return [self.read_int() for _ in range(length)]
    
    def read_long_array(self) -> List[int]:
        length = self.read_int()
        return [self.read_long() for _ in range(length)]
    
    def read_compound(self) -> Dict[str, Any]:
        """读取复合标签"""
        result = {}
        while True:
            tag_type = self.read_ubyte()
            if tag_type == NBT_TAG.END:
                break
            name = self.read_string()
            value = self._read_tag_value(tag_type)
            result[name] = value
        return result
    
    def _read_tag_value(self, tag_type: int) -> Any:
        """根据标签类型读取值"""
        if tag_type == NBT_TAG.BYTE:
            return self.read_byte()
        elif tag_type == NBT_TAG.SHORT:
            return self.read_short()
        elif tag_type == NBT_TAG.INT:
            return self.read_int()
        elif tag_type == NBT_TAG.LONG:
            return self.read_long()
        elif tag_type == NBT_TAG.FLOAT:
            return self.read_float()
        elif tag_type == NBT_TAG.DOUBLE:
            return self.read_double()
        elif tag_type == NBT_TAG.BYTE_ARRAY:
            return self.read_byte_array()
        elif tag_type == NBT_TAG.STRING:
            return self.read_string()
        elif tag_type == NBT_TAG.LIST:
            return self._read_list()
        elif tag_type == NBT_TAG.COMPOUND:
            return self.read_compound()
        elif tag_type == NBT_TAG.INT_ARRAY:
            return self.read_int_array()
        elif tag_type == NBT_TAG.LONG_ARRAY:
            return self.read_long_array()
        else:
            raise ValueError(f"Unknown tag type: {tag_type}")
    
    def _read_list(self) -> List[Any]:
        """读取列表标签"""
        elem_type = self.read_ubyte()
        length = self.read_int()
        result = []
        for _ in range(length):
            if elem_type == NBT_TAG.COMPOUND:
                result.append(self.read_compound())
            else:
                result.append(self._read_tag_value(elem_type))
        return result
    
    @staticmethod
    def read(data: bytes) -> Dict[str, Any]:
        """读取NBT数据，返回字典"""
        reader = NBTReader(data)
        # 读取根标签
        tag_type = reader.read_ubyte()
        if tag_type != NBT_TAG.COMPOUND:
            raise ValueError("Root tag must be a compound")
        name = reader.read_string()  # 根标签名称
        return reader.read_compound()
