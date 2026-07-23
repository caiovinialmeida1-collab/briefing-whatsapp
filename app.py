import os
import re
import logging
from datetime import datetime, timedelta

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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
WEBHOOK_VERIFY_TOKEN = os.environ.get("WEBHOOK_VERIFY_TOKEN")  # opcional, para proteger o /webhook
DATABASE_URL = os.environ.get("DATABASE_URL")  # Postgres do Railway (persiste o checklist)
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")  # token da integracao interna do Notion
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")  # id da base "Tarefas Briefing"

TIMEZONE = pytz.timezone("America/Sao_Paulo")

# Coordenadas usadas para a previsao do tempo (Rio de Janeiro por padrao).
LATITUDE = os.environ.get("BRIEFING_LAT", "-22.9068")
LONGITUDE = os.environ.get("BRIEFING_LON", "-43.1729")

WORKOUT_PLAN = {
    0: "Pernas (agachamento, leg press, cadeira extensora)",       # Monday
    1: "Peito e triceps (supino, crucifixo, triceps corda)",       # Tuesday
    2: "Costas e biceps (puxada, remada, rosca direta)",           # Wednesday
    3: "Ombro e abdomen (desenvolvimento, elevacao lateral, prancha)",  # Thursday
    4: "Pernas (posterior/gluteos: stiff, cadeira flexora, hip thrust)",  # Friday
    5: "Cardio leve + mobilidade",                                  # Saturday
    6: "Descanso",                                                  # Sunday
}


