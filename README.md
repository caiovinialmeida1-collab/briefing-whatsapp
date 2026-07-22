# Briefing WhatsApp Automático

Envia todos os dias às 6h (America/Sao_Paulo) um briefing matinal via WhatsApp Business Cloud API,
com agenda, tarefas, treino do dia, calorias/macros e um checklist de sono/FC/estresse.

## Setup local

1. `python -m venv .venv && .venv\Scripts\activate` (Windows) ou `source .venv/bin/activate` (Linux/Mac)
2. `pip install -r requirements.txt`
3. Copie `.env.example` para `.env` e preencha:
   - `WHATSAPP_PHONE_ID`
   - `WHATSAPP_ACCESS_TOKEN`
   - `WHATSAPP_BUSINESS_ID`
   - `WHATSAPP_VERIFY_TOKEN`
   - `USER_PHONE_NUMBER` (formato internacional, ex: 5521999999999)
4. `python app.py`

## Endpoints

- `GET /health` — healthcheck
- `GET /test` — dispara o briefing imediatamente (útil para testar)
- `GET /webhook` — verificação do webhook pela Meta
- `POST /webhook` — recebe eventos/mensagens do WhatsApp

## Deploy (Railway)

1. Conecte este repositório no Railway.
2. Configure as 5 variáveis de ambiente acima no dashboard do Railway.
3. Railway detecta o `Procfile` e sobe o serviço automaticamente.
4. Pegue a URL pública gerada (ex: `https://algo.railway.app`).

## Configurar Webhook na Meta

Em Meta for Developers → seu app → WhatsApp → Configuração → Webhooks:

- Callback URL: `https://SUA-URL-RAILWAY.railway.app/webhook`
- Verify Token: o mesmo valor de `WHATSAPP_VERIFY_TOKEN`

## Token de acesso

O token gerado em "Meta for Developers → Configuração da API" é temporário (~24h).
Para produção, gere um **token permanente de System User** (Business Settings → System Users)
e atualize a variável `WHATSAPP_ACCESS_TOKEN` no Railway.
