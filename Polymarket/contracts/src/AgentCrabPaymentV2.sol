// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.24;

import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {UUPSUpgradeable} from "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {OwnableUpgradeable} from "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import {ReentrancyGuardUpgradeable} from "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title AgentCrabPayment V2
/// @notice V2 upgrade: disables renounceOwnership() to prevent accidental contract bricking.
/// @dev Storage layout MUST match V1 exactly (slots 0-4 unchanged).
contract AgentCrabPaymentV2 is Initializable, UUPSUpgradeable, OwnableUpgradeable, ReentrancyGuardUpgradeable {
    using SafeERC20 for IERC20;

    // === Slot 0 ===
    IERC20 public usdt;
    uint256 public constant PAYMENT_AMOUNT = 10 ** 16; // 0.01 USDT (18 decimals)

    // === Slots 1-4 (mappings, must match V1 exactly) ===
    mapping(address => uint256) public deposits;
    mapping(address => uint256) public totalDeposited;
    mapping(address => uint256) public directPayments;
    mapping(address => uint256) public directPaymentCount;

    event Deposited(address indexed user, uint256 amount);
    event DirectPayment(address indexed user, uint256 amount);
    event Withdrawn(address indexed owner, uint256 amount);

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    // No reinitializer needed — V2 adds no new state that requires initialization.

    /// @notice Mode B: Deposit USDT for prepaid usage
    function deposit(uint256 amount) external nonReentrant {
        require(amount > 0, "Amount must be > 0");
        usdt.safeTransferFrom(msg.sender, address(this), amount);
        deposits[msg.sender] += amount;
        totalDeposited[msg.sender] += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Mode A: Pay exactly 0.01 USDT per API call
    function pay() external nonReentrant {
        usdt.safeTransferFrom(msg.sender, address(this), PAYMENT_AMOUNT);
        directPayments[msg.sender] += PAYMENT_AMOUNT;
        directPaymentCount[msg.sender] += 1;
        emit DirectPayment(msg.sender, PAYMENT_AMOUNT);
    }

    /// @notice Owner withdraws collected USDT
    function withdraw(uint256 amount) external onlyOwner nonReentrant {
        require(amount > 0, "Amount must be > 0");
        uint256 balance = usdt.balanceOf(address(this));
        require(amount <= balance, "Insufficient contract balance");
        usdt.safeTransfer(msg.sender, amount);
        emit Withdrawn(msg.sender, amount);
    }

    function getBalance(address user) external view returns (uint256) {
        return deposits[user];
    }

    function getDirectPaymentCount(address user) external view returns (uint256) {
        return directPaymentCount[user];
    }

    /// @notice Disabled — renouncing ownership would permanently brick the contract
    /// (no upgrades, no withdrawals). This is irreversible and must never happen.
    function renounceOwnership() public pure override {
        revert("renounce disabled");
    }

    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}
