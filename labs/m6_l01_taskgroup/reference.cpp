// M6-L01 · C++ mental model: jthread and stop_token structured concurrency
#include <iostream>
#include <vector>
#include <thread>
#include <future>
#include <chrono>

template <typename T, typename Func>
auto fanout_pipeline(const std::vector<T>& items, Func worker) {
    using Result = decltype(worker(items[0]));
    std::vector<std::future<Result>> futures;
    futures.reserve(items.size());

    // Launch workers using jthreads
    for (const auto& item : items) {
        futures.push_back(std::async(std::launch::async, [worker, item] {
            return worker(item);
        }));
    }

    std::vector<Result> results;
    for (auto& fut : futures) {
        results.push_back(fut.get());
    }
    return results;
}
