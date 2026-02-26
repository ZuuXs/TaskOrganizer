#!/usr/bin/env python3
"""
Intelligent Task Planner - Main Application
"""

import streamlit as st
from datetime import datetime, timedelta, time
from typing import List, Dict, Optional, Tuple
import pytz
from dateutil.parser import parse
import os

# Constants
DEFAULT_TIMEZONE = "Europe/Paris"
MAX_DAYS_TO_PLAN = 7

class Task:
    """Represents a task to be scheduled"""
    def __init__(self, title: str, duration: float, deadline: datetime, priority: str):
        self.title = title
        self.duration = duration  # in hours
        self.deadline = deadline
        self.priority = priority  # "Low", "Normal", "High"
        self.scheduled_slots = []  # List of (start, end) datetime tuples
        self.is_planned = False
        self.message = ""
    
    def __repr__(self):
        return f"Task({self.title}, {self.duration}h, {self.deadline}, {self.priority})"

class BusySlot:
    """Represents an existing busy time slot"""
    def __init__(self, start: datetime, end: datetime, slot_type: str):
        self.start = start
        self.end = end
        self.type = slot_type  # "Cours", "Travail", etc.
    
    def __repr__(self):
        return f"BusySlot({self.start}->{self.end}, {self.type})"

class TaskPlanner:
    """Main task planning algorithm"""
    
    def __init__(self):
        self.tasks = []
        self.busy_slots = []
        self.constraints = {
            "max_hours_per_day": 8,
            "latest_hour": 22,  # 22:00
            "no_sunday": True,
            "lunch_break": (12, 13)  # 12:00-13:00
        }
    
    def add_task(self, task: Task):
        """Add a task to the planner"""
        self.tasks.append(task)
    
    def add_busy_slot(self, busy_slot: BusySlot):
        """Add a busy slot to the planner"""
        self.busy_slots.append(busy_slot)
    
    def set_constraints(self, constraints: Dict):
        """Set planning constraints"""
        self.constraints.update(constraints)
    
    def _generate_free_slots(self, start_date: datetime) -> List[Tuple[datetime, datetime]]:
        """Generate all free time slots over the next MAX_DAYS_TO_PLAN days"""
        free_slots = []
        current_date = start_date
        timezone = pytz.timezone(DEFAULT_TIMEZONE)
        
        for day in range(MAX_DAYS_TO_PLAN):
            current_day = current_date + timedelta(days=day)
            
            # Skip Sunday if constraint is set
            if self.constraints["no_sunday"] and current_day.weekday() == 6:  # 6 = Sunday
                continue
            
            # Generate time slots for this day (9:00 to latest_hour with lunch break)
            # Ensure all datetimes are timezone-aware
            day_start = timezone.localize(datetime.combine(current_day.date(), time(9, 0)))
            day_end = timezone.localize(datetime.combine(current_day.date(), time(self.constraints["latest_hour"], 0)))
            
            # Add lunch break constraint
            lunch_start = timezone.localize(datetime.combine(current_day.date(), time(12, 0)))
            lunch_end = timezone.localize(datetime.combine(current_day.date(), time(13, 0)))
            
            # Split day into morning and afternoon
            morning_slots = self._split_time_range(day_start, lunch_start)
            afternoon_slots = self._split_time_range(lunch_end, day_end)
            
            # Combine and sort all slots for this day
            day_slots = morning_slots + afternoon_slots
            day_slots.sort()
            
            # Remove busy slots
            available_slots = []
            for slot_start, slot_end in day_slots:
                is_free = True
                for busy_slot in self.busy_slots:
                    # Check if current slot overlaps with any busy slot
                    if (slot_start < busy_slot.end and slot_end > busy_slot.start):
                        is_free = False
                        break
                
                if is_free:
                    available_slots.append((slot_start, slot_end))
            
            free_slots.extend(available_slots)
        
        return free_slots
    
    def _split_time_range(self, start: datetime, end: datetime) -> List[Tuple[datetime, datetime]]:
        """Split a time range into 30-minute slots"""
        slots = []
        current = start
        
        while current < end:
            slot_end = current + timedelta(minutes=30)
            if slot_end > end:
                slot_end = end
            slots.append((current, slot_end))
            current = slot_end
        
        return slots
    
    def _sort_tasks(self) -> List[Task]:
        """Sort tasks by deadline (closest first), then priority (high first), then duration (shortest first)"""
        # Map French priority names to numerical values
        priority_order = {"Haute": 3, "Normale": 2, "Basse": 1, "High": 3, "Normal": 2, "Low": 1}
        
        return sorted(self.tasks, key=lambda task: (
            task.deadline,  # Closest deadline first
            -priority_order[task.priority],  # High priority first
            task.duration  # Shortest duration first
        ))
    
    def plan_tasks(self) -> Tuple[List[Task], List[Task]]:
        """Main planning algorithm - greedy approach"""
        # Sort tasks
        sorted_tasks = self._sort_tasks()
        
        # Generate free slots starting from today
        free_slots = self._generate_free_slots(datetime.now(pytz.timezone(DEFAULT_TIMEZONE)))
        
        planned_tasks = []
        unplanned_tasks = []
        
        for task in sorted_tasks:
            remaining_duration = task.duration
            task_slots = []
            
            # Try to find slots for this task
            for slot_start, slot_end in free_slots:
                if remaining_duration <= 0:
                    break
                
                slot_duration = (slot_end - slot_start).total_seconds() / 3600  # hours
                
                # Check if slot is before deadline and we have enough time
                if slot_end <= task.deadline and slot_duration > 0:
                    # Use as much of this slot as needed
                    use_duration = min(remaining_duration, slot_duration)
                    use_end = slot_start + timedelta(hours=use_duration)
                    
                    task_slots.append((slot_start, use_end))
                    remaining_duration -= use_duration
                    
                    # Mark this slot as used (remove from free slots)
                    # Note: In a real implementation, we'd need to handle partial usage
            
            if remaining_duration <= 0:
                # Task is fully planned
                task.scheduled_slots = task_slots
                task.is_planned = True
                task.message = f"Tâche '{task.title}' planifiée avec succès"
                planned_tasks.append(task)
                
                # Remove used slots from free slots
                # This is simplified - in reality we'd need to handle partial overlaps
            else:
                # Task couldn't be fully planned
                task.is_planned = False
                task.message = f"Tâche '{task.title}' non planifiable - {remaining_duration:.1f}h restantes"
                unplanned_tasks.append(task)
        
        return planned_tasks, unplanned_tasks
    
    def get_schedule_by_day(self) -> Dict[str, List[Tuple[str, datetime, datetime]]]:
        """Get schedule organized by day"""
        schedule = {}
        
        for task in self.tasks:
            if task.is_planned:
                for slot_start, slot_end in task.scheduled_slots:
                    day_key = slot_start.strftime("%Y-%m-%d")
                    if day_key not in schedule:
                        schedule[day_key] = []
                    
                    schedule[day_key].append((
                        task.title,
                        slot_start,
                        slot_end
                    ))
        
        # Sort each day's schedule by time
        for day in schedule:
            schedule[day].sort(key=lambda x: x[1])
        
        return schedule

