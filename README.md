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
