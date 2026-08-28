# Sprint 0 Integration Tests

## Governance structure integration
- `test_dev_branch_exists`: `git branch` lists `dev` — **PASS**
- `test_remote_profile_valid`: `remote-profile.sh` reports PROVIDER=github, BASE=main, WORK=dev, MERGEPOLICY=human-approve — **PASS**
- `test_substrate_complete`: `check-substrate.sh` reports `substrate-complete` — **PASS**
