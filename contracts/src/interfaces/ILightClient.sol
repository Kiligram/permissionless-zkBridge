pragma solidity 0.8.29;

import "../ethereum/Structs.sol";

interface ILightClientGetter {
    // function head() external view returns (uint64);

    // function headers(uint64 slot) external view returns (BeaconBlockHeader memory);

    // function stateRoot(uint64 slot) external view returns (bytes32);
    function syncCommitteeRootByPeriod(uint256 _period) external payable returns (bytes32);
    function syncCommitteeRootToPoseidon(bytes32 _root) external payable returns (bytes32);

    /// @notice MODIFIED: removed `view` from the function signature to allow payment
    function executionStateRoot(uint64 slot) external payable returns (bytes32);
}

interface ILightClientSetter {
    
    function updateHeader(HeaderUpdate calldata update) external;
    
    function updateSyncCommittee(
        HeaderUpdate calldata update,
        bytes32 nextSyncCommitteePoseidon,
        Groth16Proof calldata commitmentMappingProof
    ) external;
}