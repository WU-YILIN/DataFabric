# Automated Test Workflow

Run one command to execute backend + frontend checks and persist failures for debugging.

## Command

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_test_workflow.ps1
```

## What it runs

1. `backend:pytest` (`genesis_backend`, using `.venv\Scripts\python.exe`)
2. `frontend:lint` (`npm run lint`)
3. `frontend:build` (`npm run build`)

## Outputs

- Per-run logs: `logs/test-runs/<timestamp>-*.log`
- Failure report (append mode): `docs/TEST_FAILURES.md`

## Optional flags

- Skip frontend checks:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\run_test_workflow.ps1 -NoFrontend
  ```

- Skip backend checks:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\run_test_workflow.ps1 -NoBackend
  ```

- Custom backend python path:
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\run_test_workflow.ps1 -BackendPython "D:\path\to\python.exe"
  ```