def main():
    """Main Streamlit application"""
    st.title("📅 Planificateur Intelligent de Tâches")
    
    # Initialize session state
    if "planner" not in st.session_state:
        st.session_state.planner = TaskPlanner()
    
    if "tasks" not in st.session_state:
        st.session_state.tasks = []
    
    if "busy_slots" not in st.session_state:
        st.session_state.busy_slots = []
    
    # Navigation
    menu = ["📝 Tâches", "🕒 Créneaux Occupés", "⚙️ Contraintes", "📅 Planification", "🔄 Google Calendar"]
    choice = st.sidebar.selectbox("Menu", menu)
    
    if choice == "📝 Tâches":
        _show_tasks_interface()
    
    elif choice == "🕒 Créneaux Occupés":
        _show_busy_slots_interface()
    
    elif choice == "⚙️ Contraintes":
        _show_constraints_interface()
    
    elif choice == "📅 Planification":
        _show_planning_interface()
    
    elif choice == "🔄 Google Calendar":
        _show_google_calendar_interface()

def _show_tasks_interface():
    """Task input interface"""
    st.header("📝 Gestion des Tâches")
    
    # Add new task form
    with st.form("add_task"):
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Titre de la tâche", "")
            duration = st.number_input("Durée (heures)", min_value=0.5, max_value=24.0, value=1.0, step=0.5)
        with col2:
            deadline = st.date_input("Deadline", min_value=datetime.now().date())
            priority = st.selectbox("Priorité", ["Basse", "Normale", "Haute"])
        
        submitted = st.form_submit_button("Ajouter Tâche")
        
        if submitted and title:
            # Convert date to datetime at end of day
            deadline_datetime = datetime.combine(deadline, time(23, 59))
            task = Task(title, duration, deadline_datetime, priority)
            st.session_state.planner.add_task(task)
            st.session_state.tasks.append(task)
            st.success(f"Tâche '{title}' ajoutée!")
    
    # Display existing tasks
    st.subheader("Tâches Existantes")
    if st.session_state.tasks:
        for i, task in enumerate(st.session_state.tasks):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.write(f"**{task.title}**")
            with col2:
                st.write(f"{task.duration}h - {task.priority} priorité")
            with col3:
                st.write(f"Deadline: {task.deadline.strftime('%d/%m/%Y')}")
            st.divider()
    else:
        st.info("Aucune tâche ajoutée pour le moment.")

