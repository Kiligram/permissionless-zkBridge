methods
{
    // // When a function is not using the environment (e.g., `msg.sender`), it can be
    // // declared as `envfree`
    // function joinRelayerNetwork(address) external payable;
    // function allowance(address,address) external returns(uint) envfree;
    function COLLATERAL() external returns (uint256) envfree;

    /**
     * The following functions are used to verify the zk-SNARK proofs. For certora it is impossible to assume
     * all possible proofs, so we use the `NONDET` summarization to assume that the proof verification
     * functions can return any bool value, no matter the input. Without this, the rules would be considered vacuous.
    */
    function HeaderBLSVerifier.verifySignatureProof(uint[2] memory, uint[2][2] memory, uint[2] memory, uint[34] memory) internal returns (bool) => NONDET;
    function SyncCommitteeRootToPoseidonVerifier.verifyCommitmentMappingProof(uint[2] memory, uint[2][2] memory, uint[2] memory, uint[33] memory) internal returns (bool) => NONDET;
}

rule joiningRelayerMustIncreaseContractBalance(address relayer){
    mathint contract_balance_before = nativeBalances[currentContract];

    env e;
    // require(e.msg.value == COLLATERAL()); // we do not need this because certora ignores reverted transactions, since such a state is not reachable and there is no reason to check it
    require(e.msg.sender != currentContract);
    joinRelayerNetwork(e, relayer);

    mathint contract_balance_after = nativeBalances[currentContract];

    assert contract_balance_after == contract_balance_before + COLLATERAL(),
        "Contract balance must increase after relayer joins";
}

// rule withdrawIncentiveMustLeaveCollateral(){
//     env e;
//     require(e.msg.sender != currentContract);

//     mathint contract_balance_before = nativeBalances[currentContract];
//     withdrawIncentive(e);
//     mathint contract_balance_after = nativeBalances[currentContract];

//     assert contract_balance_after - contract_balance_before == COLLATERAL(),

// }

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
            f.selector == sig:joinRelayerNetwork(address).selector ||
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

/// make sure that the contract balance is never less the total collateral balance
invariant totalCollateralEqualsContractBalance()
    nativeBalances[currentContract] == totalCollateralBalance
    {
        // we make an assumption that the function caller is never the contract itself, because otherwise it would not change the contract balance
        preserved with (env e){ 
            // require (e.msg.sender == e.tx.origin); // just does not work, this is the certora limitation
            // require nativeBalances[currentContract] == 0;
            require e.msg.sender != currentContract;
        }
        // preserved constructor(
        //             bytes32 genesisValidatorsRoot,
        //             uint256 genesisTime,
        //             uint256 secondsPerSlot,
        //             bytes4 forkVersion,
        //             uint256 startSyncCommitteePeriod,
        //             bytes32 startSyncCommitteeRoot,
        //             bytes32 startSyncCommitteePoseidon
        //           ) with (env e) {
        //     require nativeBalances[currentContract] == 0; 
        // }
    }


// hook Sstore funds[KEY address user] uint256 newBalance (uint256 oldBalance) STORAGE {
//   havoc sumOfAllFunds assuming sumOfAllFunds@new() == sumOfAllFunds@old() + newBalance - oldBalance;
// }



// ghost mathint numVoted {
//     // No votes at start
//     init_state axiom numVoted == 0;
// }

// hook Sstore _hasVoted[KEY address voter]
//     bool newVal (bool oldVal) {
//     numVoted = numVoted + 1;
// }

// /// @title Total voted intergrity
// invariant sumResultsEqualsTotalVotes()
//      nativeBalances[currentContract] == contractBalance;

// /// @title If `approve` changes a holder's allowance, then it was called by the holder
// rule onlyHolderCanChangeAllowance(address holder, address spender, method f) {

//     // The allowance before the method was called
//     mathint allowance_before = allowance(holder, spender);

//     env e;
//     calldataarg args;  // Arguments for the method f
//     f(e, args);                        

//     // The allowance after the method was called
//     mathint allowance_after = allowance(holder, spender);

//     assert allowance_after > allowance_before => e.msg.sender == holder,
//         "only the sender can change its own allowance";

//     // Assert that if the allowance changed then `approve` or `increaseAllowance` was called.
//     assert (
//         allowance_after > allowance_before =>
//         (
//             f.selector == sig:approve(address, uint).selector ||
//             f.selector == sig:increaseAllowance(address, uint).selector
//         )
//     ),
//     "only approve and increaseAllowance can increase allowances";
// }