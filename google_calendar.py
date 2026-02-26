#!/usr/bin/env python3
"""
Google Calendar Integration for Task Planner
"""

import os
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# If modifying these SCOPES, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/calendar.events']

class GoogleCalendarManager:
    """Handles Google Calendar integration"""
    
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def authenticate(self, credentials_file: str = 'credentials.json', token_file: str = 'token.pickle') -> bool:
        """Authenticate with Google Calendar API"""
        try:
            # Check if token file exists
            if os.path.exists(token_file):
                with open(token_file, 'rb') as token:
                    self.credentials = pickle.load(token)
            
            # If there are no (valid) credentials available, let the user log in.
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    self.credentials.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        credentials_file, SCOPES)
                    self.credentials = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(token_file, 'wb') as token:
                    pickle.dump(self.credentials, token)
            
            self.service = build('calendar', 'v3', credentials=self.credentials)
            return True
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return False
    
    def get_busy_slots(self, days: int = 7) -> List[Dict]:
        """Get busy slots from Google Calendar"""
        if not self.service:
            return []
        
        try:
            # Get today's date and calculate end date
            now = datetime.utcnow()
            end_date = now + timedelta(days=days)
            
            # Get events from primary calendar
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=now.isoformat() + 'Z',
                timeMax=end_date.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            busy_slots = []
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                if start and end:
                    busy_slots.append({
                        'start': start,
                        'end': end,
                        'summary': event.get('summary', 'Busy'),
                        'description': event.get('description', '')
                    })
            
            return busy_slots
            
        except Exception as e:
            print(f"Error getting busy slots: {e}")
            return []
    
    def add_event(self, title: str, start: datetime, end: datetime, description: str = "") -> bool:
        """Add an event to Google Calendar"""
        if not self.service:
            return False
        
        try:
            event = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start.isoformat(),
                    'timeZone': 'Europe/Paris',
                },
                'end': {
                    'dateTime': end.isoformat(),
                    'timeZone': 'Europe/Paris',
                },
                'reminders': {
                    'useDefault': True,
                },
            }
            
            created_event = self.service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            print(f"Event created: {created_event.get('htmlLink')}")
            return True
            
        except Exception as e:
            print(f"Error adding event: {e}")
            return False
    
    def add_multiple_events(self, events: List[Dict]) -> int:
        """Add multiple events to Google Calendar"""
        if not self.service:
            return 0
        
        success_count = 0
        for event_data in events:
            if self.add_event(
                event_data['title'],
                event_data['start'],
                event_data['end'],
                event_data.get('description', '')
            ):
                success_count += 1
        
        return success_count
    
    def get_calendar_list(self) -> List[Dict]:
        """Get list of available calendars"""
        if not self.service:
            return []
        
        try:
            calendar_list = self.service.calendarList().list().execute()
            return calendar_list.get('items', [])
        except Exception as e:
            print(f"Error getting calendar list: {e}")
            return []

def create_credentials_file():
    """Create a sample credentials.json file for Google API"""
    sample_credentials = {
        "installed": {
            "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
            "project_id": "your-project-id",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "YOUR_CLIENT_SECRET",
            "redirect_uris": ["http://localhost"]
        }
    }
    
    with open('credentials.json', 'w') as f:
        import json
        json.dump(sample_credentials, f, indent=2)
    
    print("Sample credentials.json file created. Please replace with your actual Google API credentials.")

if __name__ == "__main__":
    # Example usage
    calendar_manager = GoogleCalendarManager()
    
    # Check if credentials file exists
    if not os.path.exists('credentials.json'):
        print("No credentials.json file found.")
        create_credentials_file()
    else:
        # Try to authenticate
        if calendar_manager.authenticate():
            print("Successfully authenticated with Google Calendar!")
            
            # Get busy slots
            busy_slots = calendar_manager.get_busy_slots()
            print(f"Found {len(busy_slots)} busy slots in the next 7 days")
            
            # Example: Add an event
            # success = calendar_manager.add_event(
            #     "Test Event",
            #     datetime.now() + timedelta(hours=1),
            #     datetime.now() + timedelta(hours=2),
            #     "This is a test event"
            # )
            # print(f"Event creation {'successful' if success else 'failed'}")
        else:
            print("Authentication failed.")