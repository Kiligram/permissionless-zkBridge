pragma solidity 0.8.29;
pragma experimental ABIEncoderV2;

import "../../lib/openzeppelin-contracts/contracts/utils/ReentrancyGuard.sol";
// import "openzeppelin-contracts/contracts/access/Ownable.sol";
import "./libraries/HeaderBLSVerifier.sol";
import "./libraries/SyncCommitteeRootToPoseidonVerifier.sol";
import "./libraries/SimpleSerialize.sol";
import {ILightClientGetter, ILightClientSetter} from "../interfaces/ILightClient.sol";

uint256 constant OPTIMISTIC_UPDATE_TIMEOUT = 86400;
uint256 constant SLOTS_PER_EPOCH = 32;
uint256 constant SLOTS_PER_SYNC_COMMITTEE_PERIOD = 8192;
uint256 constant MIN_SYNC_COMMITTEE_PARTICIPANTS = 10;
uint256 constant SYNC_COMMITTEE_SIZE = 512;
uint256 constant FINALIZED_ROOT_INDEX = 105;
uint256 constant NEXT_SYNC_COMMITTEE_INDEX = 55;
uint256 constant EXECUTION_STATE_ROOT_INDEX = 402;
uint256 constant BLOCK_NUMBER_ROOT_INDEX = 406;


