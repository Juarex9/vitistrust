// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title VitisRegistry - Oracle de certificación de viñedos NFT
/// @notice Certifica la salud de un viñedo en Rootstock y notariza en Hedera
contract VitisRegistry {

    // ============================================================
    // Events
    // ============================================================

    /// @notice Emitted when an asset is certified
    event AssetCertified(
        address indexed assetContract,
        uint256 indexed tokenId,
        uint256 score,
        string topicId,
        uint256 timestamp
    );

    /// @notice Emitted when the oracle address is updated
    event OracleUpdated(address indexed oldOracle, address indexed newOracle);

    /// @notice Emitted when a low VitisScore triggers a NFT metadata update simulation
    event DynamicMetadataTriggered(
        address indexed assetContract,
        uint256 indexed tokenId,
        string reason
    );

    // ============================================================
    // State Variables
    // ============================================================

    uint256 public constant MAX_SCORE = 100;

    address public oracle;

    struct Certification {
        uint256 score;
        uint256 timestamp;
        string topicId;
    }

    mapping(address => mapping(uint256 => Certification)) public certificates;
    mapping(address => uint256[]) public certificationIds;
    mapping(address => mapping(uint256 => bool)) public isCertified;

    // ============================================================
    // Modifiers
    // ============================================================

    modifier onlyOracle() {
        require(msg.sender == oracle, "Only VitisTrust Oracle can certify");
        _;
    }

    // ============================================================
    // Constructor
    // ============================================================

    constructor() {
        oracle = msg.sender;
    }

    // ============================================================
    // Admin Functions
    // ============================================================

    /// @notice Update the oracle address
    function updateOracle(address newOracle) external onlyOracle {
        require(newOracle != address(0), "Oracle cannot be zero address");
        address oldOracle = oracle;
        oracle = newOracle;
        emit OracleUpdated(oldOracle, newOracle);
    }

    // ============================================================
    // Certification Functions
    // ============================================================

    /// @notice Certifica múltiples activos en una sola transacción (gas-efficient)
    function certifyBatch(
        address[] calldata assetContracts,
        uint256[] calldata tokenIds,
        uint256[] calldata scores,
        string[] calldata topicIds
    ) external onlyOracle {
        require(
            assetContracts.length == tokenIds.length &&
            tokenIds.length == scores.length &&
            scores.length == topicIds.length,
            "Array lengths mismatch"
        );
        for (uint256 i = 0; i < assetContracts.length; i++) {
            _certify(assetContracts[i], tokenIds[i], scores[i], topicIds[i]);
        }
    }

    /// @notice Certify a single vineyard asset with a VitisScore
    function certifyAsset(
        address assetContract,
        uint256 tokenId,
        uint256 score,
        string memory topicId
    ) public onlyOracle {
        _certify(assetContract, tokenId, score, topicId);
    }

    /// @dev Internal certification logic shared by certifyAsset and certifyBatch
    function _certify(
        address assetContract,
        uint256 tokenId,
        uint256 score,
        string memory topicId
    ) internal {
        require(assetContract != address(0), "Asset contract cannot be zero");
        require(score <= MAX_SCORE, "Score must be between 0 and 100");
        require(bytes(topicId).length > 0, "Hedera topic ID required");

        certificates[assetContract][tokenId] = Certification({
            score: score,
            timestamp: block.timestamp,
            topicId: topicId
        });

        if (!isCertified[assetContract][tokenId]) {
            isCertified[assetContract][tokenId] = true;
            certificationIds[assetContract].push(tokenId);
        }

        emit AssetCertified(assetContract, tokenId, score, topicId, block.timestamp);

        // Simulate dynamic NFT metadata update for RWA demonstration
        if (score < 50) {
            emit DynamicMetadataTriggered(assetContract, tokenId, "Low VitisScore - Health Alert");
        }
    }

    // ============================================================
    // View Functions
    // ============================================================

    /// @notice Get certification details for a specific asset
    function getCertification(
        address assetContract,
        uint256 tokenId
    ) external view returns (uint256 score, uint256 timestamp, string memory topicId) {
        Certification memory cert = certificates[assetContract][tokenId];
        return (cert.score, cert.timestamp, cert.topicId);
    }

    /// @notice Get all certified token IDs for an asset contract
    function getCertificationIds(address assetContract) external view returns (uint256[] memory) {
        return certificationIds[assetContract];
    }

    /// @notice Check if a specific token is certified
    function checkCertification(address assetContract, uint256 tokenId) external view returns (bool) {
        return isCertified[assetContract][tokenId];
    }
}
