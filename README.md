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
- Project Memory: planlanan hedefleri proje hafızasına kaydeder.
- Policy Engine: okuma işlemlerini otomatik, yazma işlemlerini onay gerektiren, yıkıcı işlemleri engellenmiş olarak sınıflandırır.
- Receipts: her planlama çalışması için kimlikli ve zaman damgalı denetim kayıtları üretir.
- /control-plane: son çalışmalar, hafıza ve politika özetini sunar.

Bu ilk dilim kasıtlı olarak bellek içidir. Kalıcı veri deposu, gerçek onay yürütmesi, MCP gateway ve multi-agent War Room sonraki dilimlerdir.
