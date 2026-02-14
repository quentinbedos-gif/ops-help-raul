"""
Application Slack Bot - Ops Help Raul
Point d'entree principal du POC.

Usage:
    python app.py          # Lance le bot Slack en mode Socket
    python app.py --test   # Lance en mode test (CLI interactif)
"""

import os
import sys
import logging
import re
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ops-help-raul")


def run_slack_bot():
    """Lance le bot Slack en mode Socket Mode."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    from agent import OpsHelpRaulAgent

    app = App(token=os.getenv("SLACK_BOT_TOKEN"))
    agent = OpsHelpRaulAgent()

    # Canal cible
    HELP_RAUL_CHANNEL = os.getenv("HELP_RAUL_CHANNEL_ID", "")

    @app.event("message")
    def handle_message(event, say, client):
        """Traite les messages sur #help_raul."""
        # Ignorer les messages du bot lui-meme
        if event.get("bot_id") or event.get("subtype"):
            return

        channel = event.get("channel", "")
        text = event.get("text", "").strip()
        user = event.get("user", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        # Si un canal specifique est configure, ne repondre que la-bas
        if HELP_RAUL_CHANNEL and channel != HELP_RAUL_CHANNEL:
            return

        # Ignorer les messages trop courts
        if len(text) < 5:
            return

        # Ignorer les messages qui ne sont pas des questions
        # (heuristique simple : contient ? ou commence par comment/pourquoi/ou/etc.)
        if not _is_question(text):
            return

        logger.info(f"Question de <@{user}>: {text[:100]}...")

        # Recuperer le contexte du thread si c'est une reponse
        thread_context = ""
        if event.get("thread_ts"):
            thread_context = _get_thread_context(client, channel, event["thread_ts"])

        # Repondre dans un thread
        try:
            response = agent.answer(text, channel_context=thread_context)
            say(text=response, thread_ts=thread_ts)
            logger.info(f"Reponse envoyee a <@{user}>")
        except Exception as e:
            logger.error(f"Erreur lors du traitement: {e}")
            say(
                text="Desole, je rencontre un probleme technique. L'equipe RevOps a ete notifiee.",
                thread_ts=thread_ts,
            )

    @app.event("app_mention")
    def handle_mention(event, say, client):
        """Traite les mentions directes du bot (@Ops Help Raul)."""
        text = event.get("text", "")
        user = event.get("user", "")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        # Retirer la mention du bot du texte
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        if not text:
            say(
                text="Comment puis-je t'aider ? Pose-moi ta question RevOps.",
                thread_ts=thread_ts,
            )
            return

        logger.info(f"Mention de <@{user}>: {text[:100]}...")

        thread_context = ""
        if event.get("thread_ts"):
            thread_context = _get_thread_context(client, channel, event["thread_ts"])

        try:
            response = agent.answer(text, channel_context=thread_context)
            say(text=response, thread_ts=thread_ts)
        except Exception as e:
            logger.error(f"Erreur: {e}")
            say(
                text="Desole, probleme technique. L'equipe RevOps est notifiee.",
                thread_ts=thread_ts,
            )

    def _is_question(text: str) -> bool:
        """Heuristique pour detecter si un message est une question."""
        text_lower = text.lower().strip()
        # Contient un point d'interrogation
        if "?" in text:
            return True
        # Commence par un mot interrogatif
        question_starters = [
            "comment", "pourquoi", "ou ", "où ", "quand", "quel", "quelle",
            "qui ", "est-ce", "how", "why", "where", "when", "what", "who",
            "can ", "could", "is ", "are ", "do ", "does ",
            "j'ai besoin", "je cherche", "je voudrais", "je veux",
            "help", "aide", "besoin", "probleme", "problème", "souci",
            "urgent", "stp", "svp", "please",
        ]
        return any(text_lower.startswith(s) for s in question_starters)

    def _get_thread_context(client, channel: str, thread_ts: str) -> str:
        """Recupere les messages precedents d'un thread pour le contexte."""
        try:
            result = client.conversations_replies(
                channel=channel,
                ts=thread_ts,
                limit=5,
            )
            messages = result.get("messages", [])
            if len(messages) <= 1:
                return ""

            # Prendre les messages precedents (sans le dernier qui est la question)
            context_parts = []
            for msg in messages[:-1]:
                user = msg.get("user", "unknown")
                text = msg.get("text", "")
                context_parts.append(f"<@{user}>: {text}")

            return "\n".join(context_parts)
        except Exception as e:
            logger.warning(f"Erreur lecture thread: {e}")
            return ""

    # Demarrage
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    logger.info("Bot Ops Help Raul demarre en Socket Mode...")
    handler.start()


def run_test_mode():
    """Mode test interactif en CLI."""
    from agent import OpsHelpRaulAgent

    print("=" * 60)
    print("  Ops Help Raul - Mode Test CLI")
    print("  Tape 'quit' pour quitter")
    print("=" * 60)

    agent = OpsHelpRaulAgent()

    while True:
        print()
        question = input("Question > ").strip()
        if question.lower() in ("quit", "exit", "q"):
            break
        if not question:
            continue

        print("\nRecherche en cours...")
        response = agent.answer(question)
        print(f"\n{response}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test_mode()
    else:
        run_slack_bot()
