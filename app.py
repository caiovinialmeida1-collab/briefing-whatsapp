import os
import logging
from datetime import datetime

import requests
import pytz
from flask import Flask, request, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("briefing")

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config (from environment variables — set these in Railway, never commit .env)
# ---------------------------------------------------------------------------
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_BUSINESS_ID = os.environ.get("WHATSAPP_BUSINESS_ID")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")
USER_PHONE_NUMBER = os.environ.get("USER_PHONE_NUMBER")

TIMEZONE = pytz.timezone("America/Sao_Paulo")
GRAPH_API_VERSION = "v20.0"

WORKOUT_PLAN = {
    0: "Pernas (agachamento, leg press, cadeira extensora)",       # Monday
    1: "Peito e triceps (supino, crucifixo, triceps corda)",       # Tuesday
    2: "Costas e biceps (puxada, remada, rosca direta)",           # Wednesday
    3: "Ombro e abdomen (desenvolvimento, elevacao lateral, prancha)",  # Thursday
    4: "Pernas (posterior/gluteos: stiff, cadeira flexora, hip thrust)",  # Friday
    5: "Cardio leve + mobilidade",                                  # Saturday
    6: "Descanso",                                                  # Sunday
}


def get_workout_of_day(weekday: int) -> str:
    return WORKOUT_PLAN.get(weekday, "Descanso")


def build_briefing_text() -> str:
    now = datetime.now(TIMEZONE)
    weekday = now.weekday()
    data_str = now.strftime("%A, %d/%m/%Y")

    workout = get_workout_of_day(weekday)

    # TODO: substituir os blocos abaixo por integrações reais
    # (Google Calendar, task tracker, plano de dieta) quando disponiveis.
    agenda = "- (conectar agenda para listar os compromissos de hoje)"
    tarefas = "- (conectar lista de tarefas para listar pendencias)"
    calorias = "- (conectar plano de dieta para exibir meta de calorias/macros)"

    texto = (
        f"*Bom dia, Caio!* ({data_str})\n\n"
        f"*Agenda de hoje:*\n{agenda}\n\n"
        f"*Tarefas pendentes:*\n{tarefas}\n\n"
        f"*Treino do dia:*\n{workout}\n\n"
        f"*Calorias/macros:*\n{calorias}\n\n"
        f"*Checklist Fitness:*\n"
        f"Responda essa mensagem com:\n"
        f"1) Horas de sono\n"
        f"2) FC de repouso\n"
        f"3) Nivel de estresse (1-5)"
    )
    return texto


def send_whatsapp_text(to_number: str, text: str) -> requests.Response:
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    logger.info("WhatsApp API response: %s %s", response.status_code, response.text)
    return response


def send_briefing():
    texto = build_briefing_text()
    resp = send_whatsapp_text(USER_PHONE_NUMBER, texto)
    return resp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/test", methods=["GET"])
def test():
    """Dispara o briefing manualmente, para testes."""
    try:
        resp = send_briefing()
        return jsonify({
            "sent": resp.status_code == 200,
            "status_code": resp.status_code,
            "response": resp.json() if resp.content else None,
        }), (200 if resp.status_code == 200 else 502)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao enviar briefing de teste")
        return jsonify({"sent": False, "error": str(exc)}), 500


@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso pela Meta.")
        return challenge, 200

    logger.warning("Falha na verificacao do webhook (token nao confere).")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    data = request.get_json(silent=True) or {}
    logger.info("Evento recebido no webhook: %s", data)
    # TODO: aqui e onde as respostas do checklist (sono/FC/estresse)
    # podem ser capturadas e encaminhadas para o projeto Fitness.
    return jsonify({"status": "received"}), 200


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
def init_scheduler():
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        send_briefing,
        trigger=CronTrigger(hour=6, minute=0, timezone=TIMEZONE),
        id="briefing_diario",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado: briefing diario as 6h (America/Sao_Paulo).")
    return scheduler


scheduler = init_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
