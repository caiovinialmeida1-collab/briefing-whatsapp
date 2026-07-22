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
# Config (from environment variables - set these in Railway, never commit .env)
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN")

TIMEZONE = pytz.timezone("America/Sao_Paulo")

WORKOUT_PLAN = {
        0: "Pernas (agachamento, leg press, cadeira extensora)",
        1: "Peito e triceps (supino, crucifixo, triceps corda)",
        2: "Costas e biceps (puxada, remada, rosca direta)",
        3: "Ombro e abdomen (desenvolvimento, elevacao lateral, prancha)",
        4: "Pernas (posterior/gluteos: stiff, cadeira flexora, hip thrust)",
        5: "Cardio leve + mobilidade",
        6: "Descanso",
}


def get_workout_of_day(weekday):
        return WORKOUT_PLAN.get(weekday, "Descanso")


def build_briefing_text():
        now = datetime.now(TIMEZONE)
        weekday = now.weekday()
        data_str = now.strftime("%A, %d/%m/%Y")

    workout = get_workout_of_day(weekday)

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


def send_telegram_text(chat_id, text):
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        response = requests.post(url, json=payload, timeout=30)
        logger.info("Telegram API response: %s %s", response.status_code, response.text)
        return response


def send_briefing():
        texto = build_briefing_text()
        resp = send_telegram_text(TELEGRAM_CHAT_ID, texto)
        return resp


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
        return jsonify({"status": "ok"}), 200


@app.route("/test", methods=["GET"])
def test():
        try:
                    resp = send_briefing()
                    return jsonify({
                        "sent": resp.status_code == 200,
                        "status_code": resp.status_code,
                        "response": resp.json() if resp.content else None,
                    }), (200 if resp.status_code == 200 else 502)
except Exception as exc:
        logger.exception("Erro ao enviar briefing de teste")
        return jsonify({"sent": False, "error": str(exc)}), 500


@app.route("/webhook", methods=["POST"])
def webhook_receive():
        if WEBHOOK_VERIFY_TOKEN:
                    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
                    if secret != WEBHOOK_VERIFY_TOKEN:
                                    logger.warning("Webhook recebido com secret token invalido.")
                                    return "Forbidden", 403

                data = request.get_json(silent=True) or {}
    logger.info("Evento recebido no webhook: %s", data)
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
