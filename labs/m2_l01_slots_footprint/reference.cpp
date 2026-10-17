// M2-L01 · C++ mental model: contiguous POD struct
#include <cstdint>
#include <vector>
#include <numeric>
#include <iostream>

struct alignas(8) Tick {
    uint32_t ts;   // 4 bytes (+ 4 padding)
    double   px;   // 8 bytes
    uint32_t qty;  // 4 bytes (+ 4 padding)
};                 // Total: 24 bytes

static_assert(sizeof(Tick) == 24, "Tick must be 24 bytes");

int main() {
    constexpr size_t N = 100'000;
    std::vector<Tick> ticks;
    ticks.reserve(N);

    for (uint32_t i = 0; i < N; ++i) {
        ticks.push_back(Tick{1'700'000'000 + i, 100.5 + (i % 10), 10 + (i % 50)});
    }

    // Contiguous memory: exactly N * sizeof(Tick) == 2,400,000 bytes (~2.28 MiB)
    std::cout << "Vector bytes: " << ticks.size() * sizeof(Tick) << "\n";
    return 0;
}
