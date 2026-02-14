"""
Module de retrieval de la Knowledge Base Notion.
Interroge la base Notion KB Help Raul pour trouver les entrees pertinentes.
"""

import os
import logging
from typing import Optional
from notion_client import Client as NotionClient

logger = logging.getLogger(__name__)

# ID de la database KB dans Notion
KB_DATABASE_ID = os.getenv("NOTION_KB_DATABASE_ID", "9a6fb1778ff040d0a28279e32fe91ff2")


class KBRetriever:
    """Recupere les entrees pertinentes de la KB Notion."""

    def __init__(self, notion_token: Optional[str] = None):
        token = notion_token or os.getenv("NOTION_API_TOKEN")
        if not token:
            raise ValueError("NOTION_API_TOKEN requis")
        self.notion = NotionClient(auth=token)
        self.db_id = KB_DATABASE_ID

    def search_by_keywords(self, query: str, max_results: int = 8) -> list[dict]:
        """
        Recherche dans la KB par mots-cles.
        Strategie : recherche dans les champs Mots-cles, Description, et Name.
        Retourne les entrees les plus pertinentes.
        """
        # Strategie 1 : Recherche textuelle via l'API Notion search
        results = []

        try:
            # Recherche directe dans la database
            response = self.notion.databases.query(
                database_id=self.db_id,
                filter=self._build_text_filter(query),
                page_size=max_results,
            )
            results.extend(self._parse_pages(response.get("results", [])))
        except Exception as e:
            logger.warning(f"Recherche par filtre echouee: {e}")

        # Si pas assez de resultats, fallback sur la recherche globale
        if len(results) < 3:
            try:
                response = self.notion.search(
                    query=query,
                    filter={"value": "page", "property": "object"},
                    page_size=max_results,
                )
                for page in response.get("results", []):
                    if page.get("parent", {}).get("database_id", "").replace("-", "") == self.db_id.replace("-", ""):
                        parsed = self._parse_single_page(page)
                        if parsed and parsed["name"] not in [r["name"] for r in results]:
                            results.append(parsed)
            except Exception as e:
                logger.warning(f"Recherche globale echouee: {e}")

        return results[:max_results]

    def search_by_category(self, category: str, max_results: int = 10) -> list[dict]:
        """Recherche toutes les entrees d'une categorie donnee."""
        try:
            response = self.notion.databases.query(
                database_id=self.db_id,
                filter={
                    "property": "Catégorie",
                    "select": {"equals": category},
                },
                page_size=max_results,
            )
            return self._parse_pages(response.get("results", []))
        except Exception as e:
            logger.error(f"Erreur recherche par categorie: {e}")
            return []

    def get_all_entries(self) -> list[dict]:
        """Recupere toutes les entrees de la KB (pour le cache)."""
        all_entries = []
        has_more = True
        start_cursor = None

        while has_more:
            kwargs = {"database_id": self.db_id, "page_size": 100}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor

            response = self.notion.databases.query(**kwargs)
            all_entries.extend(self._parse_pages(response.get("results", [])))
            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        return all_entries

    def _build_text_filter(self, query: str) -> dict:
        """
        Construit un filtre OR sur les champs textuels.
        Cherche dans : Name, Mots-cles, Description, Sous-categorie.
        """
        words = query.lower().split()
        # Prendre les 3 mots les plus significatifs (> 3 chars)
        keywords = [w for w in words if len(w) > 3][:3]
        if not keywords:
            keywords = words[:2]

        filters = []
        for kw in keywords:
            for prop in ["Mots-clés", "Description", "Name"]:
                filters.append({
                    "property": prop,
                    "rich_text" if prop != "Name" else "title": {
                        "contains": kw,
                    },
                })

        if len(filters) == 1:
            return filters[0]
        return {"or": filters}

    def _parse_pages(self, pages: list) -> list[dict]:
        """Parse une liste de pages Notion en dictionnaires KB."""
        results = []
        for page in pages:
            parsed = self._parse_single_page(page)
            if parsed:
                results.append(parsed)
        return results

    def _parse_single_page(self, page: dict) -> Optional[dict]:
        """Parse une page Notion en dictionnaire KB."""
        try:
            props = page.get("properties", {})
            return {
                "id": page["id"],
                "name": self._get_title(props.get("Name", {})),
                "categorie": self._get_select(props.get("Catégorie", {})),
                "sous_categorie": self._get_text(props.get("Sous-catégorie", {})),
                "description": self._get_text(props.get("Description", {})),
                "mots_cles": self._get_text(props.get("Mots-clés", {})),
                "process": self._get_text(props.get("Process de résolution", {})),
                "qui_resout": self._get_multi_select(props.get("Qui résout", {})),
                "action_crm": self._get_checkbox(props.get("Action CRM requise", {})),
                "lien": self._get_url(props.get("Lien process détaillé", {})),
                "confiance": self._get_select(props.get("Niveau de confiance", {})),
                "frequence": self._get_select(props.get("Fréquence", {})),
                "langue": self._get_select(props.get("Langue", {})),
                "url": page.get("url", ""),
            }
        except Exception as e:
            logger.warning(f"Erreur parsing page: {e}")
            return None

    @staticmethod
    def _get_title(prop: dict) -> str:
        items = prop.get("title", [])
        return items[0].get("plain_text", "") if items else ""

    @staticmethod
    def _get_text(prop: dict) -> str:
        items = prop.get("rich_text", [])
        return items[0].get("plain_text", "") if items else ""

    @staticmethod
    def _get_select(prop: dict) -> str:
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""

    @staticmethod
    def _get_multi_select(prop: dict) -> list[str]:
        items = prop.get("multi_select", [])
        return [item.get("name", "") for item in items]

    @staticmethod
    def _get_checkbox(prop: dict) -> bool:
        return prop.get("checkbox", False)

    @staticmethod
    def _get_url(prop: dict) -> str:
        return prop.get("url") or ""


def format_kb_entries_for_prompt(entries: list[dict]) -> str:
    """Formate les entrees KB pour injection dans le prompt Claude."""
    if not entries:
        return "Aucune entree KB trouvee pour cette question."

    parts = []
    for i, entry in enumerate(entries, 1):
        qui = ", ".join(entry.get("qui_resout", [])) or "Non defini"
        action_crm = "Oui" if entry.get("action_crm") else "Non"
        lien = entry.get("lien", "")
        lien_str = f"\n   Lien: {lien}" if lien else ""

        parts.append(
            f"### Entree {i}: {entry['name']}\n"
            f"   Categorie: {entry.get('categorie', 'N/A')} > {entry.get('sous_categorie', 'N/A')}\n"
            f"   Description: {entry.get('description', 'N/A')}\n"
            f"   Process: {entry.get('process', 'N/A')}\n"
            f"   Qui resout: {qui}\n"
            f"   Action CRM requise: {action_crm}\n"
            f"   Confiance KB: {entry.get('confiance', 'N/A')}\n"
            f"   Frequence: {entry.get('frequence', 'N/A')}"
            f"{lien_str}"
        )

    return "\n\n".join(parts)