# ---------------------------------------------------------------------------
# Banco de dados (Postgres) — historico do checklist fitness
# ---------------------------------------------------------------------------
def get_db_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    if not DATABASE_URL:
        logger.warning("DATABASE_URL nao configurada — checklist nao sera salvo.")
        return
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS checklist (
                id SERIAL PRIMARY KEY,
                dia DATE NOT NULL,
                texto TEXT,
                sono NUMERIC,
                fc INTEGER,
                estresse INTEGER,
                criado_em TIMESTAMP DEFAULT NOW()
            )
            """
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Banco de dados inicializado (tabela checklist ok).")
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao inicializar o banco de dados")


def parse_checklist(texto: str):
    sono = fc = estresse = None

    m = re.search(r"(\d+[.,]?\d*)\s*h(oras)?", texto, re.IGNORECASE)
    if m:
        sono = float(m.group(1).replace(",", "."))

    m = re.search(r"fc\D{0,6}(\d{2,3})", texto, re.IGNORECASE)
    if m:
        fc = int(m.group(1))

    m = re.search(r"estr[eé]sse\D{0,6}(\d)", texto, re.IGNORECASE)
    if m:
        estresse = int(m.group(1))

    return sono, fc, estresse


def save_checklist(texto: str):
    if not DATABASE_URL:
        return
    sono, fc, estresse = parse_checklist(texto)
    hoje = datetime.now(TIMEZONE).date()
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO checklist (dia, texto, sono, fc, estresse) VALUES (%s, %s, %s, %s, %s)",
            (hoje, texto, sono, fc, estresse),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao salvar checklist no banco")


def has_checklist_today() -> bool:
    if not DATABASE_URL:
        return True  # sem banco, nao bloqueia o lembrete
    hoje = datetime.now(TIMEZONE).date()
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM checklist WHERE dia = %s", (hoje,))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao verificar checklist do dia")
        return True


def get_streak() -> int:
    if not DATABASE_URL:
        return 0
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT dia FROM checklist ORDER BY dia DESC")
        dias = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao calcular streak")
        return 0

    streak = 0
    esperado = datetime.now(TIMEZONE).date()
    for d in dias:
        if d == esperado:
            streak += 1
            esperado -= timedelta(days=1)
        else:
            break
    return streak


def get_weekly_summary() -> str:
    if not DATABASE_URL:
        return "Banco de dados ainda nao configurado — nao tenho historico pra resumir."

    desde = datetime.now(TIMEZONE).date() - timedelta(days=7)
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT sono, fc, estresse FROM checklist WHERE dia >= %s",
            (desde,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao buscar resumo semanal")
        return "Deu erro ao consultar seu historico. Tenta de novo mais tarde."

    if not rows:
        return "Sem registros de checklist na ultima semana ainda."

    sonos = [r[0] for r in rows if r[0] is not None]
    fcs = [r[1] for r in rows if r[1] is not None]
    estresses = [r[2] for r in rows if r[2] is not None]

    partes = [f"*Resumo dos ultimos 7 dias* ({len(rows)} registro(s)):"]
    if sonos:
        partes.append(f"Sono medio: {sum(sonos) / len(sonos):.1f}h")
    if fcs:
        partes.append(f"FC media de repouso: {sum(fcs) / len(fcs):.0f}bpm")
    if estresses:
        partes.append(f"Estresse medio: {sum(estresses) / len(estresses):.1f}/5")
    partes.append(f"Streak atual: {get_streak()} dia(s) seguidos")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# Previsao do tempo (Open-Meteo — gratuito, sem necessidade de API key)
# ---------------------------------------------------------------------------
def get_weather_text() -> str:
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={LATITUDE}&longitude={LONGITUDE}"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            "&timezone=America%2FSao_Paulo"
        )
        resp = requests.get(url, timeout=10)
        dados = resp.json()
        tmax = dados["daily"]["temperature_2m_max"][0]
        tmin = dados["daily"]["temperature_2m_min"][0]
        chuva = dados["daily"]["precipitation_probability_max"][0]
        return f"Min {tmin:.0f}°C / Max {tmax:.0f}°C, chance de chuva {chuva}%"
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao buscar previsao do tempo")
        return "(nao foi possivel obter a previsao do tempo agora)"


# ---------------------------------------------------------------------------
# Tarefas (Notion — base "Tarefas Briefing")
# ---------------------------------------------------------------------------
def get_notion_tasks_text() -> str:
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return "- (conectar Notion para listar pendencias)"
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
        headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        payload = {
            "filter": {
                "and": [
                    {"property": "Status", "status": {"does_not_equal": "Done"}},
                    {"property": "Status", "status": {"does_not_equal": "Archived"}},
                ]
            },
            "sorts": [{"property": "Due", "direction": "ascending"}],
            "page_size": 10,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        resultados = resp.json().get("results", [])

        if not resultados:
            return "- Nenhuma tarefa pendente. 🎉"

        linhas = []
        for pagina in resultados:
            props = pagina.get("properties", {})
            titulo_prop = props.get("Task name", {}).get("title", [])
            titulo = titulo_prop[0]["plain_text"] if titulo_prop else "(sem titulo)"

            prazo = ""
            due = props.get("Due", {}).get("date")
            if due and due.get("start"):
                try:
                    data_prazo = datetime.fromisoformat(due["start"][:10])
                    prazo = f" (prazo: {data_prazo.strftime('%d/%m')})"
                except ValueError:
                    prazo = ""

            linhas.append(f"- {titulo}{prazo}")

        return "\n".join(linhas)
    except Exception:  # noqa: BLE001
        logger.exception("Erro ao buscar tarefas no Notion")
        return "- (nao foi possivel buscar as tarefas do Notion agora)"


# ---------------------------------------------------------------------------
# Conteudo do briefing
# ---------------------------------------------------------------------------
def get_workout_of_day(weekday: int) -> str:
    return WORKOUT_PLAN.get(weekday, "Descanso")


def build_briefing_text() -> str:
    now = datetime.now(TIMEZONE)
    weekday = now.weekday()
    data_str = now.strftime("%A, %d/%m/%Y")

    workout = get_workout_of_day(weekday)
    clima = get_weather_text()
    tarefas = get_notion_tasks_text()

    # TODO: substituir os blocos abaixo por integracoes reais
    # (Google Calendar, plano de dieta) quando disponiveis.
    agenda = "- (conectar agenda para listar os compromissos de hoje)"
    calorias = "- (conectar plano de dieta para exibir meta de calorias/macros)"

    texto = (
        f"*Bom dia, Caio!* ({data_str})\n\n"
        f"*Clima hoje:*\n{clima}\n\n"
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


def send_telegram_text(chat_id: str, text: str) -> requests.Response:
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


def send_evening_reminder():
    if has_checklist_today():
        logger.info("Checklist de hoje ja preenchido, sem lembrete noturno.")
        return
    texto = (
        "Ainda nao recebi seu checklist fitness de hoje "
        "(sono / FC de repouso / nivel de estresse).\n\n"
        "Manda quando puder, mesmo que seja rapido — ajuda a manter o streak!"
    )
    send_telegram_text(TELEGRAM_CHAT_ID, texto)


# ---------------------------------------------------------------------------
# Respostas do bot a mensagens recebidas
# ---------------------------------------------------------------------------
def build_reply_text(texto_recebido: str) -> str:
    comando = texto_recebido.strip().lower()

    if comando.startswith("/start"):
        return (
            "Ola! Sou o seu bot de briefing matinal. "
            "Todo dia as 6h eu te mando agenda, tarefas, treino, clima e um checklist fitness.\n\n"
            "Comandos disponiveis:\n"
            "/treino — treino de hoje\n"
            "/briefing — manda o briefing completo agora\n"
            "/resumo — resumo dos ultimos 7 dias do checklist\n\n"
            "Fora isso, pode me responder a qualquer momento com sono/FC/estresse "
            "(ex: '7h, FC 58, estresse 2') que eu registro tudo."
        )

    if comando.startswith("/treino"):
        now = datetime.now(TIMEZONE)
        dia_semana = now.strftime("%A")
        return f"*Treino de hoje* ({dia_semana}):\n{get_workout_of_day(now.weekday())}"

    if comando.startswith("/briefing"):
        return build_briefing_text()

    if comando.startswith("/resumo"):
        return get_weekly_summary()

    if not texto_recebido:
        return "Recebi sua mensagem (sem texto). Se quiser, me manda sono/FC/estresse em texto."

    # Assume que e uma resposta do checklist fitness.
    save_checklist(texto_recebido)
    sono, fc, estresse = parse_checklist(texto_recebido)

    detectados = []
    if sono is not None:
        detectados.append(f"sono: {sono}h")
    if fc is not None:
        detectados.append(f"FC: {fc}bpm")
    if estresse is not None:
        detectados.append(f"estresse: {estresse}/5")

    if detectados:
        detectado_str = ", ".join(detectados)
        return (
            f"Registrado! ({detectado_str})\n\n"
            f"Streak atual: {get_streak()} dia(s). Manda /resumo pra ver sua semana."
        )

    return (
        f'Recebido: "{texto_recebido}"\n\n'
        "Salvei no seu historico. Se quiser me contar sono/FC/estresse em numeros "
        "(ex: '7h, FC 58, estresse 2'), eu consigo acompanhar sua evolucao certinho."
    )


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


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    # Se WEBHOOK_VERIFY_TOKEN estiver configurado, o Telegram deve enviar o mesmo
    # valor no header X-Telegram-Bot-Api-Secret-Token (configurado via setWebhook).
    if WEBHOOK_VERIFY_TOKEN:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret != WEBHOOK_VERIFY_TOKEN:
            logger.warning("Webhook recebido com secret token invalido.")
            return "Forbidden", 403

    data = request.get_json(silent=True) or {}
    logger.info("Evento recebido no webhook: %s", data)

    message = data.get("message") or data.get("edited_message")
    if message:
        chat_id = message.get("chat", {}).get("id")
        texto_recebido = (message.get("text") or "").strip()

        if chat_id:
            try:
                resposta = build_reply_text(texto_recebido)
                send_telegram_text(chat_id, resposta)
            except Exception:  # noqa: BLE001
                logger.exception("Erro ao responder mensagem recebida no webhook")

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
    scheduler.add_job(
        send_evening_reminder,
        trigger=CronTrigger(hour=21, minute=0, timezone=TIMEZONE),
        id="lembrete_noturno",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado: briefing as 6h e lembrete noturno as 21h (America/Sao_Paulo).")
    return scheduler


init_db()
scheduler = init_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
