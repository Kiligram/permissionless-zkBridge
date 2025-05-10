import argparse
import json
from web3 import Web3
from eth_account import Account
from eth_abi.abi import decode as decode_abi
from eth_utils import remove_0x_prefix

# === CONFIGURATION ===
RPC_URL = "http://127.0.0.1:8545"  # Local Anvil by default
ABI_PATH = "./contracts/out/EthereumLightClient.sol/EthereumLightClient.json"
BROADCAST_PATH = "./contracts/broadcast/EthereumLightClient.s.sol/31337/run-latest.json"

# use 'cast rpc evm_mine' to mine a block in anvil if needed to test the inactivity of relayer
# this CLI is only for testing purposes, so use a testnet address
PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

GAS_BUFFER_MULTIPLIER = 1.2

web3 = Web3(Web3.HTTPProvider(RPC_URL))
acct = Account.from_key(PRIVATE_KEY)
if not web3.is_connected():
    print("❌ Could not connect to the RPC endpoint.")
    exit(1)

# === FUNCTIONS ===

def load_contract_address():
    """Loads the deployed contract address from broadcast JSON if using localhost RPC."""
    if "127.0.0.1" in RPC_URL or "localhost" in RPC_URL:
        try:
            with open(BROADCAST_PATH, "r") as f:
                data = json.load(f)
                txs = data.get("transactions", [])
                for tx in txs:
                    if tx.get("contractName") == "EthereumLightClient":
                        return tx.get("contractAddress") or tx.get("receipt", {}).get("contractAddress")
                # fallback: return first contractAddress found
                if txs:
                    return txs[0].get("contractAddress") or txs[0].get("receipt", {}).get("contractAddress")
        except Exception as e:
            print(f"❌ Could not load contract address from broadcast JSON: {e}")
    else:
        return CONTRACT_ADDRESS
    
    return None


def get_eth_balance(address):
    """Gets and prints the ETH balance of a given address."""

    try:
        checksum_address = web3.to_checksum_address(address)
        balance_wei = web3.eth.get_balance(checksum_address)
        balance_eth = web3.from_wei(balance_wei, 'ether')
        print(f"💰 Balance of {checksum_address} on {RPC_URL}: {balance_eth} ETH")
    except Exception as e:
        print(f"❌ Failed to fetch balance: {e}")


def load_contract(web3, abi_path, address):
    with open(abi_path, "r") as f:
        abi = json.load(f)["abi"]
    return web3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


contract = load_contract(web3, ABI_PATH, load_contract_address())



def decode_revert_reason(debug_trace_response):
    try:
        return_value = debug_trace_response['result'].get('returnValue', '')
        if not return_value:
            return "⚠️ No revert reason found in trace."

        # Remove '0x' if present and strip the first 4 bytes (Error(string) selector)
        revert_data = remove_0x_prefix(return_value)[8:]
        revert_bytes = bytes.fromhex(revert_data)

        # Decode the revert reason
        decoded = decode_abi(["string"], revert_bytes)
        print(f"❌ Revert reason: {decoded[0]}")
    except Exception as e:
        print(f"⚠️ Failed to decode revert reason: {e}")


# Prepare nested structs for header
def to_bytes32_list(lst):
    return [Web3.to_bytes(hexstr=item) for item in lst]

# Prepare nested structs for header
def prepare_header(header):
    return {
        "slot": header["slot"],
        "proposerIndex": header["proposerIndex"],
        "parentRoot": Web3.to_bytes(hexstr=header["parentRoot"]),
        "stateRoot": Web3.to_bytes(hexstr=header["stateRoot"]),
        "bodyRoot": Web3.to_bytes(hexstr=header["bodyRoot"])
    }

def parse_header_update(data):
    header_update = {
        "attestedHeader": prepare_header(data["attestedHeader"]),
        "finalizedHeader": prepare_header(data["finalizedHeader"]),
        "finalityBranch": to_bytes32_list(data["finalityBranch"]),
        "nextSyncCommitteeRoot": Web3.to_bytes(hexstr=data["nextSyncCommitteeRoot"]) if data["nextSyncCommitteeRoot"] else b"\x00" * 32,
        "nextSyncCommitteeBranch": to_bytes32_list(data["nextSyncCommitteeBranch"]),
        "executionStateRoot": Web3.to_bytes(hexstr=data["executionStateRoot"]),
        "executionStateRootBranch": to_bytes32_list(data["executionStateRootBranch"]),
        "blockNumber": data["blockNumber"],
        "blockNumberBranch": to_bytes32_list(data["blockNumberBranch"]),
        "signature": {
            "participation": data["signature"]["participation"],
            "proof": {
                "a": data["signature"]["proof"]["a"],
                "b": data["signature"]["proof"]["b"],
                "c": data["signature"]["proof"]["c"],
            }
        }
    }

    return header_update


