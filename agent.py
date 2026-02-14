"""
Orchestrateur principal de l'agent Ops Help Raul.
Chaine : KB retrieval -> context building -> Claude API -> post-processing.
Detecte le niveau de confiance et cree des entrees KB placeholder si necessaire.
"""

import os
import re
import sys
import logging
from typing import Optional
from anthropic import Anthropic
from kb_retriever import KBRetriever, format_kb_entries_for_prompt
from prompts import SYSTEM_PROMPT, KB_CONTEXT_TEMPLATE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# IDs Slack pour les escalades
PAUL_HENRI_ID = os.getenv("PAUL_HENRI_SLACK_ID", "PLACEHOLDER")
CONSTANTIN_ID = os.getenv("CONSTANTIN_SLACK_ID", "PLACEHOLDER")


class OpsHelpRaulAgent:
    """Agent principal qui orchestre KB retrieval + Claude API."""

    def __init__(self):
        self.client = Anthropic()
        self.kb = KBRetriever()
        logger.info("Agent Ops Help Raul initialise.")

    def answer(self, question: str, channel_context: str = "") -> str:
        """
        Point d'entree principal. Recoit une question, retourne une reponse.
        1. Recherche dans la KB
        2. Construit le contexte pour Claude
        3. Appelle Claude API
        4. Post-traitement (confiance, escalade, creation KB si necessaire)
        """
        logger.info(f"Question recue : {question[:80]}...")

        # Etape 1 : Recherche KB
        kb_entries = self._retrieve_kb(question)
        logger.info(f"KB: {len(kb_entries)} entree(s) trouvee(s)")

        # Etape 2 : Construire le message avec contexte KB
        kb_context = format_kb_entries_for_prompt(kb_entries)
        user_message = KB_CONTEXT_TEMPLATE.format(
            kb_entries=kb_context,
            question=question,
        )

        # Ajouter le contexte du thread si disponible
        if channel_context:
            user_message = f"## Contexte de la conversation Slack\n{channel_context}\n\n{user_message}"

        # Etape 3 : Appel Claude API
        try:
            # Remplacer les placeholders dans le system prompt
            system = SYSTEM_PROMPT.replace("PAUL_HENRI_ID", PAUL_HENRI_ID).replace("CONSTANTIN_ID", CONSTANTIN_ID)

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            answer = response.content[0].text
            logger.info("Reponse Claude recue.")
        except Exception as e:
            logger.error(f"Erreur Claude API: {e}")
            return (
                "Desole, je rencontre un probleme technique. "
                f"<@{PAUL_HENRI_ID}> ou <@{CONSTANTIN_ID}> peuvent t'aider en attendant."
            )

        # Etape 4 : Post-traitement
        answer = self._post_process(answer, kb_entries, question)
        return answer

    def _retrieve_kb(self, question: str) -> list[dict]:
        """
        Strategie de recherche multi-etapes :
        1. Recherche par mots-cles
        2. Si pas assez de resultats, detection de categorie + recherche par categorie
        """
        # Etape 1 : Recherche par mots-cles
        results = self.kb.search_by_keywords(question, max_results=8)

        # Etape 2 : Fallback par categorie si peu de resultats
        if len(results) < 2:
            category = self._detect_category(question)
            if category:
                logger.info(f"Fallback categorie detectee : {category}")
                cat_results = self.kb.search_by_category(category, max_results=5)
                # Fusionner sans doublons
                existing_names = {r["name"] for r in results}
                for entry in cat_results:
                    if entry["name"] not in existing_names:
                        results.append(entry)

        return results[:8]

    def _detect_category(self, question: str) -> Optional[str]:
        """Detection de categorie basee sur des mots-cles."""
        q = question.lower()

        category_keywords = {
            "Billing": ["facture", "facturation", "credit note", "avoir", "remboursement", "paiement",
                        "rib", "tva", "impaye", "recouvrement", "dunning", "chargebee", "stripe",
                        "prelevement", "encaissement", "chorus", "banniere", "relance"],
            "Lead": ["lead", "prospect", "conversion lead", "convertir", "assignation", "doublon",
                     "partenariat", "partnership"],
            "Contract Change": ["changement contrat", "contract change", "upsell", "downsell",
                                "migration", "rollout", "remise", "discount", "avenant",
                                "mm vers enterprise", "enterprise vers mm", "changement plan"],
            "Churn": ["churn", "resiliation", "reactivation", "reactiver", "desabonnement",
                      "annulation", "free trial", "churned"],
            "Quote": ["devis", "quote", "propal", "proposition", "multi-shop", "multi shop",
                      "approbation devis"],
            "Opportunité": ["opportunite", "opportunity", "pipeline", "conversion opp"],
            "Pricing": ["prix", "pricing", "tarif", "grille", "remise exceptionnelle",
                        "mm vs enterprise"],
            "Calendrier": ["calendly", "booking", "calendar", "rdv", "rendez-vous",
                           "assignation raul"],
            "Accès": ["acces", "login", "mot de passe", "password", "reset", "salesforce acces",
                      "chargebee acces", "stripe acces"],
            "Technique": ["bug", "sync", "synchronisation", "automation", "erreur technique",
                          "probleme sf"],
            "Subscription/MRR": ["mrr", "subscription", "abonnement", "modification cb",
                                 "mensualite"],
            "Attribution": ["attribution", "changement owner", "reassignation", "regle attribution"],
            "Rapport": ["rapport", "report", "dashboard", "tableau de bord", "stats"],
            "Intégration": ["integration", "upflow", "connecteur", "api", "webhook",
                            "cb sf sync", "calendly sf"],
        }

        best_match = None
        best_score = 0

        for category, keywords in category_keywords.items():
            score = sum(1 for kw in keywords if kw in q)
            if score > best_score:
                best_score = score
                best_match = category

        return best_match if best_score > 0 else None

    def _post_process(self, answer: str, kb_entries: list[dict], question: str) -> str:
        """
        Post-traitement de la reponse :
        - Detecte le niveau de confiance
        - Si confiance basse, cree une entree KB placeholder
        - Remplace les placeholders
        """
        # Detecter le niveau de confiance dans la reponse
        confidence = "HAUTE"
        if "[CONFIANCE:BASSE]" in answer:
            confidence = "BASSE"
        elif "[CONFIANCE:MOYENNE]" in answer:
            confidence = "MOYENNE"

        # Retirer le tag de confiance de la reponse affichee
        answer = answer.replace("[CONFIANCE:HAUTE]", "").replace("[CONFIANCE:MOYENNE]", "").replace("[CONFIANCE:BASSE]", "").strip()

        # Si confiance basse : creer une entree KB placeholder
        if confidence == "BASSE":
            logger.info("Confiance BASSE detectee -> creation entree KB placeholder")
            category = self._detect_category(question) or ""
            created = self.kb.create_placeholder_entry(
                question=question,
                category=category,
                detected_topic="",
            )
            if created and created.get("url"):
                answer += (
                    f"\n\n📝 *Une fiche a ete creee dans la KB pour documenter ce process :*\n"
                    f"<{created['url']}|Completer la fiche KB>"
                )
                logger.info(f"Entree KB creee : {created['url']}")

        # Remplacer les IDs Slack si encore en placeholder
        answer = answer.replace("<@PAUL_HENRI_ID>", f"<@{PAUL_HENRI_ID}>")
        answer = answer.replace("<@CONSTANTIN_ID>", f"<@{CONSTANTIN_ID}>")

        return answer


# Mode test standalone
if __name__ == "__main__":
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "Comment convertir un lead dans Raul ?"

    agent = OpsHelpRaulAgent()
    print(f"\nQuestion : {question}\n")
    response = agent.answer(question)
    print(f"Reponse :\n{response}")
