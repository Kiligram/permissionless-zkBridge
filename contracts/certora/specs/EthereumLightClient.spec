definition SYNC_COMMITTEE_SIZE() returns uint256 = 512;
definition SLOTS_PER_SYNC_COMMITTEE_PERIOD() returns uint256 = 8192;

methods
{
    // When a function is not using the environment (e.g., `msg.sender`), it can be
    // declared as `envfree`
    function COLLATERAL() external returns (uint256) envfree;
    function BRIDGE_BLOCK_PROPOSAL_TIMESLOT() external returns (uint256) envfree;
    function SYNC_COMMITTEE_ROOT_PRICE() external returns (uint256) envfree;
    function BRIDGE_TIMESLOT_PENALTY() external returns (uint256) envfree;
    function EXECUTION_STATE_ROOT_PRICE() external returns (uint256) envfree;
    function BRIDGE_BLOCK_PROPOSAL_TIMESLOT() external returns (uint256) envfree;
    function GENESIS_TIME() external returns (uint256) envfree;
    function SECONDS_PER_SLOT() external returns (uint256) envfree;

    /**
     * The following functions are used to verify the zk-SNARK proofs. For certora it is impossible to assume
     * all possible proofs, so we use the `NONDET` summarization to assume that the proof verification
     * functions can return any bool value, no matter the input. Without this, the rules would be considered vacuous.
    */
    function HeaderBLSVerifier.verifySignatureProof(uint[2] memory, uint[2][2] memory, uint[2] memory, uint[34] memory) internal returns (bool) => NONDET;
    function SyncCommitteeRootToPoseidonVerifier.verifyCommitmentMappingProof(uint[2] memory, uint[2][2] memory, uint[2] memory, uint[33] memory) internal returns (bool) => NONDET;
}

// a cvl function for precondition assumptions 
function setup(env e){
    require e.msg.sender != currentContract;
    require e.msg.sender != 0;
    require currentContract.whitelistArray.length < max_uint256;
    require COLLATERAL() > 0; // if collateral is 0, then the relayer can add itself multiple times to increase the chance to be selected
}

// parametric rule
rule onlyCertainFunctionsCanChangeContractBalance(method f) {

    env e;    
    calldataarg args;  // Arguments for the method f

    require (e.msg.sender != currentContract);

    mathint contract_balance_before = nativeBalances[currentContract];
    f(e, args);  

    mathint contract_balance_after = nativeBalances[currentContract];

    // Assert that if contract balance changed then the following functions were called.
    assert (
        contract_balance_after > contract_balance_before => 
        (
            f.selector == sig:joinRelayerNetwork().selector ||
            f.selector == sig:syncCommitteeRootByPeriod(uint256).selector ||
            f.selector == sig:syncCommitteeRootToPoseidon(bytes32).selector ||
            f.selector == sig:executionStateRoot(uint64).selector
        )
    ),
    "only certain functions can increase contract's balance";

    assert (
        contract_balance_after < contract_balance_before => 
        (
            f.selector == sig:exitRelayerNetwork().selector ||
            f.selector == sig:withdrawIncentive().selector 
        )
    ),
    "only certain functions can decrease contract's balance";
}


// powerful invariant that verifies that the contract has always a balance enough to pay all the relayers
// it proves the integrity of funds
ghost mathint totalCollateralBalance {
    init_state axiom totalCollateralBalance == nativeBalances[currentContract];
}

hook Sstore relayerToBalance[KEY address relayer]
    uint256 newVal (uint256 oldVal) {
    totalCollateralBalance = totalCollateralBalance + newVal - oldVal;
}

ghost mathint totalIncentiveBalance {
    init_state axiom totalIncentiveBalance == 0;
}

hook Sstore relayerToIncentive[KEY address relayer]
    uint256 newVal (uint256 oldVal) {
    totalIncentiveBalance = totalIncentiveBalance + newVal - oldVal;
}

// stakeholder invariant
// make sure that the contract balance always equals the sum of all relayers' balances
// by this we ensure that the contract always has enough funds to pay all the relayers 
invariant totalCollateralEqualsContractBalance()
    nativeBalances[currentContract] == totalCollateralBalance + totalIncentiveBalance
    {
        // we make an assumption that the function caller is never the contract itself, because otherwise it would not change the contract balance
        preserved with (env e){ 
            setup(e);
        }
    }

