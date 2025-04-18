import argparse
import subprocess
import requests
import json
import os
from datetime import datetime
from web3 import Web3
from eth_account import Account
from web3.exceptions import ContractLogicError
from eth_abi.abi import decode as decode_abi
from eth_utils import remove_0x_prefix

# === CONFIGURATION ===
HEADER_SCRIPT_PATH = "./circuits/verify_header/run.sh"
SYNC_SCRIPT_PATH = "./circuits/verify_syncCommittee/run.sh"
BEACON_API_URL = "http://testing.mainnet.beacon-api.nimbus.team"
JSON_OUTPUT_FILE = "input_data.json"
RPC_URL = "http://127.0.0.1:8545"  # Local Anvil by default
ABI_PATH = "./contracts/out/EthereumLightClient.sol/EthereumLightClient.json"
# CONTRACT_ADDRESS = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
BROADCAST_PATH = "./contracts/broadcast/EthereumLightClient.s.sol/31337/run-latest.json"
PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"

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


def run_script(script_path):
    """Runs a given bash script and returns its output."""
    if not os.path.isfile(script_path):
        print(f"❌ Script not found: {script_path}")
        return
    try:
        result = subprocess.run(["bash", script_path], check=True)
        print("✅ Script executed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Script failed: {e}")


def fetch_and_prepare_block_header_json():
    """Fetches the latest block header and writes it to a JSON file."""
    url = f"{BEACON_API_URL}/eth/v1/beacon/headers/head"
    print(f"📡 Fetching data from {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        header = data.get("data", {}).get("header", {}).get("message", {})

        if not header:
            print("❌ Header data not found in API response.")
            return

        with open(JSON_OUTPUT_FILE, "w") as f:
            json.dump(header, f, indent=4)

        print(f"✅ Header data saved to {JSON_OUTPUT_FILE}")
    except requests.RequestException as e:
        print(f"❌ Error fetching header data: {e}")

def get_eth_balance(address):
    """Gets and prints the ETH balance of a given address."""
    web3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not web3.is_connected():
        print("❌ Could not connect to the RPC endpoint.")
        return

    try:
        checksum_address = web3.to_checksum_address(address)
        balance_wei = web3.eth.get_balance(checksum_address)
        balance_eth = web3.from_wei(balance_wei, 'ether')
        print(f"💰 Balance of {checksum_address} on {RPC_URL}: {balance_eth} ETH")
    except Exception as e:
        print(f"❌ Failed to fetch balance: {e}")


def load_contract(w3, abi_path, address):
    with open(abi_path, "r") as f:
        abi = json.load(f)["abi"]
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)

# === CALL FUNCTION ===
def get_sync_committee_root_by_period(period: int):
    web3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not web3.is_connected():
        print("❌ Could not connect to RPC.")
        return None

    contract = load_contract(web3, ABI_PATH, load_contract_address())
    # abi = load_abi(ABI_PATH)
    # contract = web3.eth.contract(address=Web3.to_checksum_address(load_contract_address()), abi=abi)

    try:
        result = contract.functions.syncCommitteeRootByPeriod(period).call()
        print(f"✅ syncCommitteeRootByPeriod({period}) = {Web3.to_hex(result)}")
        return result
    except Exception as e:
        print(f"❌ Error calling contract: {e}")
        return None


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


def call_update_header():
    # Initialize web3 and signer
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    acct = Account.from_key(PRIVATE_KEY)

    # Load input data
    with open("./contracts/test/data/lightClientUpdate/goerli/5097760.json", "r") as f:
        data = json.load(f)

    # Load contract
    contract = load_contract(w3, ABI_PATH, load_contract_address())

    header_update = parse_header_update(data)

    # print(f"📦 Header update: {header_update}")

    # Send the transaction
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = contract.functions.updateHeader(header_update).build_transaction({
        "chainId": w3.eth.chain_id,
        "gas": 5_000_000,
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
    })

    send_tx(w3, tx)


def call_update_sync_committee():
    # Initialize web3 and signer
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    acct = Account.from_key(PRIVATE_KEY)

    # Load input data
    with open("./contracts/test/data/ssz2Poseidon/goerli/5097760.json", "r") as f:
        data = json.load(f)

    # Load contract
    contract = load_contract(w3, ABI_PATH, load_contract_address())

    header_update = parse_header_update(data)
    next_sync_committee_poseidon = Web3.to_bytes(hexstr=data["nextSyncCommitteePoseidon"])

    commitment_mapping_proof = {
        "a": data["ssz2PoseidonProof"]["a"],
        "b": data["ssz2PoseidonProof"]["b"],
        "c": data["ssz2PoseidonProof"]["c"]
    }

    # print(f"📦 Next sync committee poseidon: {next_sync_committee_poseidon}")
    # print(data["nextSyncCommitteePoseidon"])
    # print(f"📦 Commitment mapping proof: {commitment_mapping_proof}")

    # Send the transaction
    nonce = w3.eth.get_transaction_count(acct.address)
    tx = contract.functions.updateSyncCommittee(header_update, next_sync_committee_poseidon, commitment_mapping_proof).build_transaction({
        "chainId": w3.eth.chain_id,
        "gas": 5_000_000,
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
    })

    send_tx(w3, tx)


def send_tx(w3, tx):
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    print(f"🚀 Transaction sent: {w3.to_hex(tx_hash)}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"✅ Transaction mined in block {receipt.blockNumber}")

    if receipt.status == 1:
        print("✅ Transaction succeeded!")
    else:
        print("❌ Transaction reverted.")
        debug_trace = w3.provider.make_request("debug_traceTransaction", [w3.to_hex(tx_hash)])
        decode_revert_reason(debug_trace)



# === MAIN ===

def main():
    parser = argparse.ArgumentParser(description="zkBridge Proof Submission CLI")
    parser.add_argument("-s", "--submit", help='Run submission scripts: "header" or "sync"', choices=["header", "sync"])
    parser.add_argument("--prepare-json", action="store_true", help="Fetch block header and write input JSON")
    parser.add_argument("-b", "--balance", type=str, help="Check ETH balance of an address")
    parser.add_argument("--get-sync-root", type=int, metavar="PERIOD", help="Call syncCommitteeRootByPeriod(period)")

    args = parser.parse_args()

    if args.submit == "header":
        call_update_header()
        # run_script(HEADER_SCRIPT_PATH)
    elif args.submit == "sync":
        call_update_sync_committee()
        # run_script(SYNC_SCRIPT_PATH)
    elif args.prepare_json:
        fetch_and_prepare_block_header_json()
    elif args.balance:
        get_eth_balance(args.balance)
    elif args.get_sync_root:
        get_sync_committee_root_by_period(args.get_sync_root)
    else:
        parser.print_help()
    
if __name__ == "__main__":
    main()
