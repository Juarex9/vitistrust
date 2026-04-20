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

    /// @notice Emitted when an oracle profile is updated
    event OracleProfileUpdated(
        address indexed oracleAddress,
        uint256 reputation,
        uint256 disputesWon,
        uint256 disputesLost
    );

    /// @notice Emitted when a dispute is opened
    event DisputeOpened(
        bytes32 indexed recordId,
        address indexed challenger,
        uint256 bond,
        uint256 scoringModelVersion,
        uint256 timestamp
    );

    /// @notice Emitted when a dispute is resolved
    event DisputeResolved(
        bytes32 indexed recordId,
        bool verdict,
        address indexed resolver,
        uint256 releasedBond,
        uint256 timestamp
    );

    /// @notice Emitted when arbitrator is updated
    event ArbitratorUpdated(address indexed oldArbitrator, address indexed newArbitrator);

    /// @notice Emitted when committee mode toggles
    event CommitteeModeUpdated(bool enabled);

    /// @notice Emitted when a committee member is updated
    event CommitteeArbitratorUpdated(address indexed member, bool allowed);

    /// @notice Emitted when scoring model version is updated
    event ScoringModelVersionUpdated(uint256 oldVersion, uint256 newVersion);

    // ============================================================
    // State Variables
    // ============================================================

    uint256 public constant MAX_SCORE = 100;
    uint256 public constant DEFAULT_REPUTATION = 100;
    uint256 public minDisputeBond = 0.01 ether;

    address public oracle;
    address public arbitrator;
    bool public committeeMode;
    uint256 public currentScoringModelVersion = 1;

    struct Certification {
        uint256 score;
        uint256 timestamp;
        string topicId;
        uint256 scoringModelVersion;
    }

    struct OracleProfile {
        uint256 reputation;
        uint256 disputesWon;
        uint256 disputesLost;
    }

    struct Dispute {
        address challenger;
        uint256 bond;
        uint256 openedAt;
        uint256 scoringModelVersion;
        bool resolved;
        bool exists;
    }

    mapping(address => mapping(uint256 => Certification)) public certificates;
    mapping(address => uint256[]) public certificationIds;
    mapping(address => mapping(uint256 => bool)) public isCertified;
    mapping(address => OracleProfile) public oracleProfiles;
    mapping(bytes32 => Dispute) public disputes;
    mapping(address => bool) public committeeArbitrators;

    // ============================================================
    // Modifiers
    // ============================================================

    modifier onlyOracle() {
        require(msg.sender == oracle, "Only VitisTrust Oracle can certify");
        _;
    }

    modifier onlyArbitrator() {
        if (committeeMode) {
            require(committeeArbitrators[msg.sender], "Only committee arbitrator");
        } else {
            require(msg.sender == arbitrator, "Only arbitrator");
        }
        _;
    }

    // ============================================================
    // Constructor
    // ============================================================

    constructor() {
        oracle = msg.sender;
        arbitrator = msg.sender;
        oracleProfiles[msg.sender] = OracleProfile({
            reputation: DEFAULT_REPUTATION,
            disputesWon: 0,
            disputesLost: 0
        });
    }

    // ============================================================
    // Admin Functions
    // ============================================================

    /// @notice Update the oracle address
    function updateOracle(address newOracle) external onlyOracle {
        require(newOracle != address(0), "Oracle cannot be zero address");
        address oldOracle = oracle;
        oracle = newOracle;
        if (oracleProfiles[newOracle].reputation == 0) {
            oracleProfiles[newOracle] = OracleProfile({
                reputation: DEFAULT_REPUTATION,
                disputesWon: 0,
                disputesLost: 0
            });
            emit OracleProfileUpdated(newOracle, DEFAULT_REPUTATION, 0, 0);
        }
        emit OracleUpdated(oldOracle, newOracle);
    }

    /// @notice Update the centralized arbitrator (e.g. INV/admin multisig)
    function updateArbitrator(address newArbitrator) external onlyArbitrator {
        require(newArbitrator != address(0), "Arbitrator cannot be zero");
        address oldArbitrator = arbitrator;
        arbitrator = newArbitrator;
        emit ArbitratorUpdated(oldArbitrator, newArbitrator);
    }

    /// @notice Enable/disable committee mode for dispute resolution
    function setCommitteeMode(bool enabled) external onlyArbitrator {
        committeeMode = enabled;
        emit CommitteeModeUpdated(enabled);
    }

    /// @notice Manage committee arbitrators to support migration from centralized arbitration
    function setCommitteeArbitrator(address member, bool allowed) external onlyArbitrator {
        require(member != address(0), "Committee member cannot be zero");
        committeeArbitrators[member] = allowed;
        emit CommitteeArbitratorUpdated(member, allowed);
    }

    /// @notice Update the minimum bond required to open disputes
    function setMinDisputeBond(uint256 newMinBond) external onlyArbitrator {
        minDisputeBond = newMinBond;
    }

    /// @notice Bump scoring model version to evaluate new certifications/disputes against current methodology
    function setScoringModelVersion(uint256 newVersion) external onlyArbitrator {
        require(newVersion > currentScoringModelVersion, "Version must increase");
        uint256 oldVersion = currentScoringModelVersion;
        currentScoringModelVersion = newVersion;
        emit ScoringModelVersionUpdated(oldVersion, newVersion);
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
            topicId: topicId,
            scoringModelVersion: currentScoringModelVersion
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
    ) external view returns (uint256 score, uint256 timestamp, string memory topicId, uint256 scoringModelVersion) {
        Certification memory cert = certificates[assetContract][tokenId];
        return (cert.score, cert.timestamp, cert.topicId, cert.scoringModelVersion);
    }

    /// @notice Get all certified token IDs for an asset contract
    function getCertificationIds(address assetContract) external view returns (uint256[] memory) {
        return certificationIds[assetContract];
    }

    /// @notice Check if a specific token is certified
    function checkCertification(address assetContract, uint256 tokenId) external view returns (bool) {
        return isCertified[assetContract][tokenId];
    }

    /// @notice Open a dispute for a specific certification record using a spam-deterring bond
    /// @dev recordId should be computed as keccak256(abi.encodePacked(assetContract, tokenId))
    function openDispute(bytes32 recordId, uint256 bond) external payable {
        require(recordId != bytes32(0), "Record ID required");
        require(!disputes[recordId].exists || disputes[recordId].resolved, "Dispute already open");
        require(msg.value == bond, "Bond mismatch");
        require(bond >= minDisputeBond, "Bond too low");

        disputes[recordId] = Dispute({
            challenger: msg.sender,
            bond: bond,
            openedAt: block.timestamp,
            scoringModelVersion: currentScoringModelVersion,
            resolved: false,
            exists: true
        });

        emit DisputeOpened(recordId, msg.sender, bond, currentScoringModelVersion, block.timestamp);
    }

    /// @notice Resolve a dispute. verdict=true means dispute is upheld against oracle result.
    function resolveDispute(bytes32 recordId, bool verdict) external onlyArbitrator {
        Dispute storage dispute = disputes[recordId];
        require(dispute.exists, "Dispute not found");
        require(!dispute.resolved, "Dispute already resolved");

        dispute.resolved = true;
        address payable challenger = payable(dispute.challenger);
        uint256 bond = dispute.bond;

        OracleProfile storage profile = oracleProfiles[oracle];
        if (profile.reputation == 0) {
            profile.reputation = DEFAULT_REPUTATION;
        }

        if (verdict) {
            profile.disputesLost += 1;
            if (profile.reputation >= 5) {
                profile.reputation -= 5;
            } else {
                profile.reputation = 0;
            }
            challenger.transfer(bond);
        } else {
            profile.disputesWon += 1;
            profile.reputation += 1;
        }

        emit OracleProfileUpdated(oracle, profile.reputation, profile.disputesWon, profile.disputesLost);
        emit DisputeResolved(recordId, verdict, msg.sender, bond, block.timestamp);
    }
}
