methods
{
    // When a function is not using the environment (e.g., `msg.sender`), it can be
    // declared as `envfree`
    // function joinRelayerNetwork(address) external payable;
    // function allowance(address,address) external returns(uint) envfree;
    function COLLATERAL() external returns (uint256) envfree;
    function BRIDGE_BLOCK_PROPOSAL_TIMESLOT() external returns (uint256) envfree;
    function SYNC_COMMITTEE_ROOT_PRICE() external returns (uint256) envfree;
    function BRIDGE_TIMESLOT_PENALTY() external returns (uint256) envfree;
    function EXECUTION_STATE_ROOT_PRICE() external returns (uint256) envfree;
    function BRIDGE_BLOCK_PROPOSAL_TIMESLOT() external returns (uint256) envfree;

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
    require COLLATERAL() > 0; // important to use later, because if collateral is 0, then the relayer can add itself multiple times to increase the chance to be selected
}

rule joinRelayerNetworkUnitTest(){
    env e;
    setup(e);
    
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

    assert currentContract.whitelistArray.length == 1 => currentContract.currentProposer == e.msg.sender && currentContract.currentProposerExpiration == e.block.timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT(),
        "If this is the first relayer, then it must be the current proposer and its expiration time must be set to the current block timestamp + BRIDGE_BLOCK_PROPOSAL_TIMESLOT";
        
}

rule withdrawUnitTest(){
    env e;
    setup(e);
    requireInvariant totalCollateralEqualsContractBalance();

    mathint relayer_native_balance_before = nativeBalances[e.msg.sender];
    mathint relayer_incentive = currentContract.relayerToIncentive[e.msg.sender];
    withdrawIncentive(e);
    // mathint relayer_balance_after = currentContract.relayerToBalance[e.msg.sender];

    assert currentContract.relayerToIncentive[e.msg.sender] == 0,
        "Relayer incentive balance must be 0 after withdrawal";
    
    assert nativeBalances[e.msg.sender] == relayer_native_balance_before + relayer_incentive,
        "Relayer eth balance must increase by the incentive";
}

