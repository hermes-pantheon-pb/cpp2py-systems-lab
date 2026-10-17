// M8-L01 · C++ mental model: gRPC synchronous servicer
#include <grpcpp/grpcpp.h>
#include <unordered_map>
#include <mutex>
#include <string>

// Conceptual C++ Servicer
class KeyValueServiceImpl final /* : public KeyValueService::Service */ {
public:
    /*
    grpc::Status Get(grpc::ServerContext* context, const GetRequest* request, GetResponse* response) override {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = store_.find(request->key());
        if (it == store_.end()) {
            return grpc::Status(grpc::StatusCode::NOT_FOUND, "Key not found");
        }
        response->set_key(request->key());
        response->set_value(it->second);
        return grpc::Status::OK;
    }
    */
private:
    std::mutex mu_;
    std::unordered_map<std::string, std::string> store_;
};
