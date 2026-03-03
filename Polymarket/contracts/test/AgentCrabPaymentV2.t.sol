// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {AgentCrabPayment} from "../src/AgentCrabPayment.sol";
import {AgentCrabPaymentV2} from "../src/AgentCrabPaymentV2.sol";
import {MockERC20} from "./mocks/MockERC20.sol";

contract AgentCrabPaymentV2Test is Test {
    AgentCrabPayment implV1;
    AgentCrabPaymentV2 implV2;
    ERC1967Proxy proxy;
    MockERC20 usdt;

    address owner = makeAddr("owner");
    address alice = makeAddr("alice");

    function setUp() public {
        // Deploy mock USDT (18 decimals like BSC)
        usdt = new MockERC20("USDT", "USDT", 18);

        // Deploy V1 via proxy (mimics production)
        implV1 = new AgentCrabPayment();
        bytes memory initData = abi.encodeCall(implV1.initialize, (address(usdt), owner));
        proxy = new ERC1967Proxy(address(implV1), initData);

        // Give alice some USDT
        usdt.mint(alice, 100 * 10 ** 18);
        vm.prank(alice);
        usdt.approve(address(proxy), type(uint256).max);

        // Alice deposits 1 USDT via V1
        vm.prank(alice);
        AgentCrabPayment(address(proxy)).deposit(1 * 10 ** 18);
    }

    function _upgradeToV2() internal {
        implV2 = new AgentCrabPaymentV2();
        vm.prank(owner);
        AgentCrabPayment(address(proxy)).upgradeToAndCall(address(implV2), "");
    }

    // --- Storage preservation after upgrade ---

    function test_upgradePreservesDeposits() public {
        uint256 balanceBefore = AgentCrabPayment(address(proxy)).getBalance(alice);
        _upgradeToV2();
        uint256 balanceAfter = AgentCrabPaymentV2(address(proxy)).getBalance(alice);
        assertEq(balanceBefore, balanceAfter, "deposits must survive upgrade");
    }

    function test_upgradePreservesTotalDeposited() public {
        uint256 before = AgentCrabPayment(address(proxy)).totalDeposited(alice);
        _upgradeToV2();
        uint256 after_ = AgentCrabPaymentV2(address(proxy)).totalDeposited(alice);
        assertEq(before, after_, "totalDeposited must survive upgrade");
    }

    function test_upgradePreservesUSDT() public {
        _upgradeToV2();
        assertEq(
            address(AgentCrabPaymentV2(address(proxy)).usdt()),
            address(usdt),
            "usdt address must survive upgrade"
        );
    }

    // --- V2 functionality works after upgrade ---

    function test_depositWorksAfterUpgrade() public {
        _upgradeToV2();
        vm.prank(alice);
        AgentCrabPaymentV2(address(proxy)).deposit(2 * 10 ** 18);
        assertEq(AgentCrabPaymentV2(address(proxy)).getBalance(alice), 3 * 10 ** 18);
    }

    function test_payWorksAfterUpgrade() public {
        _upgradeToV2();
        vm.prank(alice);
        AgentCrabPaymentV2(address(proxy)).pay();
        assertEq(AgentCrabPaymentV2(address(proxy)).getDirectPaymentCount(alice), 1);
    }

    function test_withdrawWorksAfterUpgrade() public {
        _upgradeToV2();
        uint256 ownerBefore = usdt.balanceOf(owner);
        vm.prank(owner);
        AgentCrabPaymentV2(address(proxy)).withdraw(1 * 10 ** 18);
        assertEq(usdt.balanceOf(owner), ownerBefore + 1 * 10 ** 18);
    }

    // --- renounceOwnership disabled ---

    function test_renounceOwnership_reverts() public {
        _upgradeToV2();
        vm.prank(owner);
        vm.expectRevert("renounce disabled");
        AgentCrabPaymentV2(address(proxy)).renounceOwnership();
    }

    // --- Upgrade authorization still works ---

    function test_onlyOwnerCanUpgrade() public {
        _upgradeToV2();
        AgentCrabPaymentV2 implV3 = new AgentCrabPaymentV2();
        vm.prank(alice); // not owner
        vm.expectRevert();
        AgentCrabPaymentV2(address(proxy)).upgradeToAndCall(address(implV3), "");
    }

    function test_ownerCanUpgradeAgain() public {
        _upgradeToV2();
        AgentCrabPaymentV2 implV3 = new AgentCrabPaymentV2();
        vm.prank(owner);
        AgentCrabPaymentV2(address(proxy)).upgradeToAndCall(address(implV3), "");
        // Still works
        assertEq(AgentCrabPaymentV2(address(proxy)).getBalance(alice), 1 * 10 ** 18);
    }

    // --- transferOwnership still works ---

    function test_transferOwnership() public {
        _upgradeToV2();
        address newOwner = makeAddr("newOwner");
        vm.prank(owner);
        AgentCrabPaymentV2(address(proxy)).transferOwnership(newOwner);
        // New owner can withdraw
        vm.prank(newOwner);
        AgentCrabPaymentV2(address(proxy)).withdraw(1 * 10 ** 18);
    }
}
