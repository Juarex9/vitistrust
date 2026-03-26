// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract VitisRegistry {
    /// @notice Emitted when an asset is certified
    /// @param assetContract The external NFT contract address
    /// @param tokenId The token ID
    /// @param score The VitisScore (0-100)
    /// @param hederaTopicId The Hedera topic ID for audit trail
    event AssetCertified(
        address indexed assetContract,
        uint256 indexed tokenId,
        uint256 score,
        string hederaTopicId,
        uint256 timestamp
    );

    /// @notice Emitted when the oracle address is updated
    /// @param oldOracle The previous oracle address
    /// @param newOracle The new oracle address
    event OracleUpdated(address indexed oldOracle, address indexed newOracle);

    /// @notice Maximum allowed VitisScore
    uint256 public constant MAX_SCORE = 100;

    /// @notice The oracle address that can certify assets
    address public oracle;

    /// @notice Certification structure
    struct Certification {
        uint256 score;
        uint256 timestamp;
        string hederaTopicId;
    }

    /// @notice Mapping of (asset contract address => token ID => Certification)
    mapping(address => mapping(uint256 => Certification)) public certificates;

    /// @notice Mapping of (asset contract => token IDs certified)
    mapping(address => uint256[]) public certificationIds;

    /// @notice Check if a specific token is certified
    mapping(address => mapping(uint256 => bool)) public isCertified;

    /// @dev Modifier to ensure only the oracle can call certain functions
    modifier onlyOracle() {
        require(msg.sender == oracle, "Only VitisTrust Oracle can certify");
        _;
    }

    /// @notice Initialize the contract with the deployer as oracle
    constructor() {
        oracle = msg.sender;
    }

    /// @notice Update the oracle address
    /// @param newOracle The new oracle address
    function updateOracle(address newOracle) external onlyOracle {
        require(newOracle != address(0), "Oracle cannot be zero address");
        address oldOracle = oracle;
        oracle = newOracle;
        emit OracleUpdated(oldOracle, newOracle);
    }

    /// @notice Certify a vineyard asset with VitisScore
    /// @param assetContract The external NFT contract address
    /// @param tokenId The token ID
    /// @param score The VitisScore (0-100)
    /// @param hederaTopicId The Hedera topic ID for audit trail
    function certifyAsset(
        address assetContract,
        uint256 tokenId,
        uint256 score,
        string memory hederaTopicId
    ) external onlyOracle {
        require(assetContract != address(0), "Asset contract cannot be zero");
        require(score <= MAX_SCORE, "Score must be between 0 and 100");
        require(bytes(hederaTopicId).length > 0, "Hedera topic ID required");

        Certification memory cert = Certification({
            score: score,
            timestamp: block.timestamp,
            hederaTopicId: hederaTopicId
        });

        certificates[assetContract][tokenId] = cert;

        if (!isCertified[assetContract][tokenId]) {
            isCertified[assetContract][tokenId] = true;
            certificationIds[assetContract].push(tokenId);
        }

        emit AssetCertified(assetContract, tokenId, score, hederaTopicId, block.timestamp);
    }

    /// @notice Get certification details for a specific asset
    /// @param assetContract The external NFT contract address
    /// @param tokenId The token ID
    /// @return score The VitisScore
    /// @return timestamp The certification timestamp
    /// @return hederaTopicId The Hedera topic ID
    function getCertification(
        address assetContract,
        uint256 tokenId
    ) external view returns (uint256 score, uint256 timestamp, string memory hederaTopicId) {
        Certification memory cert = certificates[assetContract][tokenId];
        return (cert.score, cert.timestamp, cert.hederaTopicId);
    }

    /// @notice Get all certified token IDs for an asset contract
    /// @param assetContract The external NFT contract address
    /// @return Array of token IDs
    function getCertificationIds(address assetContract) external view returns (uint256[] memory) {
        return certificationIds[assetContract];
    }

    /// @notice Check if a specific token is certified
    /// @param assetContract The external NFT contract address
    /// @param tokenId The token ID
    /// @return Boolean indicating if certified
    function checkCertification(address assetContract, uint256 tokenId) external view returns (bool) {
        return isCertified[assetContract][tokenId];
    }
}
