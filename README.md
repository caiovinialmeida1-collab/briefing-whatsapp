# Briefing Telegram Automático

Envia todos os dias às 6h (America/Sao_Paulo) um briefing matinal via Telegram,
com agenda, tarefas, treino do dia, calorias/macros e um checklist de sono/FC/estresse.

## Setup local

1. `python -m venv .venv && .venv\Scripts\activate` (Windows) ou `source .venv/bin/activate` (Linux/Mac)
2. `pip install -r requirements.txt`
3. Copie `.env.example` para `.env` e preencha:
   - `TELEGRAM_BOT_TOKEN` (gerado pelo @BotFather no Telegram)
   - `TELEGRAM_CHAT_ID` (seu chat ID numérico, ex: via @userinfobot ou getUpdates)
   - `WEBHOOK_VERIFY_TOKEN` (opcional — protege o endpoint /webhook)
4. `python app.py`

## Endpoints

- `GET /health` — healthcheck
- `GET /test` — dispara o briefing imediatamente (útil para testar)
- `POST /webhook` — recebe mensagens/eventos do bot (respostas do checklist, etc.)

## Deploy (Railway)

1. Conecte este repositório no Railway.
2. Configure as 3 variáveis de ambiente acima no dashboard do Railway.
3. Railway detecta o `Procfile` e sobe o serviço automaticamente.
4. Pegue a URL pública gerada (ex: `https://algo.railway.app`).

## Criar o bot no Telegram

1. Fale com **@BotFather** no Telegram, envie `/newbot`, escolha nome e username.
2. Copie o token retornado para `TELEGRAM_BOT_TOKEN`.
3. Envie qualquer mensagem para o seu bot (ex: "oi").
4. Acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` e pegue o `chat.id` da resposta — esse é o `TELEGRAM_CHAT_ID`.

## Configurar webhook (opcional, para receber respostas)

Para o bot receber mensagens (ex: respostas do checklist fitness), registre o webhook apontando para o Railway:

```
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://SUA-URL-RAILWAY.railway.app/webhook&secret_token=<WEBHOOK_VERIFY_TOKEN>
```

## Por que Telegram em vez de WhatsApp Business API?

A WhatsApp Cloud API exige número de produção verificado, tem janela de 24h para
mensagens livres, e bloqueia números de teste em mensagens cross-country para o Brasil
(erro 130497). O Telegram Bot API não tem nenhuma dessas restrições, é gratuito e
não exige verificação de empresa — por isso foi escolhido para o envio automático diário.