def load_json(path: str):
    """
    Loads a JSON file from the given path and returns its content as a dictionary.

    Args:
        path (str): The file path to the JSON file.

    Returns:
        dict or None: Parsed JSON data if successful, None otherwise.
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File '{path}' not found.")
    except json.JSONDecodeError as e:
        print(f"❌ Error: Failed to parse JSON file '{path}': {e}")
    exit(1)


def call_update_header(slot: str):
    data = load_json(f"./test_data/header/{slot}.json")

    header_update = parse_header_update(data)

    # Estimate gas
    estimated_gas = contract.functions.updateHeader(header_update).estimate_gas({
        "from": acct.address
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Send the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.updateHeader(header_update).build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
    })

    send_tx(web3, tx, estimated_gas)


def call_update_sync_committee(slot: str):
    data = load_json(f"./test_data/syncCommittee/{slot}.json")

    header_update = parse_header_update(data)
    next_sync_committee_poseidon = Web3.to_bytes(hexstr=data["nextSyncCommitteePoseidon"])

    commitment_mapping_proof = {
        "a": data["ssz2PoseidonProof"]["a"],
        "b": data["ssz2PoseidonProof"]["b"],
        "c": data["ssz2PoseidonProof"]["c"]
    }

    # Estimate gas
    estimated_gas = contract.functions.updateSyncCommittee(
        header_update, next_sync_committee_poseidon, commitment_mapping_proof
    ).estimate_gas({
        "from": acct.address
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Send the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.updateSyncCommittee(
        header_update, next_sync_committee_poseidon, commitment_mapping_proof
    ).build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
    })

    send_tx(web3, tx, estimated_gas)


def send_tx(web3, tx, estimated_gas, get_return_value=False):
    # Get balance before transaction
    balance_before = web3.eth.get_balance(acct.address)

    signed_tx = web3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)

    print(f"🚀 Transaction sent: {web3.to_hex(tx_hash)}")
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"✅ Transaction mined in block {receipt.blockNumber}")

    # Retrieve gas used and calculate ETH spent
    gas_used = receipt.gasUsed
    gas_price = tx["gasPrice"]
    eth_spent = web3.from_wei(gas_used * gas_price, "ether")

    # Get balance after transaction
    balance_after = web3.eth.get_balance(acct.address)

    print(f"⛽ Gas estimated: {estimated_gas} | Actually used: {gas_used} ({eth_spent} ETH)")

    balance_diff = balance_after - balance_before
    sign = "+" if balance_diff >= 0 else "-"
    print(f"💰 Balance before: {web3.from_wei(balance_before, 'ether')} ETH | After: {web3.from_wei(balance_after, 'ether')} ETH | Diff: {sign}{web3.from_wei(abs(balance_diff), 'ether')} ETH")

    if receipt.status == 1:
        print("✅ Transaction succeeded!")
        if get_return_value:
            try:
                # Attempt to fetch the return value of the called function
                call_tx = {
                    "to": tx["to"],
                    "from": acct.address,  # must include
                    "data": tx["data"],  # contract method calldata
                    "value": tx.get("value", 0)  # optional if not payable
                }
                return_value = web3.eth.call(call_tx, block_identifier=receipt.blockNumber)
                if return_value:
                    return return_value
            except Exception as e:
                print(f"⚠️ Failed to fetch return value: {e}")
                return False
        return True
    else:
        print("❌ Transaction reverted.")
        debug_trace = web3.provider.make_request("debug_traceTransaction", [web3.to_hex(tx_hash)])
        decode_revert_reason(debug_trace)
        return False


def call_join_relayer_network():
    """Calls the joinRelayerNetwork function in the smart contract with the required collateral."""

    # Read COLLATERAL value from contract
    collateral = contract.functions.COLLATERAL().call()

    # Estimate gas
    estimated_gas = contract.functions.joinRelayerNetwork().estimate_gas({
        "from": acct.address,
        "value": collateral,
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Build the transaction with collateral value
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.joinRelayerNetwork().build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
        "value": collateral,  # Send the collateral as ETH
    })

    # Send the transaction
    if send_tx(web3, tx, estimated_gas):
        print(f"✅ Joined relayer {acct.address}")


def call_exit_relayer_network():
    """Calls the exitRelayerNetwork function in the smart contract."""

    # Estimate gas
    estimated_gas = contract.functions.exitRelayerNetwork().estimate_gas({
        "from": acct.address
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Build the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.exitRelayerNetwork().build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
    })

    # Send the transaction
    send_tx(web3, tx, estimated_gas)


def call_withdraw_incentive():
    """Calls the withdrawIncentive function in the smart contract."""

    # Estimate gas
    estimated_gas = contract.functions.withdrawIncentive().estimate_gas({
        "from": acct.address
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Build the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.withdrawIncentive().build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
    })

    # Send the transaction
    send_tx(web3, tx, estimated_gas)


def get_current_proposer():
    """Fetches the current proposer from the smart contract."""
    try:
        current_proposer = contract.functions.currentProposer().call()
        print(f"✅ Current proposer: {current_proposer}")
        return current_proposer
    except Exception as e:
        print(f"❌ Error fetching current proposer: {e}")
        return None


def get_sync_committee_root_by_period(period: int):
    """Calls the syncCommitteeRootByPeriod function in the smart contract."""
    # Fetch the required fee
    sync_committee_root_price = contract.functions.SYNC_COMMITTEE_ROOT_PRICE().call()

    # Estimate gas
    estimated_gas = contract.functions.syncCommitteeRootByPeriod(period).estimate_gas({
        "from": acct.address,
        "value": sync_committee_root_price,
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Build the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.syncCommitteeRootByPeriod(period).build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
        "value": sync_committee_root_price,  # Send the required fee
    })

    # Send the transaction
    result = send_tx(web3, tx, estimated_gas, get_return_value=True)
    if result:
        print(f"✅ Sync Committee Root for period {period}: 0x{result.hex()}")
    else:
        print(f"❌ Failed to call fetch the return value")


def get_sync_committee_root_to_poseidon(root: str):
    """Calls the syncCommitteeRootToPoseidon function in the smart contract and prints the result."""
    # Fetch the required fee
    sync_committee_root_price = contract.functions.SYNC_COMMITTEE_ROOT_PRICE().call()

    # Estimate gas
    estimated_gas = contract.functions.syncCommitteeRootToPoseidon(Web3.to_bytes(hexstr=root)).estimate_gas({
        "from": acct.address,
        "value": sync_committee_root_price,
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Build the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.syncCommitteeRootToPoseidon(Web3.to_bytes(hexstr=root)).build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
        "value": sync_committee_root_price,  # Send the required fee
    })

    # Send the transaction
    result = send_tx(web3, tx, estimated_gas, get_return_value=True)
    if result:
        print(f"✅ Sync Committee Root to Poseidon for root {root}: 0x{result.hex()}")
    else:
        print(f"❌ Failed to call fetch the return value")

def get_execution_state_root(slot: int):
    """Calls the executionStateRoot function in the smart contract and prints the result."""

    # Fetch the required fee
    execution_state_root_price = contract.functions.EXECUTION_STATE_ROOT_PRICE().call()

    # Estimate gas
    estimated_gas = contract.functions.executionStateRoot(slot).estimate_gas({
        "from": acct.address,
        "value": execution_state_root_price,
    })
    gas_limit = int(estimated_gas * GAS_BUFFER_MULTIPLIER)

    # Build the transaction
    nonce = web3.eth.get_transaction_count(acct.address)
    tx = contract.functions.executionStateRoot(slot).build_transaction({
        "chainId": web3.eth.chain_id,
        "gas": gas_limit,
        "gasPrice": web3.eth.gas_price,
        "nonce": nonce,
        "value": execution_state_root_price,  # Send the required fee
    })

    # Send the transaction
    result = send_tx(web3, tx, estimated_gas, get_return_value=True)
    if result:
        print(f"✅ Execution State Root for slot {slot}: 0x{result.hex()}")
    else:
        print(f"❌ Failed to call fetch the return value")


# === MAIN ===

def main():
    parser = argparse.ArgumentParser(description="zkBridge CLI")
    parser.add_argument("--submit-header", type=str, metavar="SLOT", help='Submit a header update, for testing purposes there are the following pre-prepared slots: 7295584, 7295904, 7297568, 7299712, 7299968. Submit these slots in this order, otherwise it will revert, what is expected behavior. If you get a sync committee error, you need to submit the new sync committee for new period. This will happen right after 7297568 slot.') 
    parser.add_argument("--submit-sync", type=str, metavar="SLOT", help='Submit sync committee update, for testing purposes there is the following pre-prepared slot: 7298976')
    parser.add_argument("-b", "--balance", nargs="?", const=acct.address, type=str, metavar="ADDRESS", help="Check ETH balance of an address (defaults to your account)")
    
    parser.add_argument("--join-relayer", action="store_true", help="Join the relayer network")
    parser.add_argument("--exit-relayer", action="store_true", help="Exit the relayer network")
    parser.add_argument("--withdraw-incentive", action="store_true", help="Withdraw incentive from the contract")

    parser.add_argument("--get-proposer", action="store_true", help="Get the current proposer")
    parser.add_argument("--get-sync-root", type=int, metavar="PERIOD", help="Purchase the root for a given period.")
    parser.add_argument("--sync-root-to-poseidon", type=str, metavar="ROOT", help="Purchase the sync committee root calculated with Poseidon hash corresponding to the given sync committee root.")
    parser.add_argument("--execution-state-root", type=int, metavar="SLOT", help="Purchase the execution state root for a given slot.")

    args = parser.parse_args()

    if args.submit_header:
        call_update_header(args.submit_header)
    elif args.submit_sync:
        call_update_sync_committee(args.submit_sync)
    elif args.balance:
        get_eth_balance(args.balance)
    elif args.get_sync_root:
        get_sync_committee_root_by_period(args.get_sync_root)
    elif args.join_relayer:
        call_join_relayer_network()
    elif args.exit_relayer:
        call_exit_relayer_network()
    elif args.withdraw_incentive:
        call_withdraw_incentive()
    elif args.get_proposer:
        get_current_proposer()
    elif args.sync_root_to_poseidon:
        get_sync_committee_root_to_poseidon(args.sync_root_to_poseidon)
    elif args.execution_state_root:
        get_execution_state_root(args.execution_state_root)
    else:
        parser.print_help()
    
if __name__ == "__main__":
    main()
