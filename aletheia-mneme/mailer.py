import resend
import env

resend.api_key = env.RESEND_API_KEY

def _send(to: str, subject: str, text: str) -> None:
    try:
        resend.Emails.send({
            "from": env.EMAIL_FROM,
            "to": to,
            "subject": subject,
            "text": text,
        })
    except Exception as e:
        import structlog
        structlog.get_logger().error("email_failed", to=to, error=str(e))

def send_api_key(to: str, api_key: str) -> None:
    _send(to, "Your Aletheia Mneme API Key",
        f"Welcome to Aletheia Mneme.\n\nYour API key:\n{api_key}\n\n"
        f"Docs: https://aletheia-mneme.onrender.com/docs\n\n"
        f"All 16 tools are available including semantic search, relay, and cloud sync.")
