methods
{
    // // When a function is not using the environment (e.g., `msg.sender`), it can be
    // // declared as `envfree`
    // function joinRelayerNetwork(address) external payable;
    // function allowance(address,address) external returns(uint) envfree;
    function COLLATERAL() external returns (uint256) envfree;
    function BRIDGE_BLOCK_PROPOSAL_TIMESLOT() external returns (uint256) envfree;
    function SYNC_COMMITTEE_ROOT_PRICE() external returns (uint256) envfree;
    function BRIDGE_TIMESLOT_PENALTY() external returns (uint256) envfree;

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
    // require(e.msg.value == COLLATERAL()); // we do not need this because certora ignores reverted transactions, since such a state is not reachable and there is no reason to check it
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

// relayerToBalance[periodToSubmitter[_period]] += msg.value;
// rule syncCommitteeRootByPeriodUnitTest(uint256 _period){
//     env e;
//     setup(e);
//     // require();

//     mathint relayer_incentive_before = currentContract.relayerToIncentive[currentContract.periodToSubmitter[_period]];
//     mathint relayer_collateral_before = currentContract.relayerToBalance[currentContract.periodToSubmitter[_period]];
//     syncCommitteeRootByPeriod(e, _period);
//     mathint relayer_address = currentContract.periodToSubmitter[_period];
//     mathint relayer_incentive_after = currentContract.relayerToIncentive[relayer_address];
//     mathint relayer_collateral_after = currentContract.relayerToBalance[relayer_address];

//     assert relayer_collateral_before == COLLATERAL() => relayer_incentive_after == relayer_incentive_before + SYNC_COMMITTEE_ROOT_PRICE(),
//         "Relayer's incentive balance must increase by the sync committee root price";

//     uint256 excess = 

//     assert relayer_collateral_before < COLLATERAL() => relayer_collateral_after == relayer_collateral_before
// }


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
//     if (selector == sig:joinRelayerNetwork().selector) {
//         addressesInWhitelist[newVal] = addressesInWhitelist[newVal] + 1;
//     }
//     else {
//         addressesInWhitelist[oldVal] = addressesInWhitelist[oldVal] - 1;
//         addressesInWhitelist[newVal] = addressesInWhitelist[newVal] + 1;
//     }
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