rule exitRelayerNetworkUnitTest(){
    env e;
    setup(e);

    // assert forall uint256 index. (index < currentContract.whitelistArray.length => currentContract.whitelistArray[index] != 0)
    mathint relayer_balance_before = nativeBalances[e.msg.sender];
    mathint relayer_collateral_before = currentContract.relayerToBalance[e.msg.sender];
    exitRelayerNetwork(e);

    assert nativeBalances[e.msg.sender] == relayer_balance_before + relayer_collateral_before,
        "Relayer's eth balance must increase by the relayer's collateral";

    assert currentContract.relayerToBalance[e.msg.sender] == 0,
        "Relayer's collateral balance must be 0 after exiting the network";

    // TODO: check that the relayer is removed from the whitelist array, but it is needed to add that there are no duplicates in the whitelist array
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

// relayerToBalance[periodToSubmitter[_period]] += msg.value;
rule syncCommitteeRootByPeriodUnitTest(uint256 _period){
    env e;
    setup(e);

    address relayer_address = currentContract.periodToSubmitter[_period];
    mathint relayer_incentive_before = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_before = currentContract.relayerToBalance[relayer_address];
    bytes32 return_value = syncCommitteeRootByPeriod(e, _period);
    mathint relayer_incentive_after = currentContract.relayerToIncentive[relayer_address];
    mathint relayer_collateral_after = currentContract.relayerToBalance[relayer_address];

    assert return_value != to_bytes32(0),
        "Sync committee root cannot be 0";
    
    assert return_value == currentContract._syncCommitteeRootByPeriod[_period],
        "Function must return the sync committee root for the given period";

    mathint excess = relayer_collateral_before + SYNC_COMMITTEE_ROOT_PRICE() - COLLATERAL();

    if (relayer_collateral_before == 0) {
        assert relayer_collateral_after == relayer_collateral_before && relayer_incentive_after == relayer_incentive_before + SYNC_COMMITTEE_ROOT_PRICE(),
            "When the relayer is not in the whitelist anymore, the relayer's collateral balance must remain zero and the whole incentive must be added to the relayer's incentive balance";        
    }
    else {
        assert excess > 0 => (relayer_incentive_after == relayer_incentive_before + excess && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) exceeds the collateral balance, the rest must go to the incentive balance";
            

        assert excess == 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) is equal to the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must be equal to the collateral";

        
        assert excess < 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == relayer_collateral_before + SYNC_COMMITTEE_ROOT_PRICE()),
            "When the (collateral balance + incentive) is less than the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must increase by the sync committee root price";   
    }
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

    assert return_value != to_bytes32(0),
        "Sync committee root cannot be 0";

    assert return_value == currentContract._syncCommitteeRootToPoseidon[_root],
        "Function must return the poseidon sync committee root for the given sync committee root";

    mathint excess = relayer_collateral_before + SYNC_COMMITTEE_ROOT_PRICE() - COLLATERAL();

    if (relayer_collateral_before == 0) {
        assert relayer_collateral_after == relayer_collateral_before && relayer_incentive_after == relayer_incentive_before + SYNC_COMMITTEE_ROOT_PRICE(),
            "When the relayer is not in the whitelist anymore, the relayer's collateral balance must remain zero and the whole incentive must be added to the relayer's incentive balance";        
    }
    else {
        assert excess > 0 => (relayer_incentive_after == relayer_incentive_before + excess && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) exceeds the collateral balance, the rest must go to the incentive balance";
            

        assert excess == 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) is equal to the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must be equal to the collateral";

        
        assert excess < 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == relayer_collateral_before + SYNC_COMMITTEE_ROOT_PRICE()),
            "When the (collateral balance + incentive) is less than the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must increase by the sync committee root price";   
    }
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

    assert return_value != to_bytes32(0),
        "Sync committee root cannot be 0";

    assert return_value == currentContract._executionStateRoots[slot],
        "Function must return the execution state root for the given slot";

    mathint excess = relayer_collateral_before + EXECUTION_STATE_ROOT_PRICE() - COLLATERAL();

    if (relayer_collateral_before == 0) {
        assert relayer_collateral_after == relayer_collateral_before && relayer_incentive_after == relayer_incentive_before + EXECUTION_STATE_ROOT_PRICE(),
            "When the relayer is not in the whitelist anymore, the relayer's collateral balance must remain zero and the whole incentive must be added to the relayer's incentive balance";        
    }
    else {
        assert excess > 0 => (relayer_incentive_after == relayer_incentive_before + excess && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) exceeds the collateral balance, the rest must go to the incentive balance";
            

        assert excess == 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == COLLATERAL()),
            "When the (collateral balance + incentive) is equal to the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must be equal to the collateral";

        
        assert excess < 0 => (relayer_incentive_after == relayer_incentive_before && relayer_collateral_after == relayer_collateral_before + EXECUTION_STATE_ROOT_PRICE()),
            "When the (collateral balance + incentive) is less than the collateral, the relayer's incentive balance must not change and the relayer's collateral balance must increase by the sync committee root price";   
    }
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

        // _syncCommitteeRootToPoseidon[syncCommitteeRoot] = syncCommitteePoseidon; done
    
        // latestSyncCommitteePeriod = nextPeriod; done 
        // _syncCommitteeRootByPeriod[nextPeriod] = update.nextSyncCommitteeRoot; done

        // periodToSubmitter[nextPeriod] = msg.sender;
        // _syncCommitteeRootToSubmitter[update.nextSyncCommitteeRoot] = msg.sender;
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

        // if(msg.sender != currentProposer){
        //     if (relayerToBalance[currentProposer] <= BRIDGE_TIMESLOT_PENALTY) {
        //         // if remaining COLLATERAL is less than penalty, remove the relayer from whitelist for being inactive
        //         _removeRelayerFromWhitelist(currentProposer);
        //         _distributeIncentive(msg.sender, relayerToBalance[currentProposer]);
        //         // relayerToBalance[msg.sender] += relayerToBalance[currentProposer];
        //         relayerToBalance[currentProposer] = 0;
        //     }
        //     else {
        //         relayerToBalance[currentProposer] -= BRIDGE_TIMESLOT_PENALTY;
        //         _distributeIncentive(msg.sender, BRIDGE_TIMESLOT_PENALTY);
        //         // relayerToBalance[msg.sender] += BRIDGE_TIMESLOT_PENALTY;
        //     }
        // }


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

/// make sure that the contract balance is never less the total collateral balance
invariant totalCollateralEqualsContractBalance()
    nativeBalances[currentContract] == totalCollateralBalance + totalIncentiveBalance
    {
        // we make an assumption that the function caller is never the contract itself, because otherwise it would not change the contract balance
        preserved with (env e){ 
            setup(e);
        }
    }


// the problem is that it just needs to be sure that there are no 2 the same addresses in the whitelist
invariant zeroAddressCanNotBeInWhitelist()
    // currentContract.whitelistArray.length > 0 => !(exists uint256 index. currentContract.whitelistArray[index] == 0)
    forall uint256 index. (index < currentContract.whitelistArray.length => currentContract.whitelistArray[index] != 0)
    {
        preserved with (env e){
            // requireInvariant noDuplicatesInWhitelist();
            setup(e);
        }
    }

