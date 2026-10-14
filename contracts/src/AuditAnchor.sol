// SPDX-License-Identifier: MIT
pragma solidity >=0.8.11 <0.9.0;

/// @title AuditAnchor
/// @notice Keeps a public, append-only list of audit-log head hashes. The StudyRoute audit log is
///         a SHA-256 hash chain, which proves an event was not edited UNLESS an attacker can also
///         rewrite every later hash. A head hash written here is outside the database, so that
///         rewrite no longer goes unnoticed: the recomputed hash will not match the anchor.
/// @dev    Only the operator (the bank) can write. Anchors only ever move forward.
contract AuditAnchor {
    struct Anchor {
        uint64 seq;
        uint64 at;
        bytes32 head;
    }

    address public immutable operator;
    Anchor[] private anchors;

    event Anchored(uint256 indexed index, uint64 seq, bytes32 head, uint64 at);

    constructor(address operator_) {
        require(operator_ != address(0), "ZERO_OPERATOR");
        operator = operator_;
    }

    function anchor(uint64 seq, bytes32 head) external {
        require(msg.sender == operator, "ONLY_OPERATOR");
        require(head != bytes32(0), "EMPTY_HEAD");
        uint256 n = anchors.length;
        require(n == 0 || seq > anchors[n - 1].seq, "SEQ_NOT_INCREASING");
        anchors.push(Anchor(seq, uint64(block.timestamp), head));
        emit Anchored(n, seq, head, uint64(block.timestamp));
    }

    function count() external view returns (uint256) {
        return anchors.length;
    }

    function get(uint256 index) external view returns (uint64 seq, uint64 at, bytes32 head) {
        require(index < anchors.length, "NO_SUCH_ANCHOR");
        Anchor storage a = anchors[index];
        return (a.seq, a.at, a.head);
    }
}
