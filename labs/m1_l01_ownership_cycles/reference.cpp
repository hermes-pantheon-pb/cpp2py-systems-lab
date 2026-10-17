// M1-L01 · C++ mental model: owning children, non-owning back-pointer.
#include <memory>
#include <string>
#include <vector>

class Node {
public:
    explicit Node(std::string name) : name_(std::move(name)) {}

    Node& add_child(std::unique_ptr<Node> child) {
        child->parent_ = this;                  // non-owning back-pointer
        children_.push_back(std::move(child));  // owning edge
        return *children_.back();
    }

    Node* parent() const { return parent_; }    // nullptr for a root

    const std::vector<std::unique_ptr<Node>>& children() const {
        return children_;
    }

    std::string path() const {
        return parent_ ? parent_->path() + "/" + name_ : name_;
    }

private:
    std::string name_;
    Node* parent_ = nullptr;                      // does NOT own
    std::vector<std::unique_ptr<Node>> children_; // owns
};

int main() {
    auto root = std::make_unique<Node>("root");
    Node& a = root->add_child(std::make_unique<Node>("a"));
    a.add_child(std::make_unique<Node>("b"));
}   // ~root → ~a → ~b : whole tree destroyed deterministically here