invariant thereIsAlwaysProposerIfSomeoneIsInWhitelist()
    currentContract.whitelistArray.length > 0 <=> currentContract.currentProposer != 0
    {
        preserved with (env e){
            setup(e);
            requireInvariant zeroAddressCanNotBeInWhitelist();
        }
    }

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

    // function syncCommitteeRootByPeriod(uint256 _period) external payable returns (bytes32) {
    //     require(_syncCommitteeRootByPeriod[_period] != bytes32(0), "Sync committee root not found for this period");
    //     require(msg.value == SYNC_COMMITTEE_ROOT_PRICE, "Incorrect fee for sync committee root");

    //     // relayer who submitted the requested sync committee root will get the fee
    //     relayerToBalance[periodToSubmitter[_period]] += msg.value;

    //     return _syncCommitteeRootByPeriod[_period];
    // }

// invariant thereIsAlwaysSubmitterForExistingSyncCommitteeRootToPoseidon(bytes32 root)

// does not work because certora assumes that the sender can be 0
// it is possible to rewrite it to parametric rule, so that there would not be the constructor induction base
// then it would be possible to use require the invariant safely in other rules since we would have it proven
// invariant thereIsAlwaysSubmitterForExistingPeriod(uint256 _period)
//     currentContract._syncCommitteeRootByPeriod[_period] != to_bytes32(0) => currentContract.periodToSubmitter[_period] != 0
//     // currentContract.periodToSubmitter[_period] != 0 <=> currentContract._syncCommitteeRootByPeriod[_period] != to_bytes32(0)
//     {
//         preserved with (env e){
//             setup(e);
//         }
//         preserved updateSyncCommittee(EthereumLightClient.HeaderUpdate update, bytes32 nextSyncCommitteePoseidon, EthereumLightClient.Groth16Proof commitmentMappingProof) with (env e){
//             setup(e);
//             require update.nextSyncCommitteeRoot != to_bytes32(0);
//         }
//     }



// ghost mapping(address => uint256) addressesInWhitelist{
//     axiom forall address x. addressesInWhitelist[x] == 0;
// }

// hook Sstore whitelistArray[INDEX uint index]
//     address newVal (address oldVal) {
//     addressesInWhitelist[newVal] = addressesInWhitelist[newVal] + 1;
//     addressesInWhitelist[oldVal] = addressesInWhitelist[oldVal] - 1;
// }

// hook Sstore whitelistArray.length
//     uint newVal (uint oldVal) {
    
// }

// invariant noDuplicatesInWhitelist()
//     (forall address x. addressesInWhitelist[x] == 0) || (forall address x. addressesInWhitelist[x] == 1)
//     {
//         preserved with (env e){
//             setup(e);
//         }
//     }

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
            // requireInvariant isInTheWhiteListIfHasCollateral(_);
        }
        preserved joinRelayerNetwork() with (env e){
            setup(e);
            // here we assume that if there is a relayer in the whitelist, then this relayer has a collateral
            require (exists uint256 index. currentContract.whitelistArray[index] == e.msg.sender) => currentContract.relayerToBalance[e.msg.sender] > 0;
        }
    }

// double polarity issue is there is <=> therefore we splitted this invariant into two
invariant thereIsACollateralIfIsInWhitelist(address relayer) 
    (exists uint256 index. index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == relayer) => currentContract.relayerToBalance[relayer] > 0
    // !(forall uint256 index. (index < currentContract.whitelistArray.length => currentContract.whitelistArray[index] != relayer))
    {
        // we make an assumption that the function caller is never the contract itself, because otherwise it would not change the contract balance
        preserved with (env e){ 
            setup(e);
            requireInvariant noDuplicatesInWhitelist();
            require relayer != currentContract;
            require relayer != 0;
        }
    }

// the problem is that 
// is not true, because the relayer has the balance 
invariant isInTheWhiteListIfHasCollateral(address relayer) 
    // forall address relayer. (currentContract.relayerToBalance[relayer] > 0 => (exists uint256 index. (index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == relayer)))
    // forall address relayer. (currentContract.relayerToBalance[relayer] > 0 => !(forall uint256 index. (index < currentContract.whitelistArray.length => currentContract.whitelistArray[index] != relayer)))
    currentContract.relayerToBalance[relayer] > 0 => (exists uint256 index. (index < currentContract.whitelistArray.length && currentContract.whitelistArray[index] == relayer))
    // !(forall uint256 index. (index < currentContract.whitelistArray.length => currentContract.whitelistArray[index] != relayer))
    {
        // we make an assumption that the function caller is never the contract itself, because otherwise it would not change the contract balance
        preserved with (env e){ 
            setup(e);
            requireInvariant noDuplicatesInWhitelist();
            requireInvariant thereIsACollateralIfIsInWhitelist(relayer);
            requireInvariant zeroAddressCanNotBeInWhitelist();
            require BRIDGE_TIMESLOT_PENALTY() > 0;
            // require relayer != currentContract;
            // require relayer != 0;
        }
    }
