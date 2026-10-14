// SPDX-License-Identifier: MIT
pragma solidity >=0.8.11 <0.9.0;

/// @title TokenisedDeposit
/// @notice Sandbox stand-in for a bank-issued tokenised deposit (an ERC-20 subset), one per
///         currency. One unit is one minor unit of the currency (1 = 0.01 GBP for GBP).
///         Only the issuing bank mints. Holders redeem by burning; the bank pays out OFF chain.
/// @dev    Nothing here is money. It runs on a simulated chain inside the StudyRoute sandbox.
contract TokenisedDeposit {
    string public name;
    string public symbol;
    uint8 public immutable decimals;
    address public immutable issuer;
    uint256 public totalSupply;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory name_, string memory symbol_, uint8 decimals_, address issuer_) {
        require(issuer_ != address(0), "ZERO_ISSUER");
        name = name_;
        symbol = symbol_;
        decimals = decimals_;
        issuer = issuer_;
    }

    /// @notice The issuing bank creates tokens against a deposit it has taken off chain.
    function mint(address to, uint256 amount) external {
        require(msg.sender == issuer, "ONLY_ISSUER");
        require(to != address(0), "ZERO_ADDRESS");
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    /// @notice A holder gives tokens back to the bank, which pays out off chain.
    function redeem(uint256 amount) external {
        require(balanceOf[msg.sender] >= amount, "INSUFFICIENT_BALANCE");
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;
        emit Transfer(msg.sender, address(0), amount);
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 allowed = allowance[from][msg.sender];
        require(allowed >= value, "INSUFFICIENT_ALLOWANCE");
        allowance[from][msg.sender] = allowed - value;
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) private {
        require(to != address(0), "ZERO_ADDRESS");
        require(balanceOf[from] >= value, "INSUFFICIENT_BALANCE");
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
    }
}
