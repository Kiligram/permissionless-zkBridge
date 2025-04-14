
Unzip auxiliary files
```
apt update
apt install zip -y
for file in *.zip; do unzip "$file"; done
```

Download ptau file (144GB)
```
wget https://storage.googleapis.com/zkevm/ptau/powersOfTau28_hez_final_27.ptau
```


Install rust and circom
```
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


Install nodejs and dependencies
```
cd ~/permissionless-zkBridge
git submodule init
git submodule update
cd circuits
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.37.2/install.sh | bash
source ~/.bashrc
nvm install v14.8.0
node --version
npm install --unsafe-perm
```


```

```