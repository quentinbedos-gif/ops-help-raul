"""
Application Slack Bot pour Ops Help Raul.
Deux modes : Slack Bot (Socket Mode) et CLI interactif pour les tests.
"""

import os
import sys
import logging
import re
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from agent import OpsHelpRaulAgent

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Channel ID a monitorer (test ou production)
TARGET_CHANNEL = os.getenv("HELP_RAUL_CHANNEL_ID", "")


def create_slack_app() -> App:
    """Cree et configure l'application Slack."""
    app = App(token=os.getenv("SLACK_BOT_TOKEN"))
    agent = OpsHelpRaulAgent()

    @app.event("message")
    def handle_message(event, say, client):
        """Traite les messages dans la channel monitoree."""
        # Ignorer les messages du bot lui-meme
        if event.get("bot_id") or event.get("subtype"):
            return

        # Verifier que le message est dans la bonne channel
        channel = event.get("channel", "")
        if TARGET_CHANNEL and channel != TARGET_CHANNEL:
            return

        text = event.get("text", "")
        if not text or not _is_revops_request(text):
            return

        logger.info(f"Demande RevOps detectee dans {channel}: {text[:80]}...")

        # Recuperer le contexte du thread si applicable
        thread_ts = event.get("thread_ts") or event.get("ts")
        context = _get_thread_context(event, client)

        try:
            answer = agent.answer(text, channel_context=context)
            say(text=answer, thread_ts=thread_ts)
            logger.info("Reponse envoyee dans le thread.")
        except Exception as e:
            logger.error(f"Erreur lors de la reponse: {e}")
            say(
                text="Desole, je rencontre un probleme technique. Contacte Paul-Henri ou Constantin directement.",
                thread_ts=thread_ts,
            )

    @app.event("app_mention")
    def handle_mention(event, say, client):
        """Traite les mentions @Ops Help Raul."""
        text = event.get("text", "")
        # Retirer la mention du bot du texte
        text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        if not text:
            say(
                text="Salut ! Pose-moi une question RevOps et je ferai de mon mieux pour t'aider.",
                thread_ts=event.get("ts"),
            )
            return

        logger.info(f"Mention recue: {text[:80]}...")

        thread_ts = event.get("thread_ts") or event.get("ts")
        context = _get_thread_context(event, client)

        try:
            answer = agent.answer(text, channel_context=context)
            say(text=answer, thread_ts=thread_ts)
            logger.info("Reponse envoyee (mention).")
        except Exception as e:
            logger.error(f"Erreur lors de la reponse: {e}")
            say(
                text="Desole, je rencontre un probleme technique. Contacte Paul-Henri ou Constantin directement.",
                thread_ts=thread_ts,
            )

    return app


