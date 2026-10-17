// M5-L01 · C++ mental model: single-flight via shared_future map
#include <iostream>
#include <unordered_map>
#include <future>
#include <mutex>
#include <string>
#include <chrono>
#include <thread>

template <typename K, typename V, typename Loader>
class SingleFlightCache {
public:
    explicit SingleFlightCache(Loader loader) : loader_(std::move(loader)) {}

    V get(const K& key) {
        std::shared_future<V> fut;
        bool is_leader = false;

        {
            std::lock_guard<std::mutex> lock(mu_);
            auto it = cache_.find(key);
            if (it != cache_.end()) {
                return it->second;
            }

            auto fit = in_flight_.find(key);
            if (fit != in_flight_.end()) {
                fut = fit->second;
            } else {
                std::promise<V> prom;
                fut = prom.get_future().share();
                in_flight_[key] = fut;
                is_leader = true;

                // Launch worker or execute in leader outside lock
                std::thread([this, key, prom = std::move(prom)]() mutable {
                    try {
                        V val = loader_(key);
                        {
                            std::lock_guard<std::mutex> inner(mu_);
                            cache_[key] = val;
                            in_flight_.erase(key);
                        }
                        prom.set_value(val);
                    } catch (...) {
                        {
                            std::lock_guard<std::mutex> inner(mu_);
                            in_flight_.erase(key);
                        }
                        prom.set_exception(std::current_exception());
                    }
                }).detach();
            }
        }

        // Wait on the future outside the mutex!
        return fut.get();
    }

private:
    Loader loader_;
    std::mutex mu_;
    std::unordered_map<K, V> cache_;
    std::unordered_map<K, std::shared_future<V>> in_flight_;
};
