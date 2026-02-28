// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {UUPSUpgradeable} from "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {OwnableUpgradeable} from "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract AgentWayPayment is Initializable, UUPSUpgradeable, OwnableUpgradeable {
    using SafeERC20 for IERC20;

    IERC20 public usdt;
    uint256 public constant PAYMENT_AMOUNT = 10 ** 16; // 0.01 USDT (18 decimals)

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

    function initialize(address _usdt, address _owner) external initializer {
        __Ownable_init(_owner);
        __UUPSUpgradeable_init();
        usdt = IERC20(_usdt);
    }

    /// @notice Mode B: Deposit USDT for prepaid usage
    function deposit(uint256 amount) external {
        require(amount > 0, "Amount must be > 0");
        usdt.safeTransferFrom(msg.sender, address(this), amount);
        deposits[msg.sender] += amount;
        totalDeposited[msg.sender] += amount;
        emit Deposited(msg.sender, amount);
    }

    /// @notice Mode A: Pay exactly 0.01 USDT per API call
    function pay() external {
        usdt.safeTransferFrom(msg.sender, address(this), PAYMENT_AMOUNT);
        directPayments[msg.sender] += PAYMENT_AMOUNT;
        directPaymentCount[msg.sender] += 1;
        emit DirectPayment(msg.sender, PAYMENT_AMOUNT);
    }

    /// @notice Owner withdraws collected USDT
    function withdraw(uint256 amount) external onlyOwner {
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

    function _authorizeUpgrade(address newImplementation) internal override onlyOwner {}
}
