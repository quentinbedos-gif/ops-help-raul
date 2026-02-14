"""
Module agent Claude API.
Gere l'interaction avec Claude pour repondre aux questions RevOps.
"""

import os
import logging
from anthropic import Anthropic

from prompts import SYSTEM_PROMPT, KB_CONTEXT_TEMPLATE
from kb_retriever import KBRetriever, format_kb_entries_for_prompt

logger = logging.getLogger(__name__)


class OpsHelpRaulAgent:
    """Agent principal qui orchestre KB retrieval + Claude API."""

    def __init__(
        self,
        anthropic_key: str | None = None,
        notion_token: str | None = None,
        model: str = "claude-sonnet-4-5-20250929",
    ):
        api_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY requis")

        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.kb = KBRetriever(notion_token=notion_token)

        # Slack user IDs pour les mentions d'escalade
        self.paul_henri_id = os.getenv("PAUL_HENRI_SLACK_ID", "UXXXXXXXXXX")
        self.constantin_id = os.getenv("CONSTANTIN_SLACK_ID", "UXXXXXXXXXX")

        # Remplacer les placeholders dans le system prompt
        self.system_prompt = SYSTEM_PROMPT.replace(
            "PAUL_HENRI_ID", self.paul_henri_id
        ).replace("CONSTANTIN_ID", self.constantin_id)

    def answer(self, question: str, channel_context: str = "") -> str:
        """
        Repond a une question RevOps.

        Args:
            question: La question posee sur #help_raul
            channel_context: Contexte additionnel (messages precedents du thread)

        Returns:
            Reponse formatee pour Slack
        """
        # 1. Retrieval KB
        logger.info(f"Recherche KB pour: {question[:80]}...")
        kb_entries = self._retrieve_kb(question)

        # 2. Construire le contexte
        kb_text = format_kb_entries_for_prompt(kb_entries)
        user_message = KB_CONTEXT_TEMPLATE.format(
            kb_entries=kb_text,
            question=question,
        )

        if channel_context:
            user_message = f"## Contexte du thread\n{channel_context}\n\n{user_message}"

        # 3. Appel Claude API
        logger.info(f"Appel Claude API ({self.model})...")
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=self.system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            answer = response.content[0].text

            # 4. Post-processing
            answer = self._post_process(answer, kb_entries)

            logger.info(
                f"Reponse generee ({response.usage.input_tokens} in / "
                f"{response.usage.output_tokens} out tokens)"
            )
            return answer

        except Exception as e:
            logger.error(f"Erreur Claude API: {e}")
            return (
                f"Desole, je rencontre un probleme technique. "
                f"<@{self.paul_henri_id}> <@{self.constantin_id}> "
                f"pouvez-vous aider ?\n\n_Question originale: {question[:200]}_"
            )

    def _retrieve_kb(self, question: str) -> list[dict]:
        """
        Strategie de retrieval multi-etapes :
        1. Recherche par mots-cles extraits de la question
        2. Si peu de resultats, recherche par categorie detectee
        """
        # Recherche principale par mots-cles
        entries = self.kb.search_by_keywords(question, max_results=6)

        # Si pas assez de resultats, tenter par categorie
        if len(entries) < 2:
            category = self._detect_category(question)
            if category:
                cat_entries = self.kb.search_by_category(category, max_results=4)
                # Ajouter les entries non dupliquees
                existing_ids = {e["id"] for e in entries}
                for entry in cat_entries:
                    if entry["id"] not in existing_ids:
                        entries.append(entry)

        return entries[:8]  # Max 8 entries pour ne pas surcharger le contexte

    def _detect_category(self, question: str) -> str | None:
        """Detecte la categorie probable a partir de mots-cles dans la question."""
        q = question.lower()

        category_keywords = {
            "Billing": [
                "facture", "invoice", "paiement", "payment", "remboursement",
                "refund", "avoir", "credit note", "chargebee", "impaye", "unpaid",
                "rib", "tva", "adresse facturation", "chorus",
            ],
            "Lead": [
                "lead", "conversion", "convertir", "siret", "account", "prospect",
            ],
            "Contract Change": [
                "contract change", "changement contrat", "migration", "upsell",
                "downsell", "rollout", "discount", "remise", "approbation",
            ],
            "Churn": [
                "churn", "resiliation", "reactivation", "reactiver",
            ],
            "Quote": [
                "devis", "quote", "proposition",
            ],
            "Calendrier": [
                "calendrier", "booking", "calendly", "rdv", "rendez-vous",
            ],
            "Opportunité": [
                "opportunite", "opportunity", "pipeline",
            ],
            "Pricing": [
                "prix", "pricing", "tarif", "grille", "plan",
            ],
            "Accès": [
                "acces", "login", "mot de passe", "password", "permission",
            ],
            "Technique": [
                "bug", "erreur", "sync", "automation", "workflow",
            ],
            "Subscription/MRR": [
                "mrr", "subscription", "abonnement", "recurring",
            ],
            "Attribution": [
                "attribution", "assignation", "owner", "transfert portefeuille",
            ],
            "Rapport": [
                "rapport", "report", "dashboard", "kpi",
            ],
            "Intégration": [
                "integration", "sync", "api", "stripe", "upflow",
            ],
        }

        best_match = None
        best_score = 0

        for category, keywords in category_keywords.items():
            score = sum(1 for kw in keywords if kw in q)
            if score > best_score:
                best_score = score
                best_match = category

        return best_match if best_score > 0 else None

    def _post_process(self, answer: str, kb_entries: list[dict]) -> str:
        """
        Post-traitement de la reponse :
        - Remplacer les placeholders Slack IDs si necessaire
        - Ajouter le footer avec les sources
        """
        # Ajouter un footer discret avec la source
        if kb_entries:
            categories = list({e.get("categorie", "") for e in kb_entries if e.get("categorie")})
            if categories:
                answer += f"\n\n_Source KB: {', '.join(categories)}_"

        return answer


# --- Mode test standalone ---
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    agent = OpsHelpRaulAgent()

    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Comment convertir un lead dans Raul ?"
    print(f"\n--- Question: {question} ---\n")
    response = agent.answer(question)
    print(response)
