// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console} from "forge-std/Test.sol";
import {VitisRegistry} from "../contracts/VitisRegistry.sol";

contract VitisRegistryTest is Test {
    VitisRegistry public registry;
    
    address public deployer;
    address public oracle;
    address public user;
    
    address public assetContract = address(0x1234567890123456789012345678901234567890);
    uint256 public tokenId = 1;
    uint256 public score = 85;
    string public hederaTopicId = "0.0.8386842";

    event AssetCertified(
        address indexed assetContract,
        uint256 indexed tokenId,
        uint256 score,
        string hederaTopicId,
        uint256 timestamp
    );

    event OracleUpdated(address indexed oldOracle, address indexed newOracle);

    function setUp() public {
        deployer = address(this);
        oracle = deployer;
        user = address(0xDEAD);
        
        registry = new VitisRegistry();
    }

    function test_CertifyAsset_Success() public {
        vm.expectEmit(true, true, true, true);
        emit AssetCertified(assetContract, tokenId, score, hederaTopicId, block.timestamp);
        
        registry.certifyAsset(assetContract, tokenId, score, hederaTopicId);
        
        (uint256 storedScore, uint256 timestamp, string memory topicId) = registry.getCertification(assetContract, tokenId);
        
        assertEq(storedScore, score, "Score should match");
        assertEq(timestamp, block.timestamp, "Timestamp should be current");
        assertEq(keccak256(abi.encodePacked(topicId)), keccak256(abi.encodePacked(hederaTopicId)), "Topic ID should match");
        assertTrue(registry.checkCertification(assetContract, tokenId), "Should be certified");
    }

    function test_CertifyAsset_OnlyOracle() public {
        vm.prank(user);
        
        vm.expectRevert("Only VitisTrust Oracle can certify");
        registry.certifyAsset(assetContract, tokenId, score, hederaTopicId);
    }

    function test_CertifyAsset_InvalidScore() public {
        vm.expectRevert("Score must be between 0 and 100");
        registry.certifyAsset(assetContract, tokenId, 101, hederaTopicId);
    }

    function test_CertifyAsset_ZeroAssetContract() public {
        vm.expectRevert("Asset contract cannot be zero");
        registry.certifyAsset(address(0), tokenId, score, hederaTopicId);
    }

    function test_CertifyAsset_EmptyTopicId() public {
        vm.expectRevert("Hedera topic ID required");
        registry.certifyAsset(assetContract, tokenId, score, "");
    }

    function test_CertifyAsset_ScoreZero() public {
        registry.certifyAsset(assetContract, tokenId, 0, hederaTopicId);
        
        (uint256 storedScore,,) = registry.getCertification(assetContract, tokenId);
        assertEq(storedScore, 0, "Score should be 0");
    }

    function test_CertifyAsset_ScoreMax() public {
        registry.certifyAsset(assetContract, tokenId, 100, hederaTopicId);
        
        (uint256 storedScore,,) = registry.getCertification(assetContract, tokenId);
        assertEq(storedScore, 100, "Score should be 100");
    }

    function test_UpdateOracle_Success() public {
        address newOracle = address(0xBEEF);
        
        vm.expectEmit(true, true, true, true);
        emit OracleUpdated(oracle, newOracle);
        
        registry.updateOracle(newOracle);
        
        assertEq(registry.oracle(), newOracle, "Oracle should be updated");
    }

    function test_UpdateOracle_NotOracle() public {
        vm.prank(user);
        
        vm.expectRevert("Only VitisTrust Oracle can certify");
        registry.updateOracle(address(0xBEEF));
    }

    function test_UpdateOracle_ZeroAddress() public {
        vm.expectRevert("Oracle cannot be zero address");
        registry.updateOracle(address(0));
    }

    function test_GetCertificationIds() public {
        registry.certifyAsset(assetContract, 1, 85, hederaTopicId);
        registry.certifyAsset(assetContract, 2, 90, hederaTopicId);
        registry.certifyAsset(assetContract, 3, 75, hederaTopicId);
        
        uint256[] memory ids = registry.getCertificationIds(assetContract);
        
        assertEq(ids.length, 3, "Should have 3 certified tokens");
        assertEq(ids[0], 1, "First token ID should be 1");
        assertEq(ids[1], 2, "Second token ID should be 2");
        assertEq(ids[2], 3, "Third token ID should be 3");
    }

    function test_UpdateCertification() public {
        registry.certifyAsset(assetContract, tokenId, 85, hederaTopicId);
        
        registry.certifyAsset(assetContract, tokenId, 95, "0.0.9999999");
        
        uint256[] memory ids = registry.getCertificationIds(assetContract);
        
        assertEq(ids.length, 1, "Should still have 1 certified token (updated, not new)");
        
        (uint256 storedScore,,) = registry.getCertification(assetContract, tokenId);
        assertEq(storedScore, 95, "Score should be updated");
    }

    function test_CheckCertification_NotCertified() public view {
        bool certified = registry.checkCertification(assetContract, 999);
        
        assertFalse(certified, "Should not be certified");
    }

    function test_GetCertification_Unset() public view {
        (uint256 score_, uint256 timestamp, string memory topicId) = registry.getCertification(assetContract, 999);
        
        assertEq(score_, 0, "Score should be 0");
        assertEq(timestamp, 0, "Timestamp should be 0");
        assertEq(bytes(topicId).length, 0, "Topic ID should be empty");
    }
}
