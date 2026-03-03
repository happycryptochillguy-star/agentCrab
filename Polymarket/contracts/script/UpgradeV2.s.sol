// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {AgentCrabPaymentV2} from "../src/AgentCrabPaymentV2.sol";
import {UUPSUpgradeable} from "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";

contract UpgradeV2Script is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address proxy = vm.envAddress("CONTRACT_ADDRESS");

        console.log("Proxy:", proxy);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy new implementation
        AgentCrabPaymentV2 implV2 = new AgentCrabPaymentV2();
        console.log("V2 Implementation:", address(implV2));

        // 2. Upgrade proxy to V2 (no reinitializer call needed)
        UUPSUpgradeable(proxy).upgradeToAndCall(address(implV2), "");
        console.log("Upgrade complete");

        vm.stopBroadcast();
    }
}
