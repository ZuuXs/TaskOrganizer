"""
Module d'intégration Perplexity API.
- Extraction de tâches depuis un prompt utilisateur
- Conseils de planification IA
"""

import os
import json
import re
import requests
from datetime import date, timedelta
from typing import Dict, Any, Optional


class PerplexityAPI:
    """Client pour l'API Perplexity (chat completions)."""

    BASE_URL = "https://api.perplexity.ai"
    DEFAULT_MODEL = "sonar"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "Clé API Perplexity manquante. "
                "Définissez PERPLEXITY_API_KEY dans le fichier .env ou via l'interface."
            )

    def _chat(self, messages: list, temperature: float = 0.1) -> str:
        """Appel générique à l'endpoint chat/completions."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.DEFAULT_MODEL,
            "messages": messages,
            "temperature": temperature,
        }
        resp = requests.post(
            f"{self.BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Erreur API Perplexity ({resp.status_code}): {resp.text[:500]}"
            )
        return resp.json()["choices"][0]["message"]["content"]

    def extract_tasks(self, prompt: str, today: Optional[date] = None) -> Dict[str, Any]:
        """
        Extrait les tâches depuis un prompt utilisateur.

        Retourne un dict :
        {
            "tasks": [
                {
                    "title": str,
                    "duration_hours": float,
                    "deadline": "YYYY-MM-DD",
                    "priority": "Basse" | "Normale" | "Haute",
                    "notes": str,
                    "exact_datetime": "YYYY-MM-DDTHH:MM" | null,
                    "recurrence": {"pattern": "daily"|"weekly", "end_date": "YYYY-MM-DD"} | null
                },
                ...
            ],
            "planning_suggestions": str
        }
        """
        if today is None:
            today = date.today()

        default_deadline = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        tomorrow = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        one_month = (today + timedelta(days=31)).strftime("%Y-%m-%d")

        system_prompt = f"""Tu es un extracteur de tâches JSON. TON SEUL RÔLE est d'extraire des tâches depuis le texte de l'utilisateur et de retourner du JSON.

RÈGLES ABSOLUES :
1. Retourne UNIQUEMENT un objet JSON valide. Zéro texte avant ou après.
2. NE JAMAIS expliquer les sujets mentionnés (nourriture, sport, médicaments, suppléments, etc.).
3. NE JAMAIS faire de recherche web ou ajouter des informations externes.
4. Si le texte dit "manger X", "prendre X", "faire X" → extrait-le comme une tâche avec title="X" ou "Manger X", point final.
5. Chaque tâche : title, duration_hours, deadline, priority, notes, exact_datetime, recurrence.

DURÉE si non précisée — estime :
- activité physique (sport, marche) = 1h
- repas, prise de complément = 0.5h
- rapport, document = 3h
- révision examen = 4h
- réunion, RDV = 1h

DEADLINE : date limite. Si exact_datetime est défini, utilise sa date. Sinon "{default_deadline}".

PRIORITÉ : exactement "Basse", "Normale", ou "Haute".

EXACT_DATETIME — si l'utilisateur précise une heure ("à 15h", "at 3pm", "ce soir 20h", "demain matin 9h") :
  → format "YYYY-MM-DDTHH:MM"
  → "demain à 15h" = "{tomorrow}T15:00"
  → "ce soir à 20h" = "{today.strftime('%Y-%m-%d')}T20:00"
  → sinon : null

RECURRENCE — si l'utilisateur dit "tous les jours", "chaque jour", "every day", "quotidien", "toutes les semaines" :
  → {{"pattern": "daily" ou "weekly", "end_date": "YYYY-MM-DD"}}
  → end_date max = {one_month}
  → si durée non précisée, end_date = dans 7 jours
  → sinon : null

Date d'aujourd'hui : {today.strftime("%d/%m/%Y")} ({today.strftime("%A")})

FORMAT JSON — SEULE RÉPONSE AUTORISÉE :
{{
    "tasks": [
        {{
            "title": "Titre de la tâche",
            "duration_hours": 1.0,
            "deadline": "YYYY-MM-DD",
            "priority": "Normale",
            "notes": "",
            "exact_datetime": null,
            "recurrence": null
        }}
    ],
    "planning_suggestions": "Conseil bref"
}}"""

        # Préfixe explicite pour contraindre l'IA à ne pas chercher sur le web
        user_message = f"Extrais les tâches de ce texte (JSON uniquement) :\n\n{prompt}"

        content = self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
        )

        return self._parse_json_response(content)

    def get_planning_advice(self, tasks_summary: str, schedule_summary: str) -> str:
        """
        Demande à Perplexity des conseils personnalisés sur le planning généré.
        """
        prompt = f"""En tant que coach de productivité, donne des conseils pratiques et motivants (3-5 points) pour ce planning de tâches.

TÂCHES À PLANIFIER :
{tasks_summary}

PLANNING PROPOSÉ :
{schedule_summary}

Réponds en français. Sois concis, positif et actionnable. Utilise des emojis pour rendre ça dynamique."""

        return self._chat([{"role": "user", "content": prompt}], temperature=0.7)

    def _parse_json_response(self, content: str) -> Dict[str, Any]:
        """Extrait et parse le JSON d'une réponse Perplexity (robuste aux textes parasites)."""
        content = content.strip()

        # 1. Chercher un bloc ```json ... ```
        json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_block:
            try:
                return json.loads(json_block.group(1))
            except json.JSONDecodeError:
                pass

        # 2. Extraction robuste par comptage de profondeur (gère le texte autour du JSON)
        start = content.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape_next = False
            for i, ch in enumerate(content[start:], start):
                if escape_next:
                    escape_next = False
                    continue
                if ch == "\\" and in_string:
                    escape_next = True
                    continue
                if ch == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(content[start : i + 1])
                            except json.JSONDecodeError:
                                # Essayer le prochain {
                                next_start = content.find("{", start + 1)
                                if next_start > start:
                                    start = next_start
                                    depth = 0
                                    in_string = False

        raise ValueError(
            f"Impossible de parser la réponse JSON. "
            f"L'IA a peut-être retourné du texte au lieu de JSON. "
            f"Réessayez ou reformulez votre demande. "
            f"(Réponse reçue : {content[:200]}...)"
        )
