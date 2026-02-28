"""
Module d'intégration Google Calendar.
Gère l'authentification OAuth2, la lecture et l'écriture d'événements.
"""

import os
import json
from datetime import datetime, timedelta, date, time
from typing import List, Optional, Dict, Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ['https://www.googleapis.com/auth/calendar']


class OAuthError(Exception):
    pass


class GoogleCalendarManager:
    """Gestionnaire pour l'API Google Calendar."""

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
    ):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.creds = None

    def authenticate(self) -> bool:
        """
        Lance le flux OAuth2 et construit le service Calendar.
        Sauvegarde le token dans token_path pour les sessions futures.
        Retourne True si authentification réussie.
        """
        self.creds = None

        if os.path.exists(self.token_path):
            try:
                self.creds = Credentials.from_authorized_user_file(
                    self.token_path, SCOPES
                )
            except Exception:
                self.creds = None

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception:
                    self.creds = None

            if not self.creds:
                if not os.path.exists(self.credentials_path):
                    raise OAuthError(
                        f"Fichier credentials.json introuvable à '{self.credentials_path}'.\n"
                        "Veuillez suivre les instructions du README pour configurer Google Calendar."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            with open(self.token_path, "w") as token_file:
                token_file.write(self.creds.to_json())

        self.service = build("calendar", "v3", credentials=self.creds)
        return True

    def is_authenticated(self) -> bool:
        return self.service is not None

    def get_events(self, days_ahead: int = 30) -> List[Dict[str, Any]]:
        """
        Récupère les événements du calendrier principal pour les N prochains jours.
        """
        if not self.is_authenticated():
            raise OAuthError("Non authentifié. Appelez authenticate() d'abord.")

        now = datetime.utcnow().isoformat() + "Z"
        future = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"

        events_result = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                timeMax=future,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])

    def create_event(
        self,
        title: str,
        start_dt: datetime,
        end_dt: datetime,
        description: str = "",
        timezone: str = "Europe/Paris",
    ) -> Dict[str, Any]:
        """Crée un événement dans le calendrier principal."""
        if not self.is_authenticated():
            raise OAuthError("Non authentifié.")

        event_body = {
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": timezone,
            },
        }
        created = (
            self.service.events()
            .insert(calendarId="primary", body=event_body)
            .execute()
        )
        return created

    def parse_events_to_slots(self, events: List[Dict]) -> List[Dict]:
        """
        Convertit une liste d'événements Google Calendar en créneaux occupés
        (format dict compatible avec OccupiedSlot du scheduler).
        """
        slots = []
        for event in events:
            raw_start = event["start"].get("dateTime", event["start"].get("date"))
            raw_end = event["end"].get("dateTime", event["end"].get("date"))
            title = event.get("summary", "Événement")

            try:
                if "T" in raw_start:
                    start_dt = _parse_dt(raw_start)
                    end_dt = _parse_dt(raw_end)
                    slots.append(
                        {
                            "date": start_dt.date(),
                            "start_time": start_dt.time().replace(second=0, microsecond=0),
                            "end_time": end_dt.time().replace(second=0, microsecond=0),
                            "slot_type": "Google Calendar",
                            "title": title,
                        }
                    )
                # All-day events are ignored (no specific time)
            except Exception:
                continue

        return slots


def _parse_dt(raw: str) -> datetime:
    """Parse une chaîne ISO 8601 en datetime naïf (heure locale)."""
    # Supprimer le 'Z' ou le décalage timezone pour simplifier
    raw = raw.strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    if "+" in raw[10:]:
        raw = raw[: raw.rfind("+")]
    if raw.count("-") > 2:
        idx = raw.rfind("-")
        raw = raw[:idx]
    return datetime.fromisoformat(raw)