invariant zeroAddressCanNotBeInWhitelist()
    forall uint256 index. (index < currentContract.whitelistArray.length => currentContract.whitelistArray[index] != 0)
    {
        preserved with (env e){
            setup(e);
        }
    }

// stakeholder invariant
invariant thereIsAlwaysProposerIfSomeoneIsInWhitelist()
    currentContract.whitelistArray.length > 0 <=> currentContract.currentProposer != 0
    {
        preserved with (env e){
            setup(e);
            requireInvariant zeroAddressCanNotBeInWhitelist();
        }
    }

// stakeholder invariant
invariant thereIsAlwaysSubmitterForExistingExecutionStateRoot(uint64 slot)
    currentContract.slotToSubmitter[slot] != 0 <=> currentContract._executionStateRoots[slot] != to_bytes32(0)
    {
        preserved with (env e){
            setup(e);
        }
        preserved updateHeader(EthereumLightClient.HeaderUpdate update) with (env e){
            setup(e);
            // we assume that the executionStateRoot can never be 0
            require update.executionStateRoot != to_bytes32(0);
        }
        preserved updateSyncCommittee(EthereumLightClient.HeaderUpdate update, bytes32 nextSyncCommitteePoseidon, EthereumLightClient.Groth16Proof commitmentMappingProof) with (env e){
            setup(e);
            // we assume that the executionStateRoot can never be 0
            require update.executionStateRoot != to_bytes32(0);
        }
    }

/**
    the problem is that certora assumes there is some relayer in the whitelist, which does not have the collateral
    here we are comparing each element of the whitelist with each other to check that there are no duplicates
    normally that would have been done by ghost + hook, but certora does not properly support hooking in dynamic arrays
    even official representative could not help with that.
    We even have to make an assumption that if there is a relayer in the whitelist, then this relayer has a collateral, because otherwise joinRelayerNetwork() will fail because certora assumes that there can be relayer in the whitelist without collateral.
*/
invariant noDuplicatesInWhitelist()
    forall uint256 index1. (index1 < currentContract.whitelistArray.length => 
    (forall uint256 index2. ((index2 < currentContract.whitelistArray.length && index1 != index2) => 
    currentContract.whitelistArray[index1] != currentContract.whitelistArray[index2])))
    {
        preserved with (env e){
            setup(e);
        }
        preserved joinRelayerNetwork() with (env e){
            setup(e);
            // here we assume that if there is a relayer in the whitelist, then this relayer has a collateral
            requireInvariant thereIsACollateralIfIsInWhitelist(e.msg.sender);
        }
    }

// double polarity issue is there is <=> therefore we split this invariant into two
invariant thereIsACollateralIfIsInWhitelist(address relayer) 
    (exists uint256 index. index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == relayer) => currentContract.relayerToBalance[relayer] > 0
    {
        preserved with (env e){ 
            setup(e);
            requireInvariant noDuplicatesInWhitelist();
        }
    }

invariant isInTheWhiteListIfHasCollateral(address relayer) 
    currentContract.relayerToBalance[relayer] > 0 => (exists uint256 index. (index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == relayer))
    {
        preserved with (env e){ 
            setup(e);
        }
    }

invariant proposerIsAlwaysWhitelisted()
    currentContract.currentProposer != 0 => (exists uint256 index. (index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == currentContract.currentProposer))
    {
        preserved with (env e){
            setup(e);
        }
    } 

rule joinRelayerNetworkUnitTest(){
    env e;
    setup(e);
    
    requireInvariant proposerIsAlwaysWhitelisted();
    requireInvariant thereIsACollateralIfIsInWhitelist(e.msg.sender);

    mathint contract_balance_before = nativeBalances[currentContract];
    joinRelayerNetwork(e);
    mathint contract_balance_after = nativeBalances[currentContract];


    assert contract_balance_after == contract_balance_before + COLLATERAL(),
        "Contract balance must increase after relayer joins";

    assert currentContract.relayerToBalance[e.msg.sender] == COLLATERAL(),
        "Relayer balance must be equal to the collateral";

    uint256 relayer_index = assert_uint256(currentContract.whitelistArray.length - 1);
    assert currentContract.whitelistArray[relayer_index] == e.msg.sender,
        "Relayer must be added to the end of whitelist array";

    assert currentContract.whitelistArray.length == 1 <=> currentContract.currentProposer == e.msg.sender && currentContract.currentProposerExpiration == e.block.timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT(),
        "If this is the first relayer, then it must be the current proposer and its expiration time must be set to the current block timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT";
}