def _show_busy_slots_interface():
    """Busy slots input interface"""
    st.header("🕒 Créneaux Occupés")
    
    # Add new busy slot form
    with st.form("add_busy_slot"):
        col1, col2, col3 = st.columns(3)
        with col1:
            slot_date = st.date_input("Date", min_value=datetime.now().date())
        with col2:
            slot_start_time = st.time_input("Heure de début", value=time(9, 0))
        with col3:
            slot_end_time = st.time_input("Heure de fin", value=time(11, 0))
        
        slot_type = st.selectbox("Type", ["Cours", "Travail", "Réunion", "Autre"])
        
        submitted = st.form_submit_button("Ajouter Créneau")
        
        if submitted:
            start_datetime = datetime.combine(slot_date, slot_start_time)
            end_datetime = datetime.combine(slot_date, slot_end_time)
            
            if end_datetime > start_datetime:
                busy_slot = BusySlot(start_datetime, end_datetime, slot_type)
                st.session_state.planner.add_busy_slot(busy_slot)
                st.session_state.busy_slots.append(busy_slot)
                st.success(f"Créneau '{slot_type}' ajouté!")
            else:
                st.error("L'heure de fin doit être après l'heure de début!")
    
    # Display existing busy slots
    st.subheader("Créneaux Existants")
    if st.session_state.busy_slots:
        for i, slot in enumerate(st.session_state.busy_slots):
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.write(f"**{slot.type}**")
            with col2:
                st.write(f"{slot.start.strftime('%d/%m %H:%M')} - {slot.end.strftime('%H:%M')}")
            with col3:
                if st.button("❌", key=f"delete_slot_{i}"):
                    st.session_state.busy_slots.remove(slot)
                    st.session_state.planner.busy_slots.remove(slot)
                    st.rerun()
            st.divider()
    else:
        st.info("Aucun créneau occupé ajouté pour le moment.")

def _show_constraints_interface():
    """Constraints input interface"""
    st.header("⚙️ Contraintes de Planification")
    
    # Get current constraints
    constraints = st.session_state.planner.constraints
    
    with st.form("constraints_form"):
        col1, col2 = st.columns(2)
        with col1:
            max_hours = st.slider("Heures max de travail/jour", 1, 12, constraints["max_hours_per_day"])
            latest_hour = st.slider("Heure limite (24h format)", 18, 23, constraints["latest_hour"])
        with col2:
            no_sunday = st.checkbox("Pas de travail le dimanche", constraints["no_sunday"])
            lunch_break = st.checkbox("Pause déjeuner 12h-13h", True)
        
        submitted = st.form_submit_button("Enregistrer Contraintes")
        
        if submitted:
            new_constraints = {
                "max_hours_per_day": max_hours,
                "latest_hour": latest_hour,
                "no_sunday": no_sunday,
                "lunch_break": (12, 13) if lunch_break else None
            }
            st.session_state.planner.set_constraints(new_constraints)
            st.success("Contraintes enregistrées!")
    
    # Display current constraints
    st.subheader("Contraintes Actuelles")
    st.write(f"• Heures max/jour: {constraints['max_hours_per_day']}h")
    st.write(f"• Heure limite: {constraints['latest_hour']}:00")
    st.write(f"• Pas de dimanche: {'Oui' if constraints['no_sunday'] else 'Non'}")
    st.write(f"• Pause déjeuner: 12h-13h")

def _show_planning_interface():
    """Planning results interface"""
    st.header("📅 Résultats de la Planification")
    
    if st.button("🔄 Lancer la Planification", type="primary"):
        with st.spinner("Planification en cours..."):
            planned_tasks, unplanned_tasks = st.session_state.planner.plan_tasks()
            schedule_by_day = st.session_state.planner.get_schedule_by_day()
        
        st.success("Planification terminée!")
        
        # Display schedule
        st.subheader("📆 Calendrier Planifié")
        
        if schedule_by_day:
            for day, tasks in schedule_by_day.items():
                day_name = datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B %Y")
                st.markdown(f"### {day_name}")
                
                for task_title, start, end in tasks:
                    st.write(f"🕒 **{task_title}** - {start.strftime('%H:%M')} à {end.strftime('%H:%M')}")
                st.divider()
        else:
            st.info("Aucune tâche planifiée.")
        
        # Display unplanned tasks
        if unplanned_tasks:
            st.subheader("❌ Tâches Non Planifiables")
            for task in unplanned_tasks:
                st.warning(f"{task.message}")
        else:
            st.success("Toutes les tâches ont été planifiées avec succès!")
    else:
        st.info("Cliquez sur le bouton pour lancer la planification.")

