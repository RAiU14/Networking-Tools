# Security guidance

This repository contains network automation tools. Treat all runtime inputs and outputs as sensitive unless proven otherwise.

## Never commit

- Real device inventories.
- SSH usernames or passwords.
- API tokens, client secrets, bearer tokens, private keys, or generated auth files.
- Device command outputs, logs, failed-device reports, database files, or cached vendor data.
- Screenshots or captures that reveal hostnames, IP addresses, serial numbers, usernames, routing, VLANs, or topology.

## Credential handling

- Use local environment variables, password managers, or untracked local files.
- Rotate any credential that was ever stored in a repository, spreadsheet, chat, ticket, email, or shared zip.
- Prefer read-only or least-privilege accounts for automation.
- Avoid shared admin passwords.

## Safe publishing checklist

Before publishing or sharing:

```bash
find . -type f \( -name '*.log' -o -name '*.pyc' -o -name '*.db' \)
grep -RInI -E 'password|secret|token|api[_-]?key|client[_-]?secret|Authorization|Bearer' .
grep -RInI -E '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' .
```

Review matches manually. Localhost/test/example values are fine; real internal values are not.

## Cisco EOX Manager

Cisco EOX Manager is independent and not affiliated with Cisco. Use official Cisco APIs where available and keep scraping as a controlled fallback only. Users are responsible for respecting vendor terms, robots.txt, rate limits, and applicable laws.

Do not bundle generated Cisco lifecycle datasets or cached databases in the public repository. Let each user generate their own local cache.
