// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {AgentWayPayment} from "../src/AgentWayPayment.sol";
import {MockERC20} from "./mocks/MockERC20.sol";

contract AgentWayPaymentTest is Test {
    AgentWayPayment public payment;
    MockERC20 public usdt;

    address public owner = address(0x1);
    address public user1 = address(0x2);
    address public user2 = address(0x3);

    uint256 public constant PAYMENT_AMOUNT = 10 ** 16;

    function setUp() public {
        usdt = new MockERC20("Tether USD", "USDT", 18);

        AgentWayPayment impl = new AgentWayPayment();
        bytes memory initData = abi.encodeCall(impl.initialize, (address(usdt), owner));
        ERC1967Proxy proxy = new ERC1967Proxy(address(impl), initData);
        payment = AgentWayPayment(address(proxy));

        // Fund users
        usdt.mint(user1, 100 ether);
        usdt.mint(user2, 100 ether);
    }

    // === Initialization ===

    function test_initialization() public view {
        assertEq(address(payment.usdt()), address(usdt));
        assertEq(payment.owner(), owner);
        assertEq(payment.PAYMENT_AMOUNT(), PAYMENT_AMOUNT);
    }

    function test_cannotReinitialize() public {
        vm.expectRevert();
        payment.initialize(address(usdt), owner);
    }

    // === Deposit (Mode B) ===

    function test_deposit() public {
        uint256 amount = 1 ether;
        vm.startPrank(user1);
        usdt.approve(address(payment), amount);
        payment.deposit(amount);
        vm.stopPrank();

        assertEq(payment.deposits(user1), amount);
        assertEq(payment.totalDeposited(user1), amount);
        assertEq(payment.getBalance(user1), amount);
    }

    function test_depositMultiple() public {
        vm.startPrank(user1);
        usdt.approve(address(payment), 3 ether);
        payment.deposit(1 ether);
        payment.deposit(2 ether);
        vm.stopPrank();

        assertEq(payment.deposits(user1), 3 ether);
        assertEq(payment.totalDeposited(user1), 3 ether);
    }

    function test_depositEmitsEvent() public {
        uint256 amount = 1 ether;
        vm.startPrank(user1);
        usdt.approve(address(payment), amount);

        vm.expectEmit(true, false, false, true);
        emit AgentWayPayment.Deposited(user1, amount);
        payment.deposit(amount);
        vm.stopPrank();
    }

    function test_depositZeroReverts() public {
        vm.prank(user1);
        vm.expectRevert("Amount must be > 0");
        payment.deposit(0);
    }

    // === Pay (Mode A) ===

    function test_pay() public {
        vm.startPrank(user1);
        usdt.approve(address(payment), PAYMENT_AMOUNT);
        payment.pay();
        vm.stopPrank();

        assertEq(payment.directPayments(user1), PAYMENT_AMOUNT);
        assertEq(payment.directPaymentCount(user1), 1);
        assertEq(payment.getDirectPaymentCount(user1), 1);
    }

    function test_payMultiple() public {
        vm.startPrank(user1);
        usdt.approve(address(payment), PAYMENT_AMOUNT * 3);
        payment.pay();
        payment.pay();
        payment.pay();
        vm.stopPrank();

        assertEq(payment.directPaymentCount(user1), 3);
        assertEq(payment.directPayments(user1), PAYMENT_AMOUNT * 3);
    }

    function test_payEmitsEvent() public {
        vm.startPrank(user1);
        usdt.approve(address(payment), PAYMENT_AMOUNT);

        vm.expectEmit(true, false, false, true);
        emit AgentWayPayment.DirectPayment(user1, PAYMENT_AMOUNT);
        payment.pay();
        vm.stopPrank();
    }

    function test_payNoApprovalReverts() public {
        vm.prank(user1);
        vm.expectRevert();
        payment.pay();
    }

    // === Withdraw ===

    function test_withdraw() public {
        // User deposits first
        vm.startPrank(user1);
        usdt.approve(address(payment), 1 ether);
        payment.deposit(1 ether);
        vm.stopPrank();

        uint256 ownerBalBefore = usdt.balanceOf(owner);

        vm.prank(owner);
        payment.withdraw(1 ether);

        assertEq(usdt.balanceOf(owner), ownerBalBefore + 1 ether);
    }

    function test_withdrawOnlyOwner() public {
        vm.startPrank(user1);
        usdt.approve(address(payment), 1 ether);
        payment.deposit(1 ether);
        vm.stopPrank();

        vm.prank(user1);
        vm.expectRevert();
        payment.withdraw(1 ether);
    }

    function test_withdrawZeroReverts() public {
        vm.prank(owner);
        vm.expectRevert("Amount must be > 0");
        payment.withdraw(0);
    }

    function test_withdrawOverBalanceReverts() public {
        vm.prank(owner);
        vm.expectRevert("Insufficient contract balance");
        payment.withdraw(1 ether);
    }

    function test_withdrawEmitsEvent() public {
        vm.startPrank(user1);
        usdt.approve(address(payment), 1 ether);
        payment.deposit(1 ether);
        vm.stopPrank();

        vm.prank(owner);
        vm.expectEmit(true, false, false, true);
        emit AgentWayPayment.Withdrawn(owner, 1 ether);
        payment.withdraw(1 ether);
    }

    // === View Functions ===

    function test_getBalanceDefault() public view {
        assertEq(payment.getBalance(user1), 0);
    }

    function test_getDirectPaymentCountDefault() public view {
        assertEq(payment.getDirectPaymentCount(user1), 0);
    }
}