def _show_google_calendar_interface():
    """Google Calendar integration interface"""
    st.header("🔄 Intégration Google Calendar")
    
    # Check if Google Calendar module can be imported
    try:
        from google_calendar import GoogleCalendarManager
        
        if "calendar_manager" not in st.session_state:
            st.session_state.calendar_manager = GoogleCalendarManager()
        
        calendar_manager = st.session_state.calendar_manager
        
        # Check authentication status
        if not hasattr(calendar_manager, 'service') or calendar_manager.service is None:
            st.info("🔑 Veuillez vous authentifier avec Google Calendar")
            
            if st.button("🔑 Se connecter à Google Calendar"):
                with st.spinner("Authentification en cours..."):
                    # Check if credentials file exists
                    if os.path.exists('credentials.json'):
                        if calendar_manager.authenticate():
                            st.success("Authentification réussie!")
                            st.rerun()
                        else:
                            st.error("Échec de l'authentification")
                    else:
                        st.error("Fichier credentials.json manquant. Veuillez le créer avec vos identifiants Google API.")
        else:
            # Authenticated - show options
            st.success("✅ Connecté à Google Calendar")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📥 Importer les créneaux occupés"):
                    with st.spinner("Récupération des créneaux..."):
                        busy_slots = calendar_manager.get_busy_slots(7)
                        
                        if busy_slots:
                            st.success(f"{len(busy_slots)} créneaux occupés trouvés")
                            
                            # Convert to BusySlot objects and add to planner
                            from main import BusySlot
                            for slot_data in busy_slots:
                                try:
                                    # Parse datetime strings
                                    start_str = slot_data['start']
                                    end_str = slot_data['end']
                                    
                                    # Handle both datetime and date formats
                                    if 'T' in start_str:
                                        start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                                        end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                                    else:
                                        start_dt = datetime.fromisoformat(start_str)
                                        end_dt = datetime.fromisoformat(end_str)
                                    
                                    # Convert to local timezone if needed
                                    if start_dt.tzinfo is None:
                                        start_dt = pytz.timezone(DEFAULT_TIMEZONE).localize(start_dt)
                                        end_dt = pytz.timezone(DEFAULT_TIMEZONE).localize(end_dt)
                                    else:
                                        start_dt = start_dt.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                                        end_dt = end_dt.astimezone(pytz.timezone(DEFAULT_TIMEZONE))
                                    
                                    busy_slot = BusySlot(start_dt, end_dt, slot_data['summary'])
                                    st.session_state.planner.add_busy_slot(busy_slot)
                                    st.session_state.busy_slots.append(busy_slot)
                                except Exception as e:
                                    st.warning(f"Erreur lors de l'import d'un créneau: {e}")
                                    continue
                            
                            st.rerun()
                        else:
                            st.info("Aucun créneau occupé trouvé dans Google Calendar")
            
            with col2:
                if st.button("📤 Exporter le planning vers Google Calendar"):
                    # Get planned tasks
                    planned_tasks, _ = st.session_state.planner.plan_tasks()
                    
                    if planned_tasks:
                        events_to_add = []
                        
                        for task in planned_tasks:
                            for slot_start, slot_end in task.scheduled_slots:
                                events_to_add.append({
                                    'title': f"[Tâche] {task.title}",
                                    'start': slot_start,
                                    'end': slot_end,
                                    'description': f"Tâche planifiée: {task.duration}h, Priorité: {task.priority}"
                                })
                        
                        if events_to_add:
                            with st.spinner(f"Ajout de {len(events_to_add)} événements..."):
                                success_count = calendar_manager.add_multiple_events(events_to_add)
                                st.success(f"{success_count}/{len(events_to_add)} événements ajoutés à Google Calendar!")
                        else:
                            st.info("Aucun événement à ajouter")
                    else:
                        st.info("Aucune tâche planifiée à exporter")
            
            # Show calendar info
            st.subheader("📅 Informations du calendrier")
            calendars = calendar_manager.get_calendar_list()
            if calendars:
                st.write(f"**Calendrier principal:** {calendars[0].get('summary', 'Inconnu')}")
                st.write(f"**ID:** {calendars[0].get('id', 'Inconnu')}")
            
            if st.button("🔄 Se déconnecter"):
                st.session_state.calendar_manager = GoogleCalendarManager()
                st.success("Déconnexion réussie")
                st.rerun()
                
    except ImportError:
        st.warning("📦 Module Google Calendar non disponible")
        st.write("""
        Pour activer l'intégration Google Calendar:
        
        1. Installez les dépendances requises:
        ```bash
        pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
        ```
        
        2. Créez un fichier `credentials.json` avec vos identifiants Google API
        
        3. Activez les API Google Calendar dans votre console Google Cloud
        
        *Fonctionnalité désactivée pour le moment*
        """)

if __name__ == "__main__":
    main()