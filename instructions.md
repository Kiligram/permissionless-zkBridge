```
anvil --code-size-limit 999999
```

```
forge script script/EthereumLightClient.s.sol:DeployLightClient \
  --rpc-url http://127.0.0.1:8545 \
  --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80 \
  --broadcast
```


```
export CERTORAKEY=
sudo apt install openjdk-11-jre-headless
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
solc-select install 0.8.14
solc-select use 0.8.14

cd contracts/
certoraRun EthereumLightClient.conf


```