// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {AgentCrabPayment} from "../src/AgentCrabPayment.sol";

contract DeployScript is Script {
    // BSC USDT (18 decimals)
    address constant BSC_USDT = 0x55d398326f99059fF775485246999027B3197955;

    function run() external {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console.log("Deployer:", deployer);

        vm.startBroadcast(deployerPrivateKey);

        // Deploy implementation
        AgentCrabPayment impl = new AgentCrabPayment();
        console.log("Implementation:", address(impl));

        // Deploy proxy with initialize call
        bytes memory initData = abi.encodeCall(impl.initialize, (BSC_USDT, deployer));
        ERC1967Proxy proxy = new ERC1967Proxy(address(impl), initData);
        console.log("Proxy (use this address):", address(proxy));

        vm.stopBroadcast();
    }
}