rule withdrawUnitTest(){
    env e;
    setup(e);
    requireInvariant totalCollateralEqualsContractBalance();

    mathint relayer_native_balance_before = nativeBalances[e.msg.sender];
    mathint relayer_incentive = currentContract.relayerToIncentive[e.msg.sender];
    withdrawIncentive(e);

    assert currentContract.relayerToIncentive[e.msg.sender] == 0,
        "Relayer incentive balance must be 0 after withdrawal";
    
    assert nativeBalances[e.msg.sender] == relayer_native_balance_before + relayer_incentive,
        "Relayer eth balance must increase by the incentive";
}

rule exitRelayerNetworkUnitTest(){
    env e;
    setup(e);
    requireInvariant noDuplicatesInWhitelist();

    mathint relayer_balance_before = nativeBalances[e.msg.sender];
    mathint relayer_collateral_before = currentContract.relayerToBalance[e.msg.sender];
    exitRelayerNetwork(e);

    assert nativeBalances[e.msg.sender] == relayer_balance_before + relayer_collateral_before,
        "Relayer's eth balance must increase by the relayer's collateral";

    assert currentContract.relayerToBalance[e.msg.sender] == 0,
        "Relayer's collateral balance must be 0 after exiting the network";

    // check that the relayer is removed from the whitelist array, we need to use noDuplicatesInWhitelist invariant for this
    assert !(exists uint256 index. (index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == e.msg.sender)),
        "Relayer must be removed from the whitelist array";
}


function assertIncentive(
    mathint relayer_incentive_before,
    mathint relayer_collateral_before,
    mathint relayer_incentive_after,
    mathint relayer_collateral_after,
    mathint incentive_to_distribute
) {
    mathint excess = relayer_collateral_before + incentive_to_distribute - COLLATERAL();

    if (relayer_collateral_before == 0) {
        assert relayer_collateral_after == relayer_collateral_before && relayer_incentive_after == relayer_incentive_before + incentive_to_distribute,
            "When the relayer is not in the whitelist anymore, the relayer's collateral balance must remain zero and the whole incentive must be added to the relayer's incentive balance";        
    }
    else {
        assert excess > 0 => (relayer_incentive_after == relayer_incentive_before + excess && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) exceeds the collateral balance, the rest must go to the incentive balance";
            

        assert excess == 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) is equal to the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must be equal to the collateral";

        
        assert excess < 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == relayer_collateral_before + incentive_to_distribute),
            "When the (collateral balance + incentive) is less than the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must increase by the sync committee root price";   
    }
}


rule syncCommitteeRootByPeriodUnitTest(uint256 _period){
    env e;
    setup(e);

    address relayer_address = currentContract.periodToSubmitter[_period];
    mathint relayer_incentive_before = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_before = currentContract.relayerToBalance[relayer_address];
    bytes32 return_value = syncCommitteeRootByPeriod(e, _period);
    mathint relayer_incentive_after = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_after = currentContract.relayerToBalance[relayer_address];

    assertIncentive(relayer_incentive_before, relayer_collateral_before, relayer_incentive_after, relayer_collateral_after, SYNC_COMMITTEE_ROOT_PRICE());

    assert return_value != to_bytes32(0),
        "Sync committee root cannot be 0";
    
    assert return_value == currentContract._syncCommitteeRootByPeriod[_period],
        "Function must return the sync committee root for the given period";
}


rule syncCommitteeRootToPoseidonUnitTest(bytes32 _root){
    env e;
    setup(e);

    address relayer_address = currentContract._syncCommitteeRootToSubmitter[_root];
    mathint relayer_incentive_before = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_before = currentContract.relayerToBalance[relayer_address];
    bytes32 return_value = syncCommitteeRootToPoseidon(e, _root);
    mathint relayer_incentive_after = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_after = currentContract.relayerToBalance[relayer_address];

    assertIncentive(relayer_incentive_before, relayer_collateral_before, relayer_incentive_after, relayer_collateral_after, SYNC_COMMITTEE_ROOT_PRICE());

    assert return_value != to_bytes32(0),
        "Sync committee root cannot be 0";

    assert return_value == currentContract._syncCommitteeRootToPoseidon[_root],
        "Function must return the poseidon sync committee root for the given sync committee root";
}

