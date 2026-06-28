# Repository cleanup report

This report documents what was removed or changed before publishing.

## Removed from the clean package

- `.git/` history and remote metadata from the uploaded archive.
- Python bytecode caches: `__pycache__/`, `*.pyc`.
- Test/runtime caches: `.pytest_cache/`.
- Runtime logs from root, Cisco EOX Manager, and network automation runs.
- Device capture output files containing real internal hostnames/IP addresses and Cisco command output.
- Failure reports containing internal hostnames/IP addresses.
- Local spreadsheet inventory files under `Log_Capture/Sheets/`.

## Sensitive data found

The uploaded repo included local operational artifacts that should not be public:

- A device spreadsheet with SSH credential columns and filled values.
- Command output captures from lab/network devices.
- Logs and failure reports with internal IP addresses, hostnames, and a local workstation path.
- Git remote metadata tied to the original repository URL.

Those files are not included in this cleaned package.

## Safe replacements added

- `Log_Capture/Sheets/devices.example.csv`
- `Log_Capture/Sheets/commands.example.csv`
- `Log_Capture/Sheets/README.md`
- Root `.gitignore` rules that block common local inventory, credential, log, cache, and runtime files.
- Documentation for setup, security, publishing, and contribution workflow.

## Recommended before pushing

Run these checks locally from the repository root:

```bash
git status --short
git add .
git diff --cached --check
git secrets --scan  # optional, if installed
```

Also rotate any SSH password or lab credential that appeared in a committed or shared spreadsheet, even if the public clean package no longer contains it.
