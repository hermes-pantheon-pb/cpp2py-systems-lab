// M3-L01 · C++ mental model: RAII deterministic destruction
#include <iostream>
#include <string>
#include <stdexcept>

class Connection {
public:
    explicit Connection(std::string endpoint) : endpoint_(std::move(endpoint)), is_closed_(false) {
        std::cout << "Connecting to " << endpoint_ << "\n";
    }

    ~Connection() {
        close();
    }

    // Disable copying, allow moving
    Connection(const Connection&) = delete;
    Connection& operator=(const Connection&) = delete;
    Connection(Connection&& other) noexcept : endpoint_(std::move(other.endpoint_)), is_closed_(other.is_closed_) {
        other.is_closed_ = true;
    }

    void send(const std::string& msg) {
        if (is_closed_) throw std::runtime_error("Connection closed");
        // send msg...
    }

    void close() {
        if (!is_closed_) {
            is_closed_ = true;
            std::cout << "Closed " << endpoint_ << "\n";
        }
    }

    bool is_closed() const { return is_closed_; }

private:
    std::string endpoint_;
    bool is_closed_;
};

int main() {
    {
        Connection conn("127.0.0.1:50051");
        conn.send("ping");
    } // ~Connection() called deterministically right here at closing brace
    return 0;
}
