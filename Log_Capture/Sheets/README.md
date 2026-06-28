# Input file templates

Use these templates as the starting point for local inventory files.

- `devices.example.csv` shows the required device columns.
- `commands.example.csv` shows the command-list format.

Do **not** commit real inventory files. Real files can include internal IPs,
hostnames, usernames, and passwords. The root `.gitignore` blocks common local
filenames such as `devices.xlsx`, `devices.csv`, `commands.xlsx`, and
`commands.csv` while keeping the `.example.csv` templates tracked.
