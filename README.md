# Briefing Telegram Automatico

Envia todos os dias as 6h (America/Sao_Paulo) um briefing matinal via Telegram, com agenda, tarefas, treino do dia, calorias/macros e um checklist de sono/FC/estresse.

## Setup local

Crie um ambiente virtual, rode `pip install -r requirements.txt`, copie `.env.example` para `.env` e preencha `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` e `WEBHOOK_VERIFY_TOKEN` (opcional). Depois rode `python app.py`.

## Endpoints

`GET /health` (healthcheck). `GET /test` (dispara o briefing imediatamente, util para testar). `POST /webhook` (recebe mensagens/eventos do bot, respostas do checklist etc).

## Deploy (Railway)

Conecte este repositorio no Railway, configure as 3 variaveis de ambiente acima no dashboard, e o Railway detecta o `Procfile` e sobe o servico automaticamente. Pegue a URL publica gerada (ex: `https://algo.railway.app`).

## Criar o bot no Telegram

Fale com @BotFather no Telegram, envie `/newbot`, escolha nome e username, e copie o token retornado para `TELEGRAM_BOT_TOKEN`. Envie qualquer mensagem para o seu bot (ex: "oi") e acesse `https://api.telegram.org/bot<TOKEN>/getUpdates` para pegar o `chat.id` da resposta, que e o `TELEGRAM_CHAT_ID`.

## Configurar webhook (opcional, para receber respostas)

Para o bot receber mensagens (ex: respostas do checklist fitness), registre o webhook apontando para o Railway usando esta URL: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://SUA-URL-RAILWAY.railway.app/webhook&secret_token=<WEBHOOK_VERIFY_TOKEN>`

## Por que Telegram em vez de WhatsApp Business API?

A WhatsApp Cloud API exige numero de producao verificado, tem janela de 24h para mensagens livres, e bloqueia numeros de teste em mensagens cross-country para o Brasil (erro 130497). O Telegram Bot API nao tem nenhuma dessas restricoes, e gratuito e nao exige verificacao de empresa, por isso foi escolhido para o envio automatico diario.
