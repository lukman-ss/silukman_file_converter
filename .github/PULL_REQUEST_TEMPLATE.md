## Summary

-

## Validation

- [ ] `python -m compileall -q app tests tools scripts`
- [ ] `python -m pytest -q`
- [ ] Production QA or targeted QA evidence is attached when release behavior changes

## Safety

- [ ] No generated artifacts are committed
- [ ] No private files, local machine paths, usernames, credentials, or secrets are included
- [ ] User-facing feature labels remain accurate
