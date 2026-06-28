# Alive Checks

Small utility for checking whether a network device is reachable.

## Install

```bash
cd Alive_Checks
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Direct ping

```bash
python alive.py 192.0.2.10
```

## Jump-host ping

Do not hardcode jump-host credentials in this repository. Export them locally:

```bash
export JUMP_HOST_DEVICE_TYPE=linux
export JUMP_HOST_IP=192.0.2.5
export JUMP_HOST_USERNAME=your_username
export JUMP_HOST_PASSWORD=your_password
python alive.py 192.0.2.10 --jump-host
```

Runtime logs are written to `Alive_Checks/logs/` and are ignored by Git.
