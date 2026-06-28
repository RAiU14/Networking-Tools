# Contributing

## Development rules

- Keep real network data out of the repository.
- Add examples with placeholder IPs from documentation ranges such as `192.0.2.0/24`.
- Do not add generated logs, captures, local spreadsheets, DB files, or caches.
- Prefer small, focused commits.
- Update documentation when changing CLI arguments, environment variables, routes, or folder layout.

## Basic checks

```bash
python -m compileall Alive_Checks Log_Capture Cisco_EOX_Manager/backend Cisco_EOX_Manager/tools
cd Cisco_EOX_Manager && pytest -q
cd Cisco_EOX_Manager/front_end && npm install && npm run build
```

The Cisco EOX frontend build requires Node.js and npm. Backend tests require Python dependencies from `Cisco_EOX_Manager/requirements-dev.txt`.
