# TEST_FAILURES

Automated failure records for debugging.


## Test Run - 2026-02-27 11:39:31

- Passed: 
- Failed: 2

### Steps
- [FAIL] **backend:pytest** (exit=1)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-113931-backend-pytest.log
- [FAIL] **frontend:lint** (exit=1)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-113931-frontend-lint.log
- [OK] **frontend:build** (exit=0)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-113931-frontend-build.log

### Failure Details

#### backend:pytest
- ExitCode: 1
- LogFile: D:\project\DataFabric\logs\test-runs\20260227-113931-backend-pytest.log

```text
cmd.exe : D:\project\DataFabric\genesis_backend\.venv\Scripts\python.exe: No module named pytest
所在位置 D:\project\DataFabric\scripts\run_test_workflow.ps1:33 字符: 13
+     $all = (& cmd /c $Command 2>&1 | Out-String)
+             ~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (D:\project\Data...le named pytest:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 

```

#### frontend:lint
- ExitCode: 1
- LogFile: D:\project\DataFabric\logs\test-runs\20260227-113931-frontend-lint.log

```text

> genesis-frontend@0.1.0 lint
> eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0

cmd.exe : 'eslint' 不是内部或外部命令，也不是可运行的程序
所在位置 D:\project\DataFabric\scripts\run_test_workflow.ps1:33 字符: 13
+     $all = (& cmd /c $Command 2>&1 | Out-String)
+             ~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: ('eslint' 不是内部或外部命令，也不是可运行的程序:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
或批处理文件。

```

---

