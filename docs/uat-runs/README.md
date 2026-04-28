# UAT Runs Archive

Store each staged UAT execution file in this directory for release traceability.

Create a new run file:

```bash
./scripts/start_uat_run.sh round-1
```

Optional staging URL annotation:

```bash
UAT_BASE_URL=https://staging.example.com ./scripts/start_uat_run.sh round-2
```

Recommended flow:
1. Generate a new run file before starting UAT.
2. Record pass/fail outcomes and defects directly in the file.
3. Commit the run file with the release candidate branch or tag.