rule executionStateRootUnitTest(uint64 slot){
    env e;
    setup(e);

    address relayer_address = currentContract.slotToSubmitter[slot];
    mathint relayer_incentive_before = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_before = currentContract.relayerToBalance[relayer_address];
    bytes32 return_value = executionStateRoot(e, slot);
    mathint relayer_incentive_after = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_after = currentContract.relayerToBalance[relayer_address];

    assertIncentive(relayer_incentive_before, relayer_collateral_before, relayer_incentive_after, relayer_collateral_after, EXECUTION_STATE_ROOT_PRICE());

    assert return_value != to_bytes32(0),
        "Sync committee root cannot be 0";

    assert return_value == currentContract._executionStateRoots[slot],
        "Function must return the execution state root for the given slot";
}


rule updateHeaderUnitTest(EthereumLightClient.HeaderUpdate headerUpdate){
    env e;
    setup(e);

    updateHeader(e, headerUpdate);

    assert currentContract.headSlot == headerUpdate.finalizedHeader.slot,
        "Head slot must be updated to the new slot";
    
    assert currentContract.headBlockNumber == headerUpdate.blockNumber,
        "Head block number must be updated to the new block number";
    
    assert currentContract._slot2block[headerUpdate.finalizedHeader.slot] == headerUpdate.blockNumber,
        "There must be added the block number for the given slot";
    
    assert currentContract._executionStateRoots[headerUpdate.finalizedHeader.slot] == headerUpdate.executionStateRoot,
        "There must be added the execution state root for the given slot";

    assert currentContract.slotToSubmitter[headerUpdate.finalizedHeader.slot] == e.msg.sender,
        "The submitter of the header must be added to the list for incentivization";
}


rule updateSyncCommitteeUnitTest(EthereumLightClient.HeaderUpdate headerUpdate, bytes32 nextSyncCommitteePoseidon, EthereumLightClient.Groth16Proof proof){
    env e;
    setup(e);

    updateSyncCommittee(e, headerUpdate, nextSyncCommitteePoseidon, proof);

    // headerUpdate test
    assert currentContract.headSlot == headerUpdate.finalizedHeader.slot,
        "Head slot must be updated to the new slot";
    
    assert currentContract.headBlockNumber == headerUpdate.blockNumber,
        "Head block number must be updated to the new block number";
    
    assert currentContract._slot2block[headerUpdate.finalizedHeader.slot] == headerUpdate.blockNumber,
        "There must be added the block number for the given slot";
    
    assert currentContract._executionStateRoots[headerUpdate.finalizedHeader.slot] == headerUpdate.executionStateRoot,
        "There must be added the execution state root for the given slot";

    assert currentContract.slotToSubmitter[headerUpdate.finalizedHeader.slot] == e.msg.sender,
        "The submitter of the header must be added to the list for incentivization";
    // headerUpdate test end

    // verifying the sync committee roots submission
    uint256 SLOTS_PER_SYNC_COMMITTEE_PERIOD = 8192;
    uint256 next_period = assert_uint256((headerUpdate.finalizedHeader.slot / SLOTS_PER_SYNC_COMMITTEE_PERIOD) + 1);

    assert currentContract.latestSyncCommitteePeriod == next_period,
        "The latest sync committee period must be updated to the new period";
    
    assert currentContract._syncCommitteeRootByPeriod[next_period] == headerUpdate.nextSyncCommitteeRoot,
        "The sync committee root for the next period must be updated to the new root";

    assert currentContract._syncCommitteeRootToPoseidon[headerUpdate.nextSyncCommitteeRoot] == nextSyncCommitteePoseidon,
        "There must be added the poseidon sync committee root for the given sync committee root";

    assert currentContract.periodToSubmitter[next_period] == e.msg.sender,
        "The submitter of the sync committee root must be added to the list for incentivization";

    assert currentContract._syncCommitteeRootToSubmitter[headerUpdate.nextSyncCommitteeRoot] == e.msg.sender,
        "The submitter of the poseidon sync committee root must be added to the list for incentivization";
}


