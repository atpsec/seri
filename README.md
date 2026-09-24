# Akış MVP

Akış, tek cümlelik bir hedefi ChatGPT planı, Composio araç keşfi ve Modal çalıştırma adımlarına dönüştüren küçük bir çalışma alanıdır.

## Çalıştırma

```powershell
cd akis-mvp
.\.venv\Scripts\python.exe server.py
```

Ardından http://127.0.0.1:4173/ adresini aç.

## Modal deploy

```powershell
.\.venv\Scripts\python.exe -m modal deploy .\modal_app.py --env main --profile tpberg3tp
```

`composio-akis` Modal Secret’ı Composio proje anahtarını içerir. Kullanıcı uygulama hesabı bağladığında `/run` endpoint’i ilgili Composio araçlarını da raporlar.


## Agent Control Plane v1

Akış artık workflow planlamanın yanında ilk control-plane katmanını da taşır:

- Agent Gateway: ChatGPT, Codex, Claude ve Cursor için ortak giriş modeli.
- Project Memory: planlanan hedefleri named Modal Dict içinde kalıcı olarak saklar.
- Policy Engine: okuma işlemlerini otomatik, yazma işlemlerini onay gerektiren, yıkıcı işlemleri engellenmiş olarak sınıflandırır.
- Governed Tool Gateway: `/tools/execute` üzerinden Composio araçlarını policy katmanından geçirir.
- Approval State Machine: yazma araçlarını `awaiting_approval` durumunda bekletir; `/approvals/{run_id}` ile approve/reject uygular.
- Receipts: planlama, policy, approval ve execution olayları için kimlikli ve zaman damgalı denetim kayıtları üretir.
- War Room: bağlı ajanları, son run'ları ve bekleyen onayları arayüzde gösterir.
- `/control-plane`: son çalışmalar, hafıza ve politika özetini sunar.

Modal Dict kayıtları dayanıklı depodadır ancak Modal'ın güncel Dict yaşam döngüsü kurallarına tabidir. Gerçek MCP transport, harici Codex/Claude session adaptörleri ve öğrenen Skill Forge sonraki dilimlerdir.


## Remote Agent Gateway

External agents can now coordinate through the authenticated MCP endpoint:

`https://tpberg3tp--akis-workflow-web.modal.run/agent/mcp`

The gateway exposes `akis_claim_task`, `akis_get_context`, and `akis_submit_result`. It uses Streamable HTTP and requires the `AKIS_AGENT_TOKEN` bearer token. See [docs/agent-gateway.md](docs/agent-gateway.md) for Codex and Claude Code setup.
