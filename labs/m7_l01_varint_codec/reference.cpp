// M7-L01 · C++ mental model: Protobuf varint and zigzag codec
#include <cstdint>
#include <vector>
#include <iostream>

std::vector<uint8_t> encode_varint(uint64_t val) {
    std::vector<uint8_t> out;
    while (val >= 0x80) {
        out.push_back(static_cast<uint8_t>((val & 0x7F) | 0x80));
        val >>= 7;
    }
    out.push_back(static_cast<uint8_t>(val & 0x7F));
    return out;
}

uint32_t encode_zigzag32(int32_t n) {
    return static_cast<uint32_t>((n << 1) ^ (n >> 31));
}

int32_t decode_zigzag32(uint32_t n) {
    return static_cast<int32_t>((n >> 1) ^ -(n & 1));
}
