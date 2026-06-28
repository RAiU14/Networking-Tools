# Log Capture

Run command collections against network devices and save the output locally.

## Install

```bash
cd Log_Capture
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Prepare input files

Copy the templates in `Sheets/` and fill them locally:

```bash
cp Sheets/devices.example.csv Sheets/devices.csv
cp Sheets/commands.example.csv Sheets/commands.csv
```

Required device columns:

```text
Hostname, IP Address, Device Type, SSH Username, SSH Password
```

The command file uses the first column as the command list.

## CLI usage

```bash
python command_run.py \
  --devices Sheets/devices.csv \
  --commands Sheets/commands.csv \
  --output-dir outputs
```

## GUI usage

```bash
python gui.py
```

Choose the devices file, command file, and output folder from the interface.

## Safety notes

- Do not commit real device inventories, command output captures, or failure reports.
- Runtime output is written under `outputs/` by default and ignored by Git.
- The app does not print passwords, but your input files contain credentials, so keep them local.