rule onlyProposerModifierPenalizationUnitTest(method f) filtered {
    f -> f.selector == sig:updateHeader(EthereumLightClient.HeaderUpdate).selector ||  
         f.selector == sig:updateSyncCommittee(EthereumLightClient.HeaderUpdate, bytes32, EthereumLightClient.Groth16Proof).selector
} {
    env e;    
    setup(e);
    requireInvariant noDuplicatesInWhitelist();
    // we assume that the chosen proposer did not manage to submit the header in time, so it will be penalized
    require e.msg.sender != currentContract.currentProposer;

    calldataarg args;  // Arguments for the method f

    address proposer_before = currentContract.currentProposer;
    mathint proposer_before_collateral = currentContract.relayerToBalance[proposer_before];

    mathint relayer_incentive_before = currentContract.relayerToIncentive[e.msg.sender];
    mathint relayer_collateral_before = currentContract.relayerToBalance[e.msg.sender];
    f(e, args);
    mathint relayer_incentive_after = currentContract.relayerToIncentive[e.msg.sender];
    mathint relayer_collateral_after = currentContract.relayerToBalance[e.msg.sender];

    // verifying incentive for the submitter
    if (proposer_before_collateral <= BRIDGE_TIMESLOT_PENALTY()){
        assertIncentive(relayer_incentive_before, relayer_collateral_before, relayer_incentive_after, relayer_collateral_after, proposer_before_collateral);
    }
    else {
        assertIncentive(relayer_incentive_before, relayer_collateral_before, relayer_incentive_after, relayer_collateral_after, BRIDGE_TIMESLOT_PENALTY());
    }

    // verifying penalization for the proposer who missed his timeslot
    assert (proposer_before_collateral <= BRIDGE_TIMESLOT_PENALTY()) => currentContract.relayerToBalance[proposer_before] == 0,
        "If the proposer was penalized and removed from the whitelist, then its balance must be 0";

    assert (proposer_before_collateral <= BRIDGE_TIMESLOT_PENALTY()) => !(exists uint256 index. (index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == proposer_before)),
        "If the proposer was penalized and removed from the whitelist, then it must not be in the whitelist anymore";

    assert (proposer_before_collateral > BRIDGE_TIMESLOT_PENALTY()) => currentContract.relayerToBalance[proposer_before] == 
        proposer_before_collateral - BRIDGE_TIMESLOT_PENALTY(),
        "If the proposer was penalized and not removed from the whitelist, then its balance must be decreased by the penalty";
    
}


rule chooseRandomProposerUnitTest(method f) filtered {
    f -> f.selector == sig:updateHeader(EthereumLightClient.HeaderUpdate).selector ||  
         f.selector == sig:updateSyncCommittee(EthereumLightClient.HeaderUpdate, bytes32, EthereumLightClient.Groth16Proof).selector
} {
    env e;    
    setup(e);
    requireInvariant noDuplicatesInWhitelist();

    calldataarg args;  // Arguments for the method f

    f(e, args);  

    assert currentContract.whitelistArray.length == 0 => currentContract.currentProposer == 0,
        "If there are no relayers in the whitelist, then the current proposer must be 0";

    assert currentContract.whitelistArray.length != 0 => currentContract.currentProposerExpiration == e.block.timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT(),
        "If there are relayers in the whitelist, there must be set expiration time for current proposer";
}


rule joinRelayerNetworkMustRevert(){
    env e;
    setup(e);
    
    require e.msg.value != COLLATERAL() || currentContract.relayerToBalance[e.msg.sender] != 0;

    joinRelayerNetwork@withrevert(e);

    assert lastReverted,
        "joinRelayerNetwork() must revert if the relayer is already in the whitelist or the send eth value is not equal to the collateral";
}

rule exitRelayerNetworkMustRevert(){
    env e;
    setup(e);
    
    require (e.msg.sender == currentContract.currentProposer &&currentContract.whitelistArray.length != 1) || currentContract.relayerToBalance[e.msg.sender] == 0;

    exitRelayerNetwork@withrevert(e);

    assert lastReverted,
        "exitRelayerNetwork() must revert if the relayer is current proposer and it is not the only relayer in the whitelist";
}

