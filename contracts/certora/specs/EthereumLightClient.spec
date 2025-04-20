methods
{
    // // When a function is not using the environment (e.g., `msg.sender`), it can be
    // // declared as `envfree`
    // function balanceOf(address) external returns (uint) envfree;
    // function allowance(address,address) external returns(uint) envfree;
    // function totalSupply() external returns (uint) envfree;
}


rule onlyIncentiveCanDecreaseContractBalance(method f) {
    mathint contract_balance_before = nativeBalances[currentContract];

    env e;
    calldataarg args;  // Arguments for the method f
    f(e, args);  

    mathint contract_balance_after = nativeBalances[currentContract];

        // Assert that if the allowance changed then `approve` or `increaseAllowance` was called.
    assert (
        contract_balance_before != contract_balance_after =>
        (
            f.selector == sig:joinRelayerNetwork(address).selector ||
            f.selector == sig:exitRelayerNetwork().selector ||
            f.selector == sig:withdrawIncentive().selector
        )
    ),
    "only joinRelayerNetwork, exitRelayerNetwork and withdrawIncentive can change the contract balance";
}


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