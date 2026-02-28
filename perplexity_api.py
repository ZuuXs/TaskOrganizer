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
    DEFAULT_MODEL = "llama-3.1-sonar-small-128k-online"

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
                    "notes": str
                },
                ...
            ],
            "planning_suggestions": str
        }
        """
        if today is None:
            today = date.today()

        default_deadline = (today + timedelta(days=7)).strftime("%Y-%m-%d")

        system_prompt = f"""Tu es un assistant de planification expert. Analyse le texte de l'utilisateur et extrait toutes les tâches à accomplir.

RÈGLES STRICTES :
1. Retourne UNIQUEMENT un objet JSON valide, sans texte avant ou après.
2. Chaque tâche doit avoir : title, duration_hours, deadline, priority, notes.
3. duration_hours : si non précisé, estime selon la complexité (ex: "faire un rapport" = 3h, "réviser pour exam" = 6h, "lire un livre" = 5h, "coder un script" = 4h).
4. deadline : si non précisé, utilise "{default_deadline}" (1 semaine).
5. priority : EXACTEMENT "Basse", "Normale", ou "Haute". Si non précisé, estime selon le contexte (exam demain = Haute, etc.).
6. notes : résumé court des détails supplémentaires.
7. planning_suggestions : une phrase de conseil sur comment aborder ces tâches.

Date d'aujourd'hui : {today.strftime("%d/%m/%Y")} ({today.strftime("%A")})

FORMAT JSON ATTENDU :
{{
    "tasks": [
        {{
            "title": "Titre de la tâche",
            "duration_hours": 2.5,
            "deadline": "YYYY-MM-DD",
            "priority": "Haute",
            "notes": "Détails optionnels"
        }}
    ],
    "planning_suggestions": "Conseil de planification"
}}"""

        content = self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
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
        """Extrait et parse le JSON d'une réponse Perplexity."""
        # Essayer de trouver un bloc JSON dans la réponse
        content = content.strip()

        # Chercher un bloc ```json ... ``` ou ``` ... ```
        json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if json_block:
            return json.loads(json_block.group(1))

        # Chercher le JSON directement
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(content[json_start:json_end])

        raise ValueError(f"Impossible de parser la réponse JSON : {content[:300]}")
