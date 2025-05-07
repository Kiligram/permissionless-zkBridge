# Tusima zkBridge with incentive mechanism and CLI


For more information about Tusima zkBridge refer  [here](https://tusima.gitbook.io/zkbridge/) and to [original README](./README_tusima_original.md).

This repository is composed of three main parts, [contracts](./contracts/README.md), [circuits](./circuits/README.md) and [CLI](./cli.py). In [auxiliary](./auxiliary/) directory you can find the necessary binaries for running the circuits. Certora verification files `EthereumLightClient.spec` (specification) and `EthereumLightClient.conf` are located under `./contracts` directory. The short overview of the project structure is as follows (it contains the files which you likely want to see or modify):

```
.
├── auxiliary
├── circuits
├── contracts
│   ├── src
│   │   └── ethereum
│   │       └── EthereumLightClient.sol
│   ├── certora
│   │   └── specs
│   │       └── EthereumLightClient.spec
│   ├── .env
│   └── EthereumLightClient.conf
└── cli.py
```
# Requirements & dependencies
If you only want to test the whole solution as a concept, you do not needed to run the circuits nor certora prover. For testing purposes we already pre-prepared the data and proofs. You can find them in the `./test_data` directory.
## Requirements
- 32 core CPU, 256GB RAM and 500GB free space (if running the circuits)
- 4 core CPU, 16GB RAM and 20GB free disk space (if running without circuits, for testing purposes)

## Pre-requisites
- `Python >= v3.8.16`

## Contracts: dependencies
1. Install submodules:
```
git submodule init
git submodule update
```

2. Install Foundry
```bash
curl -L https://foundry.paradigm.xyz | bash
```


## CLI: dependencies
1. Create a virtual environment and install dependencies:

```bash
cd ~/permissionless-zkBridge
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Circuits: dependencies (optional)

> Skip this section if you only want to test the whole solution as a concept. Otherwise, you need extensive computational resources.

> Normally, you would also need to build patched node.js, what is a time and computation consuming task. However, we provide precompiled binary in `./auxiliary` directory. 

1. Unzip auxiliary files
```bash
cd ./auxiliary
apt update
apt install zip -y
for file in *.zip; do unzip "$file"; done
```

2. Install rust and Circom v2.0.3 
```bash
cd ~
apt update
apt install build-essential -y
apt install cmake -y
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh
. "$HOME/.cargo/env"
wget https://github.com/iden3/circom/archive/refs/tags/v2.0.3.zip
unzip v2.0.3.zip
cd circom-2.0.3
cargo build --release
cargo install --path circom
circom --help
```

3. Install nodejs and dependencies
```bash
cd ~/permissionless-zkBridge/circuits
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.37.2/install.sh | bash
source ~/.bashrc
nvm install v14.8.0
nvm use v14.8.0
node --version
npm install --unsafe-perm
```

4. Download ptau file (144GB)
```bash
wget https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_27.ptau
```

## Certora: dependencies (optional)
> If you want to run Certora verification, you need to register and get a key first.

```bash
cd ~/permissionless-zkBridge
export CERTORAKEY=<YOUR_CERTORA_KEY>
sudo apt install openjdk-11-jre-headless
pip3 install solc-select
solc-select install 0.8.29
solc-select use 0.8.29
```

# Getting started

### 1. Prepare the input data for circuits and contract (optional)

> For testing purposes you can skip this step and there will be used prepared data and proofs located in the `./test_date` directory.

1. In order to submit the block header or sync committee you have to fetch the data from the Ethereum beacon node, preprocess them and save in the JSON format. 

2. Modify the `./circuits/verify_header/run.sh` accordingly and run them:

```bash
cd ~/permissionless-zkBridge/circuits/verify_header
SLOT=<SLOT_FOR_WHICH_YOU_PREPARED_DATA> bash run.sh
```

Or if you want to run the sync committee circuit:
```bash
cd ~/permissionless-zkBridge/circuits/verify_syncCommittee
PERIOD=<PERIOD_FOR_WHICH_YOU_PREPARED_DATA> bash run.sh
```

### 2. Deploy the smart contract
1. (Optional) Modify the `./contracts/.env` file with your private key, light client setup and all the other variables. For testing purposes you can skip this step as there already are default values.

2. In a separate terminal start the local Ethereum node if you want to deploy the contract locally. We recommend using Anvil, which goes with Foundry:
```bash
anvil --code-size-limit 999999
```

3. Deploy the smart contract. In this command there is used anvil as a local Ethereum node. You can also use any other EVM compatible RPC node and private key.

```bash
cd ~/permissionless-zkBridge/contracts
forge script script/EthereumLightClient.s.sol:DeployLightClient \
    --rpc-url http://127.0.0.1:8545 \
    --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
    --broadcast
```

4. Now you can run the CLI and interact with the contract.
```bash
cd ~/permissionless-zkBridge
python3 ./cli.py --help
```

```
usage: cli.py [-h] [--submit-header SLOT] [--submit-sync SLOT] [-b [ADDRESS]] [--join-relayer] [--exit-relayer] [--withdraw-incentive]       
              [--get-proposer] [--get-sync-root PERIOD] [--sync-root-to-poseidon ROOT] [--execution-state-root SLOT]

zkBridge CLI

options:
  -h, --help            show this help message and exit
  --submit-header SLOT  Submit a header update, for testing purposes there are the following pre-prepared slots: 7295584, 7295904, 7297568,  
                        7299712, 7299968. Submit these slots in this order, otherwise it will revert, what is expected behavior. If you get a
                        sync committee error, you need to submit the new sync committee for new period. This will happen right after 7297568 
                        slot.
  --submit-sync SLOT    Submit sync committee update, for testing purposes there is the following pre-prepared slot: 7298976
  -b [ADDRESS], --balance [ADDRESS]
                        Check ETH balance of an address (defaults to your account)
  --join-relayer        Join the relayer network
  --exit-relayer        Exit the relayer network
  --withdraw-incentive  Withdraw incentive from the contract
  --get-proposer        Get the current proposer
  --get-sync-root PERIOD
                        Purchase the root for a given period.
  --sync-root-to-poseidon ROOT
                        Purchase the sync committee root calculated with Poseidon hash corresponding to the given sync committee root.
  --execution-state-root SLOT
                        Purchase the execution state root for a given slot.
```

### 3. Formal verification with Certora (optional)

```bash
cd ~/permissionless-zkBridge/contracts
certoraRun EthereumLightClient.conf
```

Otherwise the mutation testing reports are available here:

| **Batch** | **Report URL** |
|----------:|----------------|
| 1 | [https://mutation-testing.certora.com/?id=1ccbea5f-42b4-48e6-94e5-748047d11db1&anonymousKey=4da52303-d33f-423e-b8a1-b3505567495d](https://mutation-testing.certora.com/?id=1ccbea5f-42b4-48e6-94e5-748047d11db1&anonymousKey=4da52303-d33f-423e-b8a1-b3505567495d) |
| 2 | [https://mutation-testing.certora.com/?id=14d57c93-e84d-4b68-b24a-511f0a22d080&anonymousKey=4ae7397b-8f7e-4012-8fd3-0ac2be28551b](https://mutation-testing.certora.com/?id=14d57c93-e84d-4b68-b24a-511f0a22d080&anonymousKey=4ae7397b-8f7e-4012-8fd3-0ac2be28551b) |
| 3 | [https://mutation-testing.certora.com/?id=fc0be51e-1a9b-4fbb-83e6-aa49bcb182fc&anonymousKey=ef5501c6-f2e1-4f5e-b99e-224dac33564f](https://mutation-testing.certora.com/?id=fc0be51e-1a9b-4fbb-83e6-aa49bcb182fc&anonymousKey=ef5501c6-f2e1-4f5e-b99e-224dac33564f) |
| 4 | [https://mutation-testing.certora.com/?id=afa99745-7e24-4f1b-afed-e97b62ec0411&anonymousKey=14722e0d-94ee-4c40-b04d-a91567d2d8eb](https://mutation-testing.certora.com/?id=afa99745-7e24-4f1b-afed-e97b62ec0411&anonymousKey=14722e0d-94ee-4c40-b04d-a91567d2d8eb) |
