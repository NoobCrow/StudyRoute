// SPDX-License-Identifier: MIT
pragma solidity >=0.8.11 <0.9.0;

interface IDeposit {
    function transfer(address to, uint256 value) external returns (bool);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

/// @title TuitionEscrow
/// @notice Programmable tuition and living-cost payments. A parent (the payer) locks a bank's
///         tokenised deposit for a university or a student (the beneficiary) in one or more
///         tranches. Each tranche is released on its date, or earlier if the payer says so.
///         Not-yet-due tranches can be taken back by the payer, or returned by the beneficiary
///         (for example after a refused visa).
/// @dev    The bank's compliance officer can FREEZE an escrow and UNFREEZE it, nothing more:
///         there is no function that lets anyone but the payer or the beneficiary move funds.
///         Amounts are integers in the token's minor unit. It runs on a SIMULATED chain in the
///         StudyRoute sandbox; no real money is involved.
contract TuitionEscrow {
    enum Status { None, Active, Frozen, Completed, Cancelled }
    enum State { Locked, Released, Refunded }

    struct Tranche {
        uint256 amount;
        uint64 releaseAfter;
        State state;
    }

    struct Escrow {
        address payer;
        address beneficiary;
        address token;
        bytes32 ref;
        Status status;
        uint256 lockedTotal;
        uint256 refundedTotal;
        Tranche[] tranches;
    }

    uint256 public constant MAX_TRANCHES = 60;

    address public immutable compliance;
    uint256 public escrowCount;
    mapping(uint256 => Escrow) private escrows;
    bool private busy;

    event Created(
        uint256 indexed id,
        address indexed payer,
        address indexed beneficiary,
        address token,
        bytes32 ref,
        uint256 total,
        uint256 tranches
    );
    event Released(uint256 indexed id, uint256 index, uint256 amount, address by, bool early);
    event Refunded(uint256 indexed id, uint256 index, uint256 amount, address by);
    event Cancelled(uint256 indexed id, uint256 refunded);
    event Frozen(uint256 indexed id, bytes32 reason);
    event Unfrozen(uint256 indexed id);
    event Finished(uint256 indexed id, uint8 status);

    modifier nonReentrant() {
        require(!busy, "REENTRANT");
        busy = true;
        _;
        busy = false;
    }

    constructor(address compliance_) {
        require(compliance_ != address(0), "ZERO_COMPLIANCE");
        compliance = compliance_;
    }

    // ------------------------------------------------------------------ create

    /// @notice Lock the total of `amounts` from the caller, to be paid to `beneficiary`.
    function create(
        address token,
        address beneficiary,
        bytes32 ref,
        uint256[] calldata amounts,
        uint64[] calldata releaseAfter
    ) external nonReentrant returns (uint256 id) {
        uint256 n = amounts.length;
        require(n > 0 && n <= MAX_TRANCHES, "BAD_TRANCHE_COUNT");
        require(n == releaseAfter.length, "LENGTH_MISMATCH");
        require(token != address(0) && beneficiary != address(0), "ZERO_ADDRESS");
        require(beneficiary != msg.sender, "PAYER_IS_BENEFICIARY");

        id = ++escrowCount;
        Escrow storage e = escrows[id];
        e.payer = msg.sender;
        e.beneficiary = beneficiary;
        e.token = token;
        e.ref = ref;
        e.status = Status.Active;

        uint256 total;
        for (uint256 i = 0; i < n; i++) {
            require(amounts[i] > 0, "ZERO_AMOUNT");
            require(i == 0 || releaseAfter[i] >= releaseAfter[i - 1], "DATES_NOT_ORDERED");
            e.tranches.push(Tranche(amounts[i], releaseAfter[i], State.Locked));
            total += amounts[i];
        }
        e.lockedTotal = total;

        require(IDeposit(token).transferFrom(msg.sender, address(this), total), "FUNDING_FAILED");
        emit Created(id, msg.sender, beneficiary, token, ref, total, n);
    }

    // ----------------------------------------------------------------- release

    /// @notice Pay a tranche whose date has come. Either party may call it.
    function releaseDue(uint256 id, uint256 index) external nonReentrant {
        Escrow storage e = _active(id);
        require(msg.sender == e.payer || msg.sender == e.beneficiary, "NOT_A_PARTY");
        Tranche storage t = _locked(e, index);
        require(block.timestamp >= t.releaseAfter, "NOT_DUE");
        _release(id, e, t, index, false);
    }

    /// @notice The payer pays a tranche before its date. This is a human decision.
    function releaseEarly(uint256 id, uint256 index) external nonReentrant {
        Escrow storage e = _active(id);
        require(msg.sender == e.payer, "ONLY_PAYER");
        _release(id, e, _locked(e, index), index, true);
    }

    // ------------------------------------------------------------ take it back

    /// @notice The beneficiary sends one locked tranche back to the payer (a refused visa, say).
    function refund(uint256 id, uint256 index) external nonReentrant {
        Escrow storage e = _active(id);
        require(msg.sender == e.beneficiary, "ONLY_BENEFICIARY");
        _refund(id, e, _locked(e, index), index);
    }

    /// @notice The payer takes back every tranche that is not yet due. Due tranches stay.
    function cancel(uint256 id) external nonReentrant {
        Escrow storage e = _active(id);
        require(msg.sender == e.payer, "ONLY_PAYER");
        uint256 before = e.refundedTotal;
        for (uint256 i = 0; i < e.tranches.length; i++) {
            Tranche storage t = e.tranches[i];
            if (t.state == State.Locked && block.timestamp < t.releaseAfter) {
                _refund(id, e, t, i);
            }
        }
        require(e.refundedTotal > before, "NOTHING_TO_CANCEL");
        emit Cancelled(id, e.refundedTotal - before);
    }

    // -------------------------------------------------------------- compliance

    /// @notice The bank's compliance officer stops all movement. Funds stay locked.
    function freeze(uint256 id, bytes32 reason) external {
        require(msg.sender == compliance, "ONLY_COMPLIANCE");
        Escrow storage e = escrows[id];
        require(e.status == Status.Active, "NOT_ACTIVE");
        e.status = Status.Frozen;
        emit Frozen(id, reason);
    }

    function unfreeze(uint256 id) external {
        require(msg.sender == compliance, "ONLY_COMPLIANCE");
        Escrow storage e = escrows[id];
        require(e.status == Status.Frozen, "NOT_FROZEN");
        e.status = Status.Active;
        emit Unfrozen(id);
    }

    // -------------------------------------------------------------------- views

    function getEscrow(uint256 id)
        external
        view
        returns (
            address payer,
            address beneficiary,
            address token,
            bytes32 ref,
            uint8 status,
            uint256 lockedTotal,
            uint256 refundedTotal,
            uint256 trancheCount
        )
    {
        Escrow storage e = escrows[id];
        require(e.status != Status.None, "NO_SUCH_ESCROW");
        return (
            e.payer,
            e.beneficiary,
            e.token,
            e.ref,
            uint8(e.status),
            e.lockedTotal,
            e.refundedTotal,
            e.tranches.length
        );
    }

    function getTranche(uint256 id, uint256 index)
        external
        view
        returns (uint256 amount, uint64 releaseAfter, uint8 state)
    {
        Escrow storage e = escrows[id];
        require(e.status != Status.None, "NO_SUCH_ESCROW");
        require(index < e.tranches.length, "NO_SUCH_TRANCHE");
        Tranche storage t = e.tranches[index];
        return (t.amount, t.releaseAfter, uint8(t.state));
    }

    // ----------------------------------------------------------------- internal

    function _active(uint256 id) private view returns (Escrow storage e) {
        e = escrows[id];
        require(e.status != Status.None, "NO_SUCH_ESCROW");
        require(e.status == Status.Active, "NOT_ACTIVE");
    }

    function _locked(Escrow storage e, uint256 index) private view returns (Tranche storage t) {
        require(index < e.tranches.length, "NO_SUCH_TRANCHE");
        t = e.tranches[index];
        require(t.state == State.Locked, "NOT_LOCKED");
    }

    function _release(uint256 id, Escrow storage e, Tranche storage t, uint256 index, bool early) private {
        t.state = State.Released;
        e.lockedTotal -= t.amount;
        require(IDeposit(e.token).transfer(e.beneficiary, t.amount), "PAYOUT_FAILED");
        emit Released(id, index, t.amount, msg.sender, early);
        _finishIfDone(id, e);
    }

    function _refund(uint256 id, Escrow storage e, Tranche storage t, uint256 index) private {
        t.state = State.Refunded;
        e.lockedTotal -= t.amount;
        e.refundedTotal += t.amount;
        require(IDeposit(e.token).transfer(e.payer, t.amount), "REFUND_FAILED");
        emit Refunded(id, index, t.amount, msg.sender);
        _finishIfDone(id, e);
    }

    /// @dev When nothing is locked any more: Cancelled if anything went back, else Completed.
    function _finishIfDone(uint256 id, Escrow storage e) private {
        if (e.lockedTotal == 0) {
            e.status = e.refundedTotal > 0 ? Status.Cancelled : Status.Completed;
            emit Finished(id, uint8(e.status));
        }
    }
}
