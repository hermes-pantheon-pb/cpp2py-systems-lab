// M4-L01 · C++ mental model: Pure virtual interface and C++20 concepts
#include <string>
#include <vector>
#include <concepts>
#include <iostream>

// 1. Classical OOP nominal interface
class IStorageBackend {
public:
    virtual ~IStorageBackend() = default;
    virtual std::vector<uint8_t> get(const std::string& key) = 0;
    virtual void put(const std::string& key, const std::vector<uint8_t>& val) = 0;
};

// 2. Modern C++20 structural concept
template <typename T>
concept StorageConcept = requires(T t, std::string k, std::vector<uint8_t> v) {
    { t.get(k) } -> std::same_as<std::vector<uint8_t>>;
    { t.put(k, v) } -> std::same_as<void>;
};

template <StorageConcept Backend>
class StorageService {
public:
    explicit StorageService(Backend backend) : backend_(std::move(backend)) {}
    std::vector<uint8_t> read(const std::string& k) { return backend_.get(k); }
    void write(const std::string& k, const std::vector<uint8_t>& v) { backend_.put(k, v); }
private:
    Backend backend_;
};