def _is_revops_request(text: str) -> bool:
    """
    Detecte si un message est une demande RevOps (question OU demande d'action).
    Adapte au style #help_raul ou les messages sont souvent des demandes directes.
    """
    text_lower = text.lower().strip()

    # Ignorer les messages trop courts (salutations, remerciements)
    if len(text_lower) < 15:
        return False

    # Ignorer les messages qui sont juste des remerciements
    thanks_only = ["merci", "merci !", "merci beaucoup", "thanks", "thank you",
                   "top merci", "super merci", "parfait merci", "ok merci",
                   "c'est bon merci", "nickel", "top", "parfait"]
    if text_lower.strip("! ") in thanks_only:
        return False

    # ---- QUESTIONS (point d'interrogation) ----
    if "?" in text:
        return True

    # ---- MOTS INTERROGATIFS ----
    question_words = [
        "comment", "pourquoi", "quand", "combien", "quel", "quelle",
        "quels", "quelles", "est-ce que", "est-ce qu", "ou est",
        "qui peut", "qui doit", "how", "what", "when", "where", "why",
    ]
    for word in question_words:
        if text_lower.startswith(word) or f" {word} " in text_lower:
            return True

    # ---- DEMANDES D'ACTION (typiques de #help_raul) ----
    action_keywords = [
        # Demandes polies
        "svp", "s'il vous plait", "s'il vous plaît", "stp", "s'il te plait",
        "merci d'avance", "merci par avance", "d'avance merci",
        # Formulations de demande
        "possible de", "est-il possible", "est-ce possible", "serait-il possible",
        "il faudrait", "il faut", "on peut", "on pourrait", "tu peux", "vous pouvez",
        "j'aimerais", "je voudrais", "je souhaite", "je souhaiterais",
        "besoin de", "besoin d'aide", "j'ai besoin",
        "peux-tu", "pouvez-vous", "pourriez-vous", "pourrais-tu",
        # Mots-cles d'aide
        "help", "quelqu'un sait", "quelqu'un peut",
        "je ne trouve pas", "je n'arrive pas",
        "probleme avec", "soucis avec", "souci avec",
        "bug", "erreur", "bloque", "bloqu",
        "urgent",
    ]
    for kw in action_keywords:
        if kw in text_lower:
            return True

    # ---- TERMES REVOPS SPECIFIQUES ----
    # Si le message contient des termes metier RevOps, c'est probablement une demande
    revops_terms = [
        # Contract Change
        " cc ", "contract change", "changement de contrat", "changement contrat",
        "upsell", "downsell", "migration", "rollout",
        # Billing
        "facture", "facturation", "remboursement", "avoir", "credit note",
        "impaye", "recouvrement", "prelevement", "chargebee", "stripe",
        "dunning", "chorus", "write-off", "write off",
        # Lead & Opportunity
        "lead", "opportunite", "opportunity", "prospect", "conversion",
        # Churn
        "churn", "resiliation", "reactivation", "desabonnement",
        # Quote
        "devis", "quote", "propal",
        # Subscription
        "subscription", "abonnement", "mrr",
        # Acces
        "acces salesforce", "acces chargebee", "acces stripe",
        "reset password", "mot de passe",
        # Technique
        "sync", "synchronisation", "automation",
        # Actions courantes
        "activer", "desactiver", "creer", "supprimer", "modifier",
        "mettre a jour", "mise a jour", "ajouter", "retirer",
        "badgeuse", "planning",
    ]
    for term in revops_terms:
        if term in text_lower:
            return True

    # ---- LIENS SALESFORCE / CHARGEBEE ----
    # Si le message contient un lien Salesforce ou Chargebee, c'est une demande RevOps
    if "lightning.force.com" in text_lower or "chargebee.com" in text_lower:
        return True

    return False


def _get_thread_context(event: dict, client) -> str:
    """
    Recupere le contexte du thread (5 derniers messages) pour les reponses en thread.
    """
    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return ""

    try:
        result = client.conversations_replies(
            channel=event["channel"],
            ts=thread_ts,
            limit=6,  # +1 car inclut le message parent
        )
        messages = result.get("messages", [])

        # Exclure le message courant et limiter a 5
        context_parts = []
        for msg in messages[-6:-1]:  # 5 derniers avant le message actuel
            user = msg.get("user", "inconnu")
            text = msg.get("text", "")
            context_parts.append(f"<@{user}>: {text}")

        return "\n".join(context_parts)
    except Exception as e:
        logger.warning(f"Impossible de recuperer le contexte du thread: {e}")
        return ""


def run_slack_bot():
    """Lance le bot Slack en mode Socket Mode."""
    app = create_slack_app()
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    logger.info("Bot Ops Help Raul demarre en mode Socket Mode...")
    logger.info(f"Channel monitoree : {TARGET_CHANNEL or 'TOUTES'}")
    handler.start()


def run_test_mode():
    """Mode test interactif en CLI."""
    print("=== Ops Help Raul - Mode Test CLI ===")
    print("Tape une question (ou 'quit' pour quitter)\n")

    agent = OpsHelpRaulAgent()

    while True:
        try:
            question = input("Question > ").strip()
            if question.lower() in ("quit", "exit", "q"):
                print("Au revoir !")
                break
            if not question:
                continue

            print("\nRecherche en cours...\n")
            answer = agent.answer(question)
            print(f"Reponse :\n{answer}\n")
            print("-" * 50 + "\n")
        except KeyboardInterrupt:
            print("\nAu revoir !")
            break
        except Exception as e:
            print(f"Erreur: {e}\n")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test_mode()
    else:
        run_slack_bot()