/// @title An on-chain light client for Ethereum
/// @author iwan.eth (initial author) | Andrii Rybak (incentive mechanism, formal verification, security update and CLI)
/// @notice An on-chain light client that complies with the Ethereum light client protocol witch 
///         is defined in `https://github.com/ethereum/consensus-specs`, it can be ethereum main 
///         net or goerli/sepolia test net.
///         With this light client you can verify any block headers from ethereum(main/test net).
/// @dev Different from normal light clients, on-chain light clients require a lower running 
///      costs because of the gas, but there is a lot of complex computational logic in ethereum 
///      consensus specs that cannot even be run in smart contracts. However, we can use zkSnarks 
///      technology to calculate complex logic and then verify it in smart contracts.
contract EthereumLightClient is ILightClientGetter, ILightClientSetter, ReentrancyGuard  {
    bytes32 public immutable GENESIS_VALIDATORS_ROOT;
    uint256 public immutable GENESIS_TIME;
    uint256 public immutable SECONDS_PER_SLOT;

    // -------------- MY CHANGES ----------------
    address public currentProposer;
    uint256 public currentProposerExpiration;

    // incentive settings
    uint256 public constant COLLATERAL = 2 ether;
    uint256 public constant BRIDGE_BLOCK_PROPOSAL_TIMESLOT = 2 minutes;
    uint256 public constant BRIDGE_TIMESLOT_PENALTY = 0.2 ether; // 0.2 ether = 10% penalty
    uint256 public constant EXECUTION_STATE_ROOT_PRICE = 0.01 ether;
    uint256 public constant SYNC_COMMITTEE_ROOT_PRICE = 0.01 ether;

    // mapping(address => bool) public whitelistMapping;
    mapping(address => uint256) public relayerToBalance;
    mapping(uint64 => address) public slotToSubmitter;
    mapping(uint256 => address) public periodToSubmitter;
    mapping(bytes32 => address) internal _syncCommitteeRootToSubmitter;
    mapping(address => uint256) public relayerToIncentive;
    
    address[] public whitelistArray;

    function joinRelayerNetwork() external payable {
        require(msg.value == COLLATERAL, "Incorrect collateral amount");
        require(relayerToBalance[msg.sender] == 0, "Address already whitelisted");
        relayerToBalance[msg.sender] = msg.value;
        whitelistArray.push(msg.sender);

        // if there is only one relayer, set it as the current proposer
        if (whitelistArray.length == 1) {
            currentProposer = msg.sender;
            currentProposerExpiration = block.timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT;
        }
    }

    function _removeRelayerFromWhitelist(address _address) internal {
        require(relayerToBalance[_address] > 0, "Address is not whitelisted");
        // Efficiently remove the address from the whitelistArray
        for (uint256 i = 0; i < whitelistArray.length; i++) {
            if (whitelistArray[i] == _address) {
                whitelistArray[i] = whitelistArray[whitelistArray.length - 1]; // Replace with the last element
                whitelistArray.pop(); // Remove the last element
                break;
            }
        }      
    }

    function exitRelayerNetwork() external nonReentrant {
        // if the relayer is the current proposer, it cannot exit
        // however, if the relayer is the only one in the network, it can exit
        require(msg.sender != currentProposer || whitelistArray.length == 1, "Cannot exit while being a proposer");

        _removeRelayerFromWhitelist(msg.sender);

        // if there are no more relayers in the network, set the current proposer to 0
        if(whitelistArray.length == 0) {
            currentProposer = address(0);
        }      

        // send back what is left from collateral
        payable(msg.sender).transfer(relayerToBalance[msg.sender]);
        relayerToBalance[msg.sender] = 0;
    }   

    function _getRandomSeed() internal view returns (uint256) {
        // Combine multiple sources of pseudo-randomness
        return uint256(
                keccak256(
                    abi.encodePacked(
                        blockhash(block.number - 1),    // Previous block hash
                        headSlot,                       // Latest finalized slot
                        address(this).balance,          // Contract balance is changed often
                        currentProposer
                    )
                )
            );
    }
        
    function _chooseRandomProposer() internal {
        if (whitelistArray.length == 0) {
            currentProposer = address(0);
            return;
        }

        // Use the random seed to select an index in the array
        currentProposer = whitelistArray[_getRandomSeed() % whitelistArray.length];
        currentProposerExpiration = block.timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT;
    }

    // proposer has a time slot to propose a block header, if it doesn't do it, anyone else from the whitelist can propose it
    // as a result the proposer who missed their slot will be penalized and the relayer who proposed the block header will get that penalty as incentive
    modifier onlyProposer() {
        require(msg.sender == currentProposer || currentProposerExpiration < block.timestamp, "Only proposer can call this function");
        require(relayerToBalance[msg.sender] > 0, "Address is not whitelisted");
        
        _;

        // if the proposer misses its time slot, it will be penalized
        // and anyone from relayers who proposes a block header will get the penalty from original proposer as incentive
        if(msg.sender != currentProposer){
            if (relayerToBalance[currentProposer] <= BRIDGE_TIMESLOT_PENALTY) {
                // if remaining COLLATERAL is less than penalty, remove the relayer from whitelist for being inactive
                _removeRelayerFromWhitelist(currentProposer);
                _distributeIncentive(msg.sender, relayerToBalance[currentProposer]);
                // relayerToBalance[msg.sender] += relayerToBalance[currentProposer];
                relayerToBalance[currentProposer] = 0;
            }
            else {
                relayerToBalance[currentProposer] -= BRIDGE_TIMESLOT_PENALTY;
                _distributeIncentive(msg.sender, BRIDGE_TIMESLOT_PENALTY);
                // relayerToBalance[msg.sender] += BRIDGE_TIMESLOT_PENALTY;
            }
        }

        // choose next block header proposer after the block header was updated
        _chooseRandomProposer();
    }

    function withdrawIncentive() external nonReentrant {
        require(relayerToIncentive[msg.sender] != 0, "No incentive to withdraw");
        
        payable(msg.sender).transfer(relayerToIncentive[msg.sender]);
        relayerToIncentive[msg.sender] = 0; // Reset the incentive balance to 0
    }

    // ------------------------------------------ 

    bytes4 public immutable defaultForkVersion;
    uint64 public headSlot;
    uint64 public headBlockNumber;
    uint256 public latestSyncCommitteePeriod;

    mapping(uint64 => uint64) internal _slot2block;
    mapping(uint64 => bytes32) internal _executionStateRoots;
    mapping(uint256 => bytes32) internal _syncCommitteeRootByPeriod;
    mapping(bytes32 => bytes32) internal _syncCommitteeRootToPoseidon;

    event HeaderUpdated(uint64 indexed slot, uint64 indexed blockNumber, bytes32 indexed executionRoot);
    event SyncCommitteeUpdated(uint64 indexed period, bytes32 indexed root);

    constructor(
        bytes32 genesisValidatorsRoot,
        uint256 genesisTime,
        uint256 secondsPerSlot,
        bytes4 forkVersion,
        uint256 startSyncCommitteePeriod,
        bytes32 startSyncCommitteeRoot,
        bytes32 startSyncCommitteePoseidon
    ) {
        GENESIS_VALIDATORS_ROOT = genesisValidatorsRoot;
        GENESIS_TIME = genesisTime;
        SECONDS_PER_SLOT = secondsPerSlot;
        defaultForkVersion = forkVersion;
        latestSyncCommitteePeriod = startSyncCommitteePeriod;
        _syncCommitteeRootByPeriod[startSyncCommitteePeriod] = startSyncCommitteeRoot;
        _syncCommitteeRootToPoseidon[startSyncCommitteeRoot] = startSyncCommitteePoseidon;

        periodToSubmitter[startSyncCommitteePeriod] = msg.sender;
        _syncCommitteeRootToSubmitter[startSyncCommitteeRoot] = msg.sender;
    }

    /// @notice MODIFIED: Added modifier
    /// @notice Updates the execution state root given a finalized light client update
    /// @dev The primary conditions for this are:
    ///      1) At least 2n/3+1 signatures from the current sync committee where n = 512
    ///      2) A valid merkle proof for the finalized header inside the currently attested header
    /// @param update a parameter just like in doxygen (must be followed by parameter name)
    function updateHeader(HeaderUpdate calldata update) external override onlyProposer {
        _verifyHeader(update);
        _updateHeader(update);
    }

    /// @notice MODIFIED: Added modifier, added syncCommitteeRootToSubmitter and periodToSubmitter mapping
    /// @notice Update the sync committee, it contains two updates actually: 
    ///         1. syncCommitteePoseidon
    ///         2. a header
    /// @dev Set the sync committee validator set root for the next sync committee period. This root 
    ///      is signed by the current sync committee. To make the proving cost of _headerBLSVerify(..) 
    ///      cheaper, we map the ssz merkle root of the validators to a poseidon merkle root (a zk-friendly 
    ///      hash function)
    /// @param update The header
    /// @param nextSyncCommitteePoseidon the syncCommitteePoseidon in the next sync committee period
    /// @param commitmentMappingProof A zkSnark proof to prove that `nextSyncCommitteePoseidon` is correct
    function updateSyncCommittee(
        HeaderUpdate calldata update,
        bytes32 nextSyncCommitteePoseidon,
        Groth16Proof calldata commitmentMappingProof
    ) external override onlyProposer {
        _verifyHeader(update);
        _updateHeader(update);

        uint64 currentPeriod = _getPeriodFromSlot(update.finalizedHeader.slot);
        uint64 nextPeriod = currentPeriod + 1;
        require(_syncCommitteeRootByPeriod[nextPeriod] == 0, "Next sync committee was already initialized");
        require(SimpleSerialize.isValidMerkleBranch(
                update.nextSyncCommitteeRoot,
                NEXT_SYNC_COMMITTEE_INDEX,
                update.nextSyncCommitteeBranch,
                update.finalizedHeader.stateRoot
            ), "Next sync committee proof is invalid");

        _mapRootToPoseidon(update.nextSyncCommitteeRoot, nextSyncCommitteePoseidon, commitmentMappingProof);

        latestSyncCommitteePeriod = nextPeriod;
        _syncCommitteeRootByPeriod[nextPeriod] = update.nextSyncCommitteeRoot;

        // Added mapping to track the incentive for the submitter
        periodToSubmitter[nextPeriod] = msg.sender;
        _syncCommitteeRootToSubmitter[update.nextSyncCommitteeRoot] = msg.sender;

        emit SyncCommitteeUpdated(nextPeriod, update.nextSyncCommitteeRoot);
    }

    /// @notice Verify a new header come from source chain
    /// @dev Implements shared logic for processing light client updates. In particular, it checks:
    ///      1) Does Merkle Inclusion Proof that proves inclusion of finalizedHeader in attestedHeader
    ///      2) Does Merkle Inclusion Proof that proves inclusion of executionStateRoot in finalizedHeader
    ///      3) Checks that 2n/3+1 signatures are provided
    ///      4) Verifies that the light client update has update.signature.participation signatures from 
    ///         the current sync committee with a zkSNARK
    /// @param update a set of params that contains attestedHeader and finalizedHeader and branches and 
    ///               proofs that prove the two header is correct
    function _verifyHeader(HeaderUpdate calldata update) internal view {
        require(update.finalityBranch.length > 0, "No finality branches provided");
        require(update.executionStateRootBranch.length > 0, "No execution state root branches provided");

        // TODO Potential for improvement: Use multi-node merkle inclusion proofs instead of 2 separate single proofs
        require(SimpleSerialize.isValidMerkleBranch(
                SimpleSerialize.sszBeaconBlockHeader(update.finalizedHeader),
                FINALIZED_ROOT_INDEX,
                update.finalityBranch,
                update.attestedHeader.stateRoot
            ), "Finality checkpoint proof is invalid");

        require(SimpleSerialize.isValidMerkleBranch(
                update.executionStateRoot,
                EXECUTION_STATE_ROOT_INDEX,
                update.executionStateRootBranch,
                update.finalizedHeader.bodyRoot
            ), "Execution state root proof is invalid");
        require(SimpleSerialize.isValidMerkleBranch(
                SimpleSerialize.toLittleEndian(update.blockNumber),
                BLOCK_NUMBER_ROOT_INDEX,
                update.blockNumberBranch,
                update.finalizedHeader.bodyRoot
            ), "Block number proof is invalid");

        require(
            3 * update.signature.participation > 2 * SYNC_COMMITTEE_SIZE, 
            "Not enough members of the sync committee signed"
        );

        uint64 currentPeriod = _getPeriodFromSlot(update.finalizedHeader.slot);
        bytes32 signingRoot = SimpleSerialize.computeSigningRoot(
            update.attestedHeader, 
            defaultForkVersion, 
            GENESIS_VALIDATORS_ROOT
        );
        require(
            _syncCommitteeRootByPeriod[currentPeriod] != 0, 
            "Sync committee was never updated for this period"
        );
        require(
            _headerBLSVerify(
                signingRoot, 
                _syncCommitteeRootByPeriod[currentPeriod], 
                update.signature.participation, 
                update.signature.proof
            ), 
            "Signature is invalid"
        );
    }

    /// @notice MODIFIED: Added note and slotToSubmitter
    function _updateHeader(HeaderUpdate calldata headerUpdate) internal {
        require(
            headerUpdate.finalizedHeader.slot > headSlot, 
            "Update slot must be greater than the current head"
        );
       
        require(
            headerUpdate.finalizedHeader.slot <= _getCurrentSlot(), 
            "Update slot is too far in the future"
        );

        headSlot = headerUpdate.finalizedHeader.slot;
        headBlockNumber = headerUpdate.blockNumber;
        _slot2block[headerUpdate.finalizedHeader.slot] = headerUpdate.blockNumber;
        _executionStateRoots[headerUpdate.finalizedHeader.slot] = headerUpdate.executionStateRoot;

        // ADDED
        // link the block to the submitter, so that they would accumulate the incentive
        slotToSubmitter[headerUpdate.finalizedHeader.slot] = msg.sender;
        //----

        emit HeaderUpdated(
            headerUpdate.finalizedHeader.slot, 
            headerUpdate.blockNumber, 
            headerUpdate.executionStateRoot
        );

    }

    /// @notice Maps a simple serialize merkle root to a poseidon merkle root with a zkSNARK. 
    /// @param syncCommitteeRoot sync committee root(ssz)
    /// @param syncCommitteePoseidon sync committee poseidon hash
    /// @param proof A zkSnarks proof to asserts that:
    ///              SimpleSerialize(syncCommittee) == Poseidon(syncCommittee).
    function _mapRootToPoseidon(
        bytes32 syncCommitteeRoot, 
        bytes32 syncCommitteePoseidon, 
        Groth16Proof calldata proof
    ) internal {
        uint256[33] memory inputs;
        // inputs is syncCommitteeSSZ[0..32] + [syncCommitteePoseidon]
        uint256 sszCommitmentNumeric = uint256(syncCommitteeRoot);
        for (uint256 i = 0; i < 32; i++) {
            inputs[32 - 1 - i] = sszCommitmentNumeric % 2 ** 8;
            sszCommitmentNumeric = sszCommitmentNumeric / 2 ** 8;
        }
        inputs[32] = uint256(syncCommitteePoseidon);
        require(
            SyncCommitteeRootToPoseidonVerifier.verifyCommitmentMappingProof(proof.a, proof.b, proof.c, inputs), 
            "Proof is invalid"
        );
        _syncCommitteeRootToPoseidon[syncCommitteeRoot] = syncCommitteePoseidon;
    }

    /// @notice Verify BLS signature
    /// @dev Does an aggregated BLS signature verification with a zkSNARK. The proof asserts that:
    ///      Poseidon(validatorPublicKeys) == _syncCommitteeRootToPoseidon[syncCommitteeRoot]
    ///      aggregatedPublicKey = InnerProduct(validatorPublicKeys, bitmap)
    ///      BLSVerify(aggregatedPublicKey, signature) == true
    /// @param signingRoot a parameter just like in doxygen (must be followed by parameter name)
    /// @return bool true/false
    function _headerBLSVerify(
        bytes32 signingRoot, 
        bytes32 syncCommitteeRoot, 
        uint256 claimedParticipation, 
        Groth16Proof calldata proof
    ) internal view returns (bool) {
        require(_syncCommitteeRootToPoseidon[syncCommitteeRoot] != 0, "Must map sync committee root to poseidon");
        uint256[34] memory inputs;
        inputs[0] = claimedParticipation;
        inputs[1] = uint256(_syncCommitteeRootToPoseidon[syncCommitteeRoot]);
        uint256 signingRootNumeric = uint256(signingRoot);
        for (uint256 i = 0; i < 32; i++) {
            inputs[(32 - 1 - i) + 2] = signingRootNumeric % 2 ** 8;
            signingRootNumeric = signingRootNumeric / 2 ** 8;
        }
        return HeaderBLSVerifier.verifySignatureProof(proof.a, proof.b, proof.c, inputs);
    }

    function _getCurrentSlot() internal view returns (uint64) {
        return uint64((block.timestamp - GENESIS_TIME) / SECONDS_PER_SLOT);
    }

    function _getPeriodFromSlot(uint64 slot) internal pure returns (uint64) {
        return uint64(slot / SLOTS_PER_SYNC_COMMITTEE_PERIOD);
    }

    function slot2block(uint64 _slot) external view returns (uint64) {
        return _slot2block[_slot];
    }

    /// @notice MODIFIED: state root require and set a fee
    function syncCommitteeRootByPeriod(uint256 _period) external payable returns (bytes32) {
        /// DeleteExpressionMutation(`require(_syncCommitteeRootByPeriod[_period] != bytes32(0), "Sync committee root not found for this period")` |==> `assert(true)`) of: `require(_syncCommitteeRootByPeriod[_period] != bytes32(0), "Sync committee root not found for this period");`
        assert(true);
        require(msg.value == SYNC_COMMITTEE_ROOT_PRICE, "Incorrect fee for sync committee root");

        // relayer who submitted the requested sync committee root will get the fee
        _distributeIncentive(periodToSubmitter[_period], msg.value);

        return _syncCommitteeRootByPeriod[_period];
    }

    /// @notice MODIFIED: state root require and set a fee
    function syncCommitteeRootToPoseidon(bytes32 _root) external payable returns (bytes32) {
        require(_syncCommitteeRootToPoseidon[_root] != bytes32(0), "Poseidon sync committee root not found for this sync committee root");
        require(msg.value == SYNC_COMMITTEE_ROOT_PRICE, "Incorrect fee for sync committee root");

        // relayer who submitted the requested sync committee root will get the fee
        _distributeIncentive(_syncCommitteeRootToSubmitter[_root], msg.value);

        return _syncCommitteeRootToPoseidon[_root];
    }


    /**
     * @dev Internal function to distribute incentives to a relayer. 
     *      This function manages the relayer's balance and incentive amounts.
     *      If the relayer's balance exceeds the predefined collateral limit, 
     *      the excess amount is moved to the incentive balance.
     *      It is needed to keep the collateral amount in the relayer's balance, so that it would not be removed from the whitelist
     *
     * @param relayer The address of the relayer to whom the incentive is distributed.
     * @param amount The amount to be added to the relayer's balance or incentive.
     */
    function _distributeIncentive(address relayer, uint256 amount) internal {
        if (relayerToBalance[relayer] == 0) {
            relayerToIncentive[relayer] += amount;
        }
        else {
            uint256 excess = 0;

            // Add the msg.value to the relayer's balance
            relayerToBalance[relayer] += amount;

            // Check if the balance exceeds the collateral
            if (relayerToBalance[relayer] > COLLATERAL) {
                excess = relayerToBalance[relayer] - COLLATERAL;

                // Move the excess to the incentive balance
                relayerToBalance[relayer] = COLLATERAL;
                relayerToIncentive[relayer] += excess;
            }
        }
    }

    /// @notice MODIFIED: state root require and set a fee
    /// @notice A function that allows you to get an executionStateRoot from a valid header
    /// @dev The executionStateRoot can be used to verify that if something happened on the source chain
    /// @param slot The slot corresponding to the executionStateRoot
    /// @return bytes32 Return the executionStateRoot corresponding to the slot
    function executionStateRoot(uint64 slot) external payable override returns (bytes32) {
        require(_executionStateRoots[slot] != bytes32(0), "Execution state root not found for this slot");
        require(msg.value == EXECUTION_STATE_ROOT_PRICE, "Incorrect fee for execution state root");
        
        // relayer who submitted the requested state root will get the fee
        _distributeIncentive(slotToSubmitter[slot], msg.value);

        return _executionStateRoots[slot];
    }
}
