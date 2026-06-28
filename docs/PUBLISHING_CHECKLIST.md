# Publishing checklist

Use this before pushing to GitHub or sharing the repository.

## Repository hygiene

- [ ] No `.git/` folder from someone else's/local zip is included in shared archives.
- [ ] `git status --short` only shows intentional source/docs changes.
- [ ] No `__pycache__`, `.pytest_cache`, `.venv`, `node_modules`, or build output.
- [ ] No runtime logs, device captures, failed-device reports, or DB files.
- [ ] No real Excel/CSV inventory files.

## Secret scan

- [ ] Search for `password`, `secret`, `token`, `api_key`, `client_secret`, `Authorization`, and `Bearer`.
- [ ] Search for private IP ranges and internal hostnames.
- [ ] Check `.env`, `.env.*`, `.eox_*`, and key/certificate files are ignored.
- [ ] Rotate any credential that was ever committed or shared.

## Documentation

- [ ] README explains what the project does and how to run each tool.
- [ ] Safety/legal notes are visible before users run scraping or automation.
- [ ] Example inputs use placeholders only.
- [ ] Generated output locations are documented and ignored by Git.

## Suggested first push from this clean package

```bash
git init
git add .
git commit -m "Clean and document networking tools"
git branch -M main
git remote add origin <your-new-repo-url>
git push -u origin main
```

If pushing to an existing repo, copy these cleaned files into a fresh branch and review the diff before merging.