rule withdrawIncentiveMustRevert(){
    env e;
    setup(e);
    
    require currentContract.relayerToIncentive[e.msg.sender] == 0;

    withdrawIncentive@withrevert(e);

    assert lastReverted,
        "withdrawIncentive() must revert if there is no incentive for the relayer";
}

function _getCurrentSlot(env e) returns uint64 {
    return assert_uint64((e.block.timestamp - GENESIS_TIME()) / SECONDS_PER_SLOT());
}

function _getPeriodFromSlot(uint64 slot) returns uint64 {
    return assert_uint64(slot / SLOTS_PER_SYNC_COMMITTEE_PERIOD());
}

rule verifyHeaderMustRevert(EthereumLightClient.HeaderUpdate update) {
    env e;    
    setup(e);
    
    require SECONDS_PER_SLOT() > 0;
    require (e.block.timestamp - GENESIS_TIME()) / SECONDS_PER_SLOT() > 0 &&
            (e.block.timestamp - GENESIS_TIME()) / SECONDS_PER_SLOT() < max_uint64;
    uint64 currentPeriod = _getPeriodFromSlot(update.finalizedHeader.
    slot);
    uint64 currentSlot = _getCurrentSlot(e);

    require update.finalityBranch.length == 0 ||
            update.executionStateRootBranch.length == 0 ||
            3 * update.signature.participation <= 2 * SYNC_COMMITTEE_SIZE() ||
            currentContract._syncCommitteeRootByPeriod[currentPeriod] == to_bytes32(0) ||
            update.finalizedHeader.slot <= currentContract.headSlot ||
            update.finalizedHeader.slot > currentSlot;

    updateHeader@withrevert(e, update);

    assert lastReverted,
        "verifyHeader() must revert if the specified conditions are not met";
}


rule updateSyncCommitteeMustRevert(EthereumLightClient.HeaderUpdate update, bytes32 nextSyncCommitteePoseidon, EthereumLightClient.Groth16Proof proof) {
    env e;    
    setup(e);

    uint64 nextPeriod = assert_uint64(_getPeriodFromSlot(update.finalizedHeader.
    slot) + 1);

    require currentContract._syncCommitteeRootByPeriod[nextPeriod] != to_bytes32(0);

    updateSyncCommittee@withrevert(e, update, nextSyncCommitteePoseidon, proof);

    assert lastReverted,
        "updateSyncCommittee() must revert if sync committee root for this period was already submitted";
}

rule onlyProposerMustRevert(method f) filtered {
    f -> f.selector == sig:updateHeader(EthereumLightClient.HeaderUpdate).selector ||  
         f.selector == sig:updateSyncCommittee(EthereumLightClient.HeaderUpdate, bytes32, EthereumLightClient.Groth16Proof).selector
} {
    env e;    
    setup(e);
    
    require (e.msg.sender != currentContract.currentProposer && currentContract.currentProposerExpiration >= e.block.timestamp) || 
            currentContract.relayerToBalance[e.msg.sender] == 0;


    calldataarg args;  // Arguments for the method f

    f@withrevert(e, args);  

    assert lastReverted,
        "onlyProposer() modifier must cause revert if the relayer is not the current proposer or it is not in the whitelist. Also must revert if the caller is not in the whitelist and the proposer time is expired";
}

rule eachMethodMustHaveNonRevertedPath(method f) {
    env e;    
    calldataarg args;  // Arguments for the method f

    f@withrevert(e, args);  

    satisfy !lastReverted,
        "all methods must have non-reverted path";    
}

// nativeCodesize is not in official docs, but is in their github: https://github.com/Certora/Examples/tree/master/CVLByExample/NativeCodeSize
rule removeRelayerFromWhitelistLivenessTest() {
    env e;    
    setup(e);
    
    require e.msg.value == 0;
    require e.msg.sender != currentContract.currentProposer ||
            currentContract.whitelistArray.length == 1;
    require currentContract.relayerToBalance[e.msg.sender] > 0;
    require currentContract._status == 1;
    require currentContract.relayerToBalance[e.msg.sender] + nativeBalances[e.msg.sender] <= max_uint256;
    require nativeBalances[currentContract] >= currentContract.relayerToBalance[e.msg.sender];
    require nativeCodesize[e.msg.sender] == 0;

    exitRelayerNetwork@withrevert(e);
 
    assert !lastReverted,
        "exitRelayerNetwork() must not revert";
}