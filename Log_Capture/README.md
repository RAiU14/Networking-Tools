# Log Capture

Run show-command collections against network devices and save timestamped output locally.

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
Hostname, IP Address, Device Type, SSH Username
```

`SSH Password` is supported in the devices file, but you can leave it blank and use either:

```bash
export NETTOOLS_SSH_PASSWORD="your-password"
```

or:

```bash
python command_run.py --prompt-password ...
```

The command file uses the first column as the command list.

## CLI usage

```bash
python command_run.py \
  --devices Sheets/devices.csv \
  --commands Sheets/commands.csv \
  --output-dir outputs
```

Useful options:

```bash
python command_run.py \
  --devices Sheets/devices.csv \
  --commands Sheets/commands.csv \
  --output-dir outputs \
  --workers 5 \
  --timeout 30 \
  --read-timeout 60 \
  --prompt-password
```

Validate files without connecting to devices:

```bash
python command_run.py \
  --devices Sheets/devices.csv \
  --commands Sheets/commands.csv \
  --dry-run
```

## GUI usage

```bash
python gui.py
```

The GUI guides users through four steps: select the devices file, select the commands file, choose an output folder, and start the run.

## Output

Each run writes:

```text
outputs/device_captures/   command output per device
outputs/reports/           CSV and JSON run summaries
outputs/logs/              runtime logs
```

## Safety notes

- Do not commit real device inventories, command output captures, or failure reports.
- Runtime output is written under `outputs/` by default and ignored by Git.
- Prefer `NETTOOLS_SSH_PASSWORD` or `--prompt-password` instead of storing passwords in spreadsheets.
