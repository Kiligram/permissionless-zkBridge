
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
apt update
apt install build-essential
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh
. "$HOME/.cargo/env"
git clone https://github.com/iden3/circom.git
cd circom
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
npm install 
```


```

```