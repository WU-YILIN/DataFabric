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

## Test Run - 2026-02-27 11:41:34

- Passed: 1
- Failed: 2

### Steps
- [FAIL] **backend:pytest** (exit=1)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-114134-backend-pytest.log
- [FAIL] **frontend:lint** (exit=2)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-114134-frontend-lint.log
- [OK] **frontend:build** (exit=0)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-114134-frontend-build.log

### Failure Details

#### backend:pytest
- ExitCode: 1
- LogFile: D:\project\DataFabric\logs\test-runs\20260227-114134-backend-pytest.log

```text
............F....F............................                           [100%]
================================== FAILURES ===================================
________ test_module16_cost_usage_project_overview_and_resource_detail ________

client = <httpx.AsyncClient object at 0x00000249B7945F50>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x00000249B78AD610>

    @pytest.mark.asyncio
    async def test_module16_cost_usage_project_overview_and_resource_detail(
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        headers = await _register_user(client, "project")
        suffix = _unique_suffix()
        event_code = f"evt_mod16_{suffix}"
    
        event_resp = await client.post(
            "/api/v1/events/",
            json={
                "code": event_code,
                "name": f"Cost Event {suffix}",
                "description": "module16 event",
                "domain": "cost",
                "owner": "mod16-owner",
                "properties": {"user_id": "string", "ts": "iso8601"},
            },
            headers=headers,
        )
        assert event_resp.status_code == 201
        event_id = event_resp.json()["data"]["id"]
    
        def fake_llm_init(self):
            self.client = None
    
        async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
            return []
    
        async def fake_arbitrate(self, prompt: str):
            return ArbitrationResponse(
                verdict="APPROVE",
                score=0.98,
                reasoning="Module16 governance pass",
                recommended_code=None,
            )
    
        monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
        monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
        monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)
    
        governance_resp = await client.post(
            "/api/v1/governance/check",
            json={
                "event_id": event_id,
                "name": f"Cost Event {suffix}",
                "description": "module16 event",
                "properties": {"user_id": "string", "ts": "iso8601"},
            },
            headers=headers,
        )
        assert governance_resp.status_code == 200
    
        pipeline_resp = await client.post(
            "/api/v1/pipelines/provision",
            json={"event_code": event_code},
            headers=headers,
        )
        assert pipeline_resp.status_code == 201
        pipeline_id = pipeline_resp.json()["data"]["id"]
    
        asset_resp = await client.post(
            "/api/v1/catalog/assets",
            json={
                "name": f"Cost Asset {suffix}",
                "asset_type": "TABLE",
                "source_system": "warehouse",
                "database_name": "dwh",
                "object_name": f"cost_asset_{suffix}",
                "domain": "cost",
                "owner": "platform",
                "status": "ACTIVE",
```

#### frontend:lint
- ExitCode: 2
- LogFile: D:\project\DataFabric\logs\test-runs\20260227-114134-frontend-lint.log

```text

> genesis-frontend@0.1.0 lint
> eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0

cmd.exe : 
所在位置 D:\project\DataFabric\scripts\run_test_workflow.ps1:33 字符: 13
+     $all = (& cmd /c $Command 2>&1 | Out-String)
+             ~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
 
Oops! Something went wrong! :(

ESLint: 9.39.3

ESLint couldn't find an eslint.config.(js|mjs|cjs) file.

From ESLint v9.0.0, the default configuration file is now eslint.config.js.
If you are using a .eslintrc.* file, please follow the migration guide
to update your configuration file to the new format:

https://eslint.org/docs/latest/use/configure/migration-guide

If you still have problems after following the migration guide, please stop by
https://eslint.org/chat/help to chat with the team.


```

---

## Test Run - 2026-02-27 11:48:20

- Passed: 1
- Failed: 2

### Steps
- [FAIL] **backend:pytest** (exit=1)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-114820-backend-pytest.log
- [FAIL] **frontend:lint** (exit=1)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-114820-frontend-lint.log
- [OK] **frontend:build** (exit=0)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-114820-frontend-build.log

### Failure Details

#### backend:pytest
- ExitCode: 1
- LogFile: D:\project\DataFabric\logs\test-runs\20260227-114820-backend-pytest.log

```text
............F.................................                           [100%]
================================== FAILURES ===================================
________ test_module16_cost_usage_project_overview_and_resource_detail ________

client = <httpx.AsyncClient object at 0x0000028998648FD0>
monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x0000028998648790>

    @pytest.mark.asyncio
    async def test_module16_cost_usage_project_overview_and_resource_detail(
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        headers = await _register_user(client, "project")
        suffix = _unique_suffix()
        event_code = f"evt_mod16_{suffix}"
    
        event_resp = await client.post(
            "/api/v1/events/",
            json={
                "code": event_code,
                "name": f"Cost Event {suffix}",
                "description": "module16 event",
                "domain": "cost",
                "owner": "mod16-owner",
                "properties": {"user_id": "string", "ts": "iso8601"},
            },
            headers=headers,
        )
        assert event_resp.status_code == 201
        event_id = event_resp.json()["data"]["id"]
    
        def fake_llm_init(self):
            self.client = None
    
        async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
            return []
    
        async def fake_arbitrate(self, prompt: str):
            return ArbitrationResponse(
                verdict="APPROVE",
                score=0.98,
                reasoning="Module16 governance pass",
                recommended_code=None,
            )
    
        monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
        monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
        monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)
    
        governance_resp = await client.post(
            "/api/v1/governance/check",
            json={
                "event_id": event_id,
                "name": f"Cost Event {suffix}",
                "description": "module16 event",
                "properties": {"user_id": "string", "ts": "iso8601"},
            },
            headers=headers,
        )
        assert governance_resp.status_code == 200
    
        pipeline_resp = await client.post(
            "/api/v1/pipelines/provision",
            json={"event_code": event_code},
            headers=headers,
        )
        assert pipeline_resp.status_code == 201
        pipeline_id = pipeline_resp.json()["data"]["id"]
    
        asset_resp = await client.post(
            "/api/v1/catalog/assets",
            json={
                "name": f"Cost Asset {suffix}",
                "asset_type": "TABLE",
                "source_system": "warehouse",
                "database_name": "dwh",
                "object_name": f"cost_asset_{suffix}",
                "domain": "cost",
                "owner": "platform",
                "status": "ACTIVE",
```

#### frontend:lint
- ExitCode: 1
- LogFile: D:\project\DataFabric\logs\test-runs\20260227-114820-frontend-lint.log

```text

> genesis-frontend@0.1.0 lint
> eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0


D:\project\DataFabric\genesis_frontend\src\auth\session.tsx
  247:6   warning  React Hook useMemo has missing dependencies: 'switchProject' and 'switchTenant'. Either include them or remove the dependency array  react-hooks/exhaustive-deps
  252:17  warning  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components       react-refresh/only-export-components

D:\project\DataFabric\genesis_frontend\src\i18n\language.tsx
  387:17  warning  Fast refresh only works when a file only exports components. Use a new file to share constants or functions between components  react-refresh/only-export-components

D:\project\DataFabric\genesis_frontend\src\pages\CollaborationWorkflow.tsx
  126:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\DataProductMarketplace.tsx
  150:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\Explore.tsx
  323:42  error  React Hook "useSuggestedSql" cannot be called inside a callback. React Hooks must be called in a React function component or a custom React Hook function  react-hooks/rules-of-hooks

D:\project\DataFabric\genesis_frontend\src\pages\IncidentResponseCenter.tsx
  165:5  error    Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')
  182:6  warning  React Hook useEffect has a missing dependency: 'detail.case'. Either include it or remove the dependency array  react-hooks/exhaustive-deps

D:\project\DataFabric\genesis_frontend\src\pages\IngestionSdkCenter.tsx
  146:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\IntegrationHub.tsx
  133:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\KnowledgeDocs.tsx
  251:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\MonitoringAlerts.tsx
  122:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\PolicyRuleCenter.tsx
  159:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\ReleaseChangeManagement.tsx
  175:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

D:\project\DataFabric\genesis_frontend\src\pages\SandboxExperimentation.tsx
  147:5  error  Unused eslint-disable directive (no problems were reported from 'react-hooks/exhaustive-deps')

鉁?15 problems (11 errors, 4 warnings)
  10 errors and 0 warnings potentially fixable with the `--fix` option.


```

---

## Test Run - 2026-02-27 11:51:03

- Passed: 3
- Failed: 0

### Steps
- [OK] **backend:pytest** (exit=0)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-115103-backend-pytest.log
- [OK] **frontend:lint** (exit=0)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-115103-frontend-lint.log
- [OK] **frontend:build** (exit=0)
  - Log: D:\project\DataFabric\logs\test-runs\20260227-115103-frontend-build.log


---

