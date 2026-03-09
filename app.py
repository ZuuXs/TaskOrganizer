"""
Planificateur Intelligent de Tâches
Application Streamlit principale.
"""

import os
import uuid
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

from google_calendar import GoogleCalendarManager, OAuthError
from perplexity_api import PerplexityAPI
from scheduler import (
    Constraints,
    OccupiedSlot,
    ScheduleResult,
    Task,
    TaskScheduler,
    PRIORITY_COLORS,
)

load_dotenv()

# ─── Configuration de la page ─────────────────────────────────────────────────

st.set_page_config(
    page_title="Planificateur Intelligent de Tâches",
    page_icon="🗓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS global ───────────────────────────────────────────────────────────────

st.markdown(
    """
<style>
/* Carte tâche */
.task-card {
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 10px;
    border-left: 5px solid;
    background: #f8f9fa;
}
.task-card.haute  { border-color: #1a5276; }
.task-card.normale{ border-color: #2980b9; }
.task-card.basse  { border-color: #aed6f1; }

/* Bloc calendrier */
.cal-block {
    border-radius: 6px;
    padding: 6px 10px;
    margin: 3px 0;
    font-size: 0.85em;
    color: white;
    font-weight: 500;
}
.cal-occupied { background: #e74c3c; }
.cal-task-haute  { background: #1a5276; }
.cal-task-normale{ background: #2980b9; }
.cal-task-basse  { background: #85c1e9; color: #1a252f; }

/* Badge priorité */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.78em;
    font-weight: bold;
    color: white;
    margin-left: 6px;
}
.badge-haute  { background: #1a5276; }
.badge-normale{ background: #2980b9; }
.badge-basse  { background: #85c1e9; color: #1a252f; }

/* Impossible */
.impossible-card {
    background: #fff5f5;
    border: 1px solid #feb2b2;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
}

/* Section headers */
.section-header {
    font-size: 1.1em;
    font-weight: 700;
    color: #2c3e50;
    margin: 12px 0 6px 0;
}

/* Google Calendar connected */
.gc-connected {
    background: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 8px;
    padding: 8px 14px;
    color: #155724;
}
.gc-disconnected {
    background: #fff3cd;
    border: 1px solid #ffeeba;
    border-radius: 8px;
    padding: 8px 14px;
    color: #856404;
}

/* Legend */
.legend-dot {
    display: inline-block;
    width: 14px;
    height: 14px;
    border-radius: 3px;
    margin-right: 5px;
    vertical-align: middle;
}
</style>
""",
    unsafe_allow_html=True,
)

# ─── Session State ─────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "tasks": [],                      # List[Task]
        "occupied_slots": [],             # List[OccupiedSlot]
        "schedule_result": None,          # ScheduleResult | None
        "gc_manager": None,               # GoogleCalendarManager | None
        "gc_events_raw": [],              # raw Google events
        "perplexity_key": os.getenv("PERPLEXITY_API_KEY", ""),
        "extraction_suggestions": "",
        "export_done": [],                # block_keys already exported
        "exported_blocks_detail": [],     # [{date, start_time, end_time, title}]
        "exported_task_ids": [],          # IDs de tâches entièrement exportées
        "ai_advice": "",
        "available_calendars": [],        # liste des agendas Google disponibles
        "selected_calendar_ids": [],      # IDs d'agendas à synchroniser
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _priority_badge(priority: str) -> str:
    cls = priority.lower()
    return f'<span class="badge badge-{cls}">{priority}</span>'


def _task_card_html(task: Task) -> str:
    cls = task.priority.lower()
    days_left = (task.deadline - date.today()).days
    if days_left < 0:
        urgency = "⚠️ Deadline dépassée"
    elif days_left == 0:
        urgency = "🔥 Deadline aujourd'hui !"
    elif days_left <= 2:
        urgency = f"⚡ Dans {days_left}j"
    else:
        urgency = f"📅 Dans {days_left}j"

    if task.pin_datetime:
        timing = f"📌 Fixé le {task.pin_datetime.strftime('%d/%m/%Y à %H:%M')}"
    else:
        timing = f"{urgency} ({task.deadline.strftime('%d/%m/%Y')})"

    recurring_badge = ' <span style="font-size:0.8em;color:#7f8c8d;">🔄 Récurrent</span>' if task.is_recurring else ""
    new_badge = ' <span style="font-size:0.78em;background:#f39c12;color:white;padding:1px 6px;border-radius:10px;">NEW</span>' if task.is_new else ""
    warning_html = (
        f'<br><span style="color:#e67e22;font-size:0.85em;">⚠️ {task.schedule_warning}</span>'
        if task.schedule_warning else ""
    )

    return f"""
<div class="task-card {cls}">
  <strong>{task.title}</strong>
  {_priority_badge(task.priority)}{recurring_badge}{new_badge}
  <br>
  ⏱️ {task.duration_hours:.1f}h &nbsp;|&nbsp; {timing}
  {warning_html}
  {"<br><em>" + task.notes + "</em>" if task.notes else ""}
</div>
"""


def _calendar_block_html(item: Dict) -> str:
    start = item["start_time"].strftime("%H:%M")
    end = item["end_time"].strftime("%H:%M")
    title = item.get("title", "")

    if item["type"] == "occupied":
        return f'<div class="cal-block cal-occupied">🔒 {start}-{end} — {title}</div>'
    else:
        prio = item.get("priority", "Normale").lower()
        icon = {"haute": "🔴", "normale": "🔵", "basse": "🟢"}.get(prio, "🔵")
        reason = item.get("reason", "")
        return (
            f'<div class="cal-block cal-task-{prio}" title="{reason}">'
            f'{icon} {start}-{end} — {title}'
            f"</div>"
        )


def _format_day_header(d: date) -> str:
    fr_days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    fr_months = [
        "", "Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
        "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc",
    ]
    wd = fr_days[d.weekday()]
    return f"{wd} {d.day} {fr_months[d.month]}"


def _get_perplexity() -> PerplexityAPI:
    key = st.session_state.perplexity_key.strip()
    if not key:
        raise ValueError("❌ Clé API Perplexity manquante. Saisissez-la dans la barre latérale.")
    return PerplexityAPI(api_key=key)


# ─── Sidebar — Contraintes & Clés API ─────────────────────────────────────────

with st.sidebar:
    st.title("🗓️ Planificateur Intelligent")
    st.markdown("---")

    st.subheader("🔑 Clés API")
    st.session_state.perplexity_key = st.text_input(
        "Clé Perplexity API",
        value=st.session_state.perplexity_key,
        type="password",
        help="Obtenez votre clé sur https://www.perplexity.ai/settings/api",
    )

    st.markdown("---")
    st.subheader("⚙️ Contraintes de travail")

    max_hours = st.slider(
        "⏰ Max heures/jour",
        min_value=1,
        max_value=14,
        value=8,
        help="Nombre maximum d'heures de travail par jour",
    )
    start_hour = st.slider("🌅 Début de journée", min_value=6, max_value=12, value=8)
    end_hour = st.slider(
        "🌙 Fin de journée (max 22h)", min_value=17, max_value=22, value=22
    )
    no_sunday = st.checkbox("🚫 Pas de travail le dimanche", value=True)
    lunch_break = st.checkbox("🍽️ Pause repas 12h-13h", value=True)

    constraints = Constraints(
        max_hours_per_day=float(max_hours),
        start_hour=start_hour,
        end_hour=end_hour,
        no_sunday=no_sunday,
        lunch_break=lunch_break,
    )

    st.markdown("---")
    st.markdown(
        """
**Légende couleurs :**
<div>
  <span class="legend-dot" style="background:#1a5276;"></span> Tâche priorité Haute<br>
  <span class="legend-dot" style="background:#2980b9;"></span> Tâche priorité Normale<br>
  <span class="legend-dot" style="background:#85c1e9;"></span> Tâche priorité Basse<br>
  <span class="legend-dot" style="background:#e74c3c;"></span> Créneau occupé<br>
</div>
""",
        unsafe_allow_html=True,
    )


# ─── Onglets principaux ────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    ["📝 Tâches", "📅 Créneaux Occupés", "🗓️ Planification", "✅ Exporter"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TÂCHES
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    st.header("📝 Mes Tâches")

    # ── Extraction via Perplexity ──
    with st.expander("🤖 Extraire des tâches depuis un prompt", expanded=True):
        prompt_text = st.text_area(
            "Décrivez vos tâches en langage naturel",
            placeholder=(
                "Ex : Je dois rendre mon rapport de stage avant vendredi, "
                "préparer une présentation pour lundi prochain (haute priorité, ~3h), "
                "et lire 2 articles scientifiques cette semaine."
            ),
            height=120,
        )
        if st.button("🚀 Extraire les tâches avec l'IA", use_container_width=True):
            if not prompt_text.strip():
                st.warning("Veuillez saisir un texte décrivant vos tâches.")
            else:
                with st.spinner("Analyse en cours via Perplexity..."):
                    try:
                        api = _get_perplexity()
                        result = api.extract_tasks(prompt_text)
                        extracted = result.get("tasks", [])
                        st.session_state.extraction_suggestions = result.get(
                            "planning_suggestions", ""
                        )
                        total_added = 0
                        for raw in extracted:
                            title = raw.get("title", "Tâche sans nom")
                            dur = float(raw.get("duration_hours", 2.0))
                            priority = raw.get("priority", "Normale")
                            notes = raw.get("notes", "")

                            # Deadline de base
                            try:
                                deadline = datetime.strptime(raw["deadline"], "%Y-%m-%d").date()
                            except Exception:
                                deadline = date.today() + timedelta(days=7)

                            # Heure exacte
                            exact_dt = None
                            if raw.get("exact_datetime"):
                                try:
                                    exact_dt = datetime.fromisoformat(raw["exact_datetime"])
                                    deadline = exact_dt.date()
                                except Exception:
                                    exact_dt = None

                            # Récurrence
                            recurrence = raw.get("recurrence")
                            if recurrence and recurrence.get("pattern"):
                                pattern = recurrence["pattern"]
                                try:
                                    end_date = datetime.strptime(recurrence["end_date"], "%Y-%m-%d").date()
                                except Exception:
                                    end_date = date.today() + timedelta(days=7)
                                end_date = min(end_date, date.today() + timedelta(days=31))
                                delta = timedelta(days=1) if pattern == "daily" else timedelta(weeks=1)
                                current_day = exact_dt.date() if exact_dt else date.today()
                                count = 0
                                while current_day <= end_date and count < 31:
                                    pin_dt = datetime.combine(current_day, exact_dt.time()) if exact_dt else None
                                    st.session_state.tasks.append(Task(
                                        title=title,
                                        duration_hours=dur,
                                        deadline=current_day,
                                        priority=priority,
                                        notes=notes,
                                        pin_datetime=pin_dt,
                                        not_before=current_day,  # récurrence : seulement ce jour
                                        is_recurring=True,
                                        recurrence_label=title,
                                    ))
                                    count += 1
                                    total_added += 1
                                    current_day += delta
                            else:
                                st.session_state.tasks.append(Task(
                                    title=title,
                                    duration_hours=dur,
                                    deadline=deadline,
                                    priority=priority,
                                    notes=notes,
                                    pin_datetime=exact_dt,
                                ))
                                total_added += 1

                        st.success(
                            f"✅ {total_added} tâche(s) extraite(s) et ajoutée(s) !"
                        )
                        if st.session_state.extraction_suggestions:
                            st.info(
                                f"💡 Suggestion IA : {st.session_state.extraction_suggestions}"
                            )
                    except Exception as e:
                        st.error(f"Erreur : {e}")

    # ── Liste des tâches ──
    st.markdown("---")
    total = len(st.session_state.tasks)
    new_count = sum(1 for t in st.session_state.tasks if t.is_new)
    st.subheader(f"📋 Tâches enregistrées ({total})")

    if not st.session_state.tasks:
        st.info("Aucune tâche pour le moment. Utilisez le prompt ci-dessus ou ajoutez une tâche manuellement.")

    # Grouper par statut : nouvelles vs déjà planifiées
    new_tasks_grp = [(i, t) for i, t in enumerate(st.session_state.tasks) if t.is_new]
    reg_tasks_grp = [(i, t) for i, t in enumerate(st.session_state.tasks) if not t.is_new]

    groups = []
    if new_tasks_grp:
        groups.append(("🆕 Nouvelles tâches — pas encore planifiées", "#fff9e6", "#f39c12", new_tasks_grp))
    if reg_tasks_grp:
        groups.append(("📅 Tâches du planning actuel", "#e8f4fd", "#2980b9", reg_tasks_grp))

    tasks_to_delete = []

    for group_label, bg, border, tasks_group in groups:
        st.markdown(
            f'<div style="background:{bg};border-left:4px solid {border};padding:8px 14px;'
            f'border-radius:6px;margin:12px 0 6px 0;">'
            f'<strong>{group_label}</strong> '
            f'<span style="color:#666;">({len(tasks_group)})</span></div>',
            unsafe_allow_html=True,
        )
        for idx, task in tasks_group:
            prio_icon = "🔴" if task.priority == "Haute" else "🔵" if task.priority == "Normale" else "🟢"
            recurring_tag = " 🔄" if task.is_recurring else ""
            pin_tag = f" 📌{task.pin_datetime.strftime('%d/%m %H:%M')}" if task.pin_datetime else f" — deadline {task.deadline.strftime('%d/%m/%Y')}"
            warn_tag = " ⚠️" if task.schedule_warning else ""
            with st.expander(
                f"{prio_icon}{recurring_tag}{warn_tag} {task.title} — {task.duration_hours:.1f}h{pin_tag}",
                expanded=False,
            ):
                if task.schedule_warning:
                    st.warning(f"⚠️ {task.schedule_warning}")
                col_a, col_b = st.columns(2)
                with col_a:
                    new_title = st.text_input(
                        "Titre", value=task.title, key=f"title_{task.id}"
                    )
                    new_dur = st.number_input(
                        "Durée (heures)",
                        min_value=0.1,
                        max_value=100.0,
                        value=task.duration_hours,
                        step=0.5,
                        key=f"dur_{task.id}",
                    )
                with col_b:
                    new_deadline = st.date_input(
                        "Deadline",
                        value=task.deadline,
                        key=f"dl_{task.id}",
                    )
                    new_priority = st.selectbox(
                        "Priorité",
                        ["Basse", "Normale", "Haute"],
                        index=["Basse", "Normale", "Haute"].index(task.priority),
                        key=f"prio_{task.id}",
                    )
                new_notes = st.text_input(
                    "Notes", value=task.notes, key=f"notes_{task.id}"
                )

                # Édition heure exacte
                st.markdown("**📌 Heure exacte**")
                ep1, ep2, ep3 = st.columns([1, 1, 2])
                with ep1:
                    keep_pin = st.checkbox(
                        "Heure fixée",
                        value=task.pin_datetime is not None,
                        key=f"pin_chk_{task.id}",
                    )
                with ep2:
                    edit_pin_date = st.date_input(
                        "Date",
                        value=task.pin_datetime.date() if task.pin_datetime else task.deadline,
                        key=f"pin_d_{task.id}",
                    )
                with ep3:
                    edit_pin_time = st.time_input(
                        "Heure",
                        value=task.pin_datetime.time() if task.pin_datetime else time(9, 0),
                        key=f"pin_t_{task.id}",
                    )

                col_save, col_del = st.columns([3, 1])
                with col_save:
                    if st.button("💾 Enregistrer", key=f"save_{task.id}"):
                        task.title = new_title
                        task.duration_hours = new_dur
                        task.deadline = new_deadline
                        task.priority = new_priority
                        task.notes = new_notes
                        if keep_pin:
                            task.pin_datetime = datetime.combine(edit_pin_date, edit_pin_time)
                            task.deadline = edit_pin_date
                        else:
                            task.pin_datetime = None
                        st.success("Tâche mise à jour !")
                        st.rerun()
                with col_del:
                    if st.button("🗑️ Supprimer", key=f"del_{task.id}"):
                        tasks_to_delete.append(idx)

    if tasks_to_delete:
        for i in sorted(tasks_to_delete, reverse=True):
            st.session_state.tasks.pop(i)
        st.rerun()

    # ── Ajout manuel ──
    st.markdown("---")
    st.subheader("➕ Ajouter une tâche manuellement")
    with st.form("add_task_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            m_title = st.text_input("Titre de la tâche *")
            m_dur = st.number_input("Durée estimée (h) *", min_value=0.5, max_value=100.0, value=2.0, step=0.5)
        with c2:
            m_deadline = st.date_input(
                "Deadline *", value=date.today() + timedelta(days=7)
            )
            m_priority = st.selectbox("Priorité", ["Normale", "Haute", "Basse"])
        m_notes = st.text_input("Notes (optionnel)")

        # Option heure exacte
        st.markdown("**📌 Heure exacte de début (optionnel)**")
        col_pin1, col_pin2, col_pin3 = st.columns([1, 1, 2])
        with col_pin1:
            m_use_pin = st.checkbox("Fixer date/heure exacte", value=False)
        with col_pin2:
            m_pin_date = st.date_input("Date exacte", value=date.today(), key="m_pin_date")
        with col_pin3:
            m_pin_time = st.time_input("Heure de début", value=time(9, 0), key="m_pin_time")

        submitted = st.form_submit_button("➕ Ajouter", use_container_width=True)
        if submitted:
            if not m_title.strip():
                st.error("Le titre est obligatoire.")
            else:
                pin_dt = datetime.combine(m_pin_date, m_pin_time) if m_use_pin else None
                # Si heure fixe, la deadline = la date exacte
                effective_deadline = m_pin_date if m_use_pin else m_deadline
                st.session_state.tasks.append(
                    Task(
                        title=m_title.strip(),
                        duration_hours=m_dur,
                        deadline=effective_deadline,
                        priority=m_priority,
                        notes=m_notes,
                        pin_datetime=pin_dt,
                    )
                )
                st.success(f"✅ Tâche '{m_title}' ajoutée !")
                st.rerun()

    # ── Tâches répétitives ──
    st.markdown("---")
    st.subheader("🔄 Ajouter une tâche répétitive")
    with st.expander("Créer une série de tâches récurrentes (max 1 mois)", expanded=False):
        with st.form("add_recurring_form", clear_on_submit=True):
            r_c1, r_c2 = st.columns(2)
            with r_c1:
                r_title = st.text_input("Titre de la tâche *", key="r_title")
                r_dur = st.number_input(
                    "Durée par session (h) *",
                    min_value=0.5, max_value=8.0, value=1.0, step=0.5, key="r_dur"
                )
                r_priority = st.selectbox(
                    "Priorité", ["Normale", "Haute", "Basse"], key="r_prio"
                )
            with r_c2:
                r_pattern = st.selectbox(
                    "Fréquence",
                    ["Tous les jours", "Toutes les semaines"],
                    key="r_pattern"
                )
                r_start = st.date_input(
                    "À partir du", value=date.today(), key="r_start"
                )
                r_end = st.date_input(
                    "Jusqu'au (max 1 mois)",
                    value=date.today() + timedelta(days=7),
                    max_value=date.today() + timedelta(days=31),
                    key="r_end"
                )

            st.markdown("**⏰ Heure fixe pour chaque occurrence (optionnel)**")
            r_col1, r_col2 = st.columns(2)
            with r_col1:
                r_use_time = st.checkbox("Fixer une heure de début", key="r_use_time")
            with r_col2:
                r_fixed_time = st.time_input("Heure de début", value=time(8, 0), key="r_fixed_time")

            r_notes = st.text_input("Notes (optionnel)", key="r_notes")

            r_submitted = st.form_submit_button("🔄 Créer les occurrences", use_container_width=True)
            if r_submitted:
                if not r_title.strip():
                    st.error("Le titre est obligatoire.")
                elif r_end < r_start:
                    st.error("La date de fin doit être après la date de début.")
                else:
                    delta = timedelta(days=1) if r_pattern == "Tous les jours" else timedelta(weeks=1)
                    max_date = min(r_end, r_start + timedelta(days=31))
                    current_day = r_start
                    count = 0
                    while current_day <= max_date:
                        pin_dt = (
                            datetime.combine(current_day, r_fixed_time)
                            if r_use_time else None
                        )
                        st.session_state.tasks.append(
                            Task(
                                title=r_title.strip(),
                                duration_hours=r_dur,
                                deadline=current_day,
                                priority=r_priority,
                                notes=r_notes,
                                pin_datetime=pin_dt,
                                not_before=current_day,  # récurrence : planifier seulement ce jour
                                is_recurring=True,
                                recurrence_label=r_title.strip(),
                            )
                        )
                        count += 1
                        current_day += delta
                    st.success(
                        f"✅ {count} occurrence(s) de '{r_title}' ajoutées ! "
                        f"({'avec heure fixe ' + r_fixed_time.strftime('%H:%M') if r_use_time else 'planification flexible'})"
                    )
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CRÉNEAUX OCCUPÉS
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    st.header("📅 Créneaux Occupés")

    # ── Google Calendar ──
    st.subheader("🔗 Google Calendar")

    gc = st.session_state.gc_manager

    if gc and gc.is_authenticated():
        st.markdown(
            '<div class="gc-connected">✅ Google Calendar connecté</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        # ── Chargement de la liste des agendas ──
        if not st.session_state.available_calendars:
            try:
                cals = gc.list_calendars()
                st.session_state.available_calendars = cals
                # Pré-sélectionner le calendrier principal
                if not st.session_state.selected_calendar_ids:
                    primary = next((c["id"] for c in cals if c.get("primary")), "primary")
                    st.session_state.selected_calendar_ids = [primary]
            except Exception:
                pass

        if st.session_state.available_calendars:
            cal_id_to_name = {c["id"]: c.get("summary", c["id"]) for c in st.session_state.available_calendars}
            cal_name_to_id = {v: k for k, v in cal_id_to_name.items()}
            all_names = list(cal_name_to_id.keys())
            default_names = [
                cal_id_to_name[cid]
                for cid in st.session_state.selected_calendar_ids
                if cid in cal_id_to_name
            ]
            selected_names = st.multiselect(
                "📆 Agendas à synchroniser",
                options=all_names,
                default=default_names,
                help="Sélectionnez les agendas dont vous voulez importer les événements comme créneaux occupés",
            )
            st.session_state.selected_calendar_ids = [cal_name_to_id[n] for n in selected_names]

        col_refresh, col_disconnect = st.columns(2)
        with col_refresh:
            if st.button("🔄 Synchroniser les événements"):
                with st.spinner("Récupération des événements..."):
                    try:
                        cal_ids = st.session_state.selected_calendar_ids or ["primary"]
                        if len(cal_ids) == 1 and cal_ids[0] == "primary":
                            events = gc.get_events(days_ahead=30)
                        else:
                            events = gc.get_events_from_calendars(cal_ids, days_ahead=30)
                        st.session_state.gc_events_raw = events
                        imported_slots = gc.parse_events_to_slots(events)
                        # Supprimer les anciens créneaux Google Calendar
                        st.session_state.occupied_slots = [
                            s for s in st.session_state.occupied_slots
                            if s.slot_type != "Google Calendar"
                        ]
                        for s_dict in imported_slots:
                            st.session_state.occupied_slots.append(
                                OccupiedSlot(**s_dict)
                            )
                        st.success(
                            f"✅ {len(imported_slots)} événement(s) importé(s) "
                            f"depuis {len(cal_ids)} agenda(s)."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur lors de la synchronisation : {e}")
        with col_disconnect:
            if st.button("🔌 Déconnecter"):
                st.session_state.gc_manager = None
                st.session_state.available_calendars = []
                st.session_state.selected_calendar_ids = []
                if os.path.exists("token.json"):
                    os.remove("token.json")
                st.rerun()
    else:
        st.markdown(
            '<div class="gc-disconnected">⚠️ Google Calendar non connecté</div>',
            unsafe_allow_html=True,
        )
        st.markdown("")
        credentials_path = st.text_input(
            "Chemin vers credentials.json",
            value=os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
        )
        if st.button("🔗 Connecter Google Calendar", use_container_width=True):
            try:
                manager = GoogleCalendarManager(
                    credentials_path=credentials_path,
                    token_path=os.getenv("GOOGLE_TOKEN_PATH", "token.json"),
                )
                with st.spinner(
                    "Ouverture du navigateur pour l'authentification Google..."
                ):
                    manager.authenticate()
                st.session_state.gc_manager = manager
                st.success("✅ Connecté à Google Calendar !")
                st.rerun()
            except OAuthError as e:
                st.error(str(e))
            except Exception as e:
                st.error(f"Erreur de connexion : {e}")

        with st.expander("ℹ️ Comment configurer Google Calendar ?"):
            st.markdown(
                """
1. Allez sur [Google Cloud Console](https://console.cloud.google.com/)
2. Créez un projet ou sélectionnez-en un existant
3. Activez l'**API Google Calendar**
4. Créez des **Identifiants OAuth 2.0** (application de bureau)
5. Téléchargez le fichier JSON → renommez-le `credentials.json`
6. Placez-le dans le dossier du projet
7. Cliquez sur **Connecter Google Calendar** ci-dessus
"""
            )

    # ── Créneaux Google Calendar importés ──
    gc_slots = [s for s in st.session_state.occupied_slots if s.slot_type == "Google Calendar"]
    if gc_slots:
        st.markdown(f"**{len(gc_slots)} créneau(x) importé(s) depuis Google Calendar :**")
        for s in gc_slots[:5]:
            st.markdown(
                f"🔴 **{s.title}** — {s.date.strftime('%d/%m/%Y')} "
                f"{s.start_time.strftime('%H:%M')}–{s.end_time.strftime('%H:%M')}"
            )
        if len(gc_slots) > 5:
            st.caption(f"... et {len(gc_slots)-5} autres.")

    # ── Créneaux manuels ──
    st.markdown("---")
    st.subheader("➕ Ajouter un créneau manuellement")
    with st.form("add_slot_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            s_date = st.date_input("Date *", value=date.today())
            s_type = st.selectbox(
                "Type", ["Cours", "Travail", "Rendez-vous", "Sport", "Autre"]
            )
        with c2:
            s_start = st.time_input("Heure début *", value=time(9, 0))
            s_title = st.text_input("Titre (optionnel)")
        with c3:
            s_end = st.time_input("Heure fin *", value=time(11, 0))

        submitted_slot = st.form_submit_button("➕ Ajouter le créneau", use_container_width=True)
        if submitted_slot:
            if s_end <= s_start:
                st.error("L'heure de fin doit être après l'heure de début.")
            else:
                st.session_state.occupied_slots.append(
                    OccupiedSlot(
                        date=s_date,
                        start_time=s_start,
                        end_time=s_end,
                        slot_type=s_type,
                        title=s_title or s_type,
                    )
                )
                st.success(f"✅ Créneau ajouté : {s_date.strftime('%d/%m/%Y')} {s_start.strftime('%H:%M')}–{s_end.strftime('%H:%M')}")
                st.rerun()

    # ── Liste tous les créneaux occupés ──
    manual_slots = [s for s in st.session_state.occupied_slots if s.slot_type != "Google Calendar"]
    if manual_slots:
        st.markdown("---")
        st.subheader(f"📋 Créneaux manuels ({len(manual_slots)})")
        slots_to_delete = []
        for idx, slot in enumerate(st.session_state.occupied_slots):
            if slot.slot_type == "Google Calendar":
                continue
            col_info, col_del = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"🔴 **{slot.title or slot.slot_type}** — "
                    f"{slot.date.strftime('%d/%m/%Y')} "
                    f"{slot.start_time.strftime('%H:%M')}–{slot.end_time.strftime('%H:%M')} "
                    f"*({slot.slot_type})*"
                )
            with col_del:
                if st.button("🗑️", key=f"del_slot_{slot.id}"):
                    slots_to_delete.append(idx)

        if slots_to_delete:
            for i in sorted(slots_to_delete, reverse=True):
                st.session_state.occupied_slots.pop(i)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PLANIFICATION
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.header("🗓️ Planification")

    # ── Bouton génération ──
    col_gen, col_advice = st.columns([2, 1])
    with col_gen:
        if st.button(
            "⚡ Générer le Planning",
            use_container_width=True,
            type="primary",
            disabled=len(st.session_state.tasks) == 0,
        ):
            if not st.session_state.tasks:
                st.warning("Ajoutez des tâches dans l'onglet 'Tâches' d'abord.")
            else:
                with st.spinner("Calcul du planning optimal..."):
                    # Exclure les tâches déjà exportées vers Google Calendar
                    exported_ids = set(st.session_state.exported_task_ids)
                    tasks_to_plan = [
                        t for t in st.session_state.tasks
                        if t.id not in exported_ids
                    ]
                    # Les blocs exportés bloquent les créneaux pour les autres tâches
                    exported_as_occupied = [
                        OccupiedSlot(
                            date=b["date"],
                            start_time=b["start_time"],
                            end_time=b["end_time"],
                            slot_type="Exporté",
                            title=b["title"],
                        )
                        for b in st.session_state.exported_blocks_detail
                    ]
                    scheduler = TaskScheduler(
                        tasks=tasks_to_plan,
                        occupied_slots=st.session_state.occupied_slots + exported_as_occupied,
                        constraints=constraints,
                    )
                    result_gen = scheduler.generate_schedule()
                    st.session_state.schedule_result = result_gen
                    st.session_state.ai_advice = ""

                    # Propager is_new=False et schedule_warning vers les tâches originales
                    all_processed = result_gen.scheduled_tasks + result_gen.impossible_tasks
                    warning_map = {t.id: t.schedule_warning for t in all_processed if t.schedule_warning}
                    processed_ids = {t.id for t in all_processed}
                    for task in st.session_state.tasks:
                        if task.id in processed_ids:
                            task.is_new = False
                        if task.id in warning_map:
                            task.schedule_warning = warning_map[task.id]
                        elif task.id in processed_ids:
                            task.schedule_warning = ""  # reset si re-généré sans warning
                st.success("✅ Planning généré !")
                st.rerun()

    with col_advice:
        if st.session_state.schedule_result and st.button(
            "🤖 Conseils IA", use_container_width=True
        ):
            with st.spinner("Consultation de l'IA..."):
                try:
                    api = _get_perplexity()
                    result = st.session_state.schedule_result
                    tasks_summary = "\n".join(
                        f"- {t.title} ({t.duration_hours}h, priorité {t.priority}, deadline {t.deadline})"
                        for t in st.session_state.tasks
                    )
                    schedule_summary = "\n".join(result.messages[:10])
                    st.session_state.ai_advice = api.get_planning_advice(
                        tasks_summary, schedule_summary
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur IA : {e}")

    result = st.session_state.schedule_result
    if not result:
        st.info("👆 Cliquez sur **Générer le Planning** pour calculer votre agenda.")
    else:
        # ── Statistiques ──
        st.markdown("---")
        warned_tasks = [t for t in result.scheduled_tasks if t.schedule_warning]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "✅ Tâches planifiées",
            len(result.scheduled_tasks),
            delta=f"dont {len(warned_tasks)} forcées ⚠️" if warned_tasks else None,
            delta_color="off" if warned_tasks else "normal",
        )
        k2.metric("❌ Non planifiables", len(result.impossible_tasks))
        k3.metric(
            "📅 Jours avec activité",
            len([d for d in result.calendar if result.calendar[d]]),
        )
        total_task_hours = sum(
            item["duration_hours"]
            for items in result.calendar.values()
            for item in items
            if item["type"] == "task"
        )
        k4.metric("⏱️ Total heures planifiées", f"{total_task_hours:.1f}h")

        # ── Conseils IA ──
        if st.session_state.ai_advice:
            st.markdown("---")
            with st.expander("🤖 Conseils de l'IA", expanded=True):
                st.markdown(st.session_state.ai_advice)

        # ── Messages explicatifs ──
        if result.messages:
            st.markdown("---")
            with st.expander(f"💬 Messages explicatifs ({len(result.messages)})", expanded=False):
                for msg in result.messages:
                    st.markdown(f"- {msg}")

        # ── Tâches partiellement forcées (≥80%) ──
        if warned_tasks:
            st.markdown("---")
            st.subheader(f"⚠️ Tâches planifiées avec moins de temps ({len(warned_tasks)})")
            st.caption("Ces tâches ont été retenues car elles sont planifiées à ≥80%. Il manque quelques créneaux.")
            for task in warned_tasks:
                st.markdown(
                    f"""<div style="background:#fff8e1;border:1px solid #f39c12;border-left:5px solid #f39c12;border-radius:8px;padding:10px 14px;margin-bottom:8px;">
<strong>⚠️ {task.title}</strong> {_priority_badge(task.priority)}<br>
<em style="color:#e67e22;">{task.schedule_warning}</em>
</div>""",
                    unsafe_allow_html=True,
                )

        # ── Tâches impossibles ──
        if result.impossible_tasks:
            st.markdown("---")
            st.subheader(f"❌ Tâches NON PLANIFIABLES ({len(result.impossible_tasks)})")
            for task in result.impossible_tasks:
                st.markdown(
                    f"""<div class="impossible-card">
<strong>❌ {task.title}</strong> — {task.duration_hours:.1f}h — deadline {task.deadline.strftime('%d/%m/%Y')}
{_priority_badge(task.priority)}<br>
<em>{task.impossible_reason}</em>
</div>""",
                    unsafe_allow_html=True,
                )

        # ── Vue calendrier ──
        st.markdown("---")
        st.subheader("📆 Calendrier")

        all_days = sorted(result.calendar.keys())
        if not all_days:
            st.info("Aucun événement à afficher.")
        else:
            if "week_offset" not in st.session_state:
                st.session_state.week_offset = 0

            today = date.today()
            week_start = today + timedelta(weeks=st.session_state.week_offset)
            week_start = week_start - timedelta(days=week_start.weekday())
            week_end = week_start + timedelta(days=6)

            nav_l, nav_label, nav_r = st.columns([1, 3, 1])
            with nav_l:
                if st.button("◀ Semaine préc."):
                    st.session_state.week_offset -= 1
                    st.rerun()
            with nav_label:
                st.markdown(
                    f"<div style='text-align:center;font-weight:700;font-size:1.1em;padding-top:6px;'>"
                    f"Semaine du {week_start.strftime('%d/%m/%Y')} au {week_end.strftime('%d/%m/%Y')}"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with nav_r:
                if st.button("Semaine suiv. ▶"):
                    st.session_state.week_offset += 1
                    st.rerun()

            week_days = [week_start + timedelta(days=i) for i in range(7)]
            if constraints.no_sunday:
                week_days = [d for d in week_days if d.weekday() != 6]

            cols = st.columns(len(week_days))
            for col, day in zip(cols, week_days):
                with col:
                    is_today = day == today
                    day_label = _format_day_header(day)
                    if is_today:
                        st.markdown(f"**🔆 {day_label}**", help="Aujourd'hui")
                    else:
                        st.markdown(f"**{day_label}**")

                    items = result.calendar.get(day, [])
                    if not items:
                        st.markdown(
                            '<div style="color:#aaa;font-size:0.8em;">Libre 🟢</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        for item in items:
                            st.markdown(_calendar_block_html(item), unsafe_allow_html=True)

            # ── Vue liste détaillée ──
            st.markdown("---")
            st.subheader("📋 Détail par jour")
            days_with_tasks = [
                d for d in sorted(result.calendar.keys())
                if any(i["type"] == "task" for i in result.calendar[d])
            ]
            for day in days_with_tasks:
                items = result.calendar[day]
                task_items = [i for i in items if i["type"] == "task"]
                if not task_items:
                    continue

                is_today = day == date.today()
                label = _format_day_header(day) + (" 🔆 Aujourd'hui" if is_today else "")
                with st.expander(
                    f"{label} — {len(task_items)} tâche(s)", expanded=(day == date.today())
                ):
                    for item in items:
                        st.markdown(_calendar_block_html(item), unsafe_allow_html=True)
                        if item["type"] == "task" and item.get("reason"):
                            st.caption(f"💡 {item['reason']}")

            # ── Suppression de tâches ──
            st.markdown("---")
            all_plan_tasks = result.scheduled_tasks + result.impossible_tasks
            if all_plan_tasks:
                with st.expander(f"🗑️ Supprimer des tâches du planning ({len(all_plan_tasks)})", expanded=False):
                    st.caption("Sélectionnez les tâches à supprimer définitivement, puis confirmez.")
                    task_options = {
                        f"{'✅' if t.is_scheduled else '❌'} {t.title} "
                        f"({'📌' if t.pin_datetime else '🔄' if t.is_recurring else '📅'} "
                        f"{t.deadline.strftime('%d/%m/%Y')}, {t.duration_hours:.1f}h)": t.id
                        for t in all_plan_tasks
                    }
                    selected_to_delete = st.multiselect(
                        "Tâches à supprimer",
                        options=list(task_options.keys()),
                        key="plan_delete_select",
                    )
                    if selected_to_delete:
                        ids_to_remove = {task_options[s] for s in selected_to_delete}
                        if st.button(
                            f"🗑️ Supprimer {len(selected_to_delete)} tâche(s)",
                            type="primary",
                            key="plan_delete_btn",
                        ):
                            st.session_state.tasks = [
                                t for t in st.session_state.tasks
                                if t.id not in ids_to_remove
                            ]
                            # Retirer aussi des listes d'export si nécessaire
                            st.session_state.exported_task_ids = [
                                tid for tid in st.session_state.exported_task_ids
                                if tid not in ids_to_remove
                            ]
                            st.session_state.schedule_result = None
                            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — EXPORTER
# ══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.header("✅ Exporter vers Google Calendar")

    result = st.session_state.schedule_result

    if not result:
        st.info("Générez d'abord un planning dans l'onglet '🗓️ Planification'.")
    elif not result.scheduled_tasks:
        st.warning("Aucune tâche planifiée à exporter.")
    else:
        gc = st.session_state.gc_manager
        if not gc or not gc.is_authenticated():
            st.warning(
                "⚠️ Google Calendar non connecté. "
                "Allez dans l'onglet '📅 Créneaux Occupés' pour vous connecter."
            )
        else:
            # Tâches disponibles à l'export (non encore exportées)
            exported_ids_set = set(st.session_state.exported_task_ids)
            exportable_tasks = [t for t in result.scheduled_tasks if t.id not in exported_ids_set]
            already_exported_count = len(result.scheduled_tasks) - len(exportable_tasks)

            if already_exported_count:
                st.success(f"✅ {already_exported_count} tâche(s) déjà exportée(s) vers Google Calendar.")
            st.info(
                f"**{len(exportable_tasks)} tâche(s) à exporter.** "
                "Sélectionnez les créneaux à ajouter à votre agenda Google."
            )

            # Sélection des blocs à exporter
            blocks_to_export = []
            for task in exportable_tasks:
                for block in task.scheduled_blocks:
                    block_key = f"{task.id}_{block['date']}_{block['start_time']}"
                    label = (
                        f"**{task.title}** — "
                        f"{block['date'].strftime('%d/%m/%Y')} "
                        f"{block['start_time'].strftime('%H:%M')}–{block['end_time'].strftime('%H:%M')} "
                        f"({block['duration_hours']:.1f}h)"
                    )
                    selected = st.checkbox(label, value=True, key=f"export_{block_key}")
                    if selected:
                        blocks_to_export.append((task, block, block_key))

            if blocks_to_export:
                st.markdown("---")
                if st.button(
                    f"📤 Exporter {len(blocks_to_export)} créneau(x) vers Google Calendar",
                    type="primary",
                    use_container_width=True,
                ):
                    success_count = 0
                    errors = []
                    progress = st.progress(0)
                    exported_in_session: set = set()
                    for i, (task, block, block_key) in enumerate(blocks_to_export):
                        try:
                            start_dt = datetime.combine(block["date"], block["start_time"])
                            end_dt = datetime.combine(block["date"], block["end_time"])
                            gc.create_event(
                                title=f"[Planificateur] {task.title}",
                                start_dt=start_dt,
                                end_dt=end_dt,
                                description=(
                                    f"Priorité : {task.priority}\n"
                                    f"Deadline : {task.deadline.strftime('%d/%m/%Y')}\n"
                                    f"{task.notes}"
                                ),
                            )
                            st.session_state.export_done.append(block_key)
                            exported_in_session.add(task.id)
                            # Mémoriser le bloc pour bloquer ce créneau à la prochaine génération
                            st.session_state.exported_blocks_detail.append({
                                "date": block["date"],
                                "start_time": block["start_time"],
                                "end_time": block["end_time"],
                                "title": f"[Exporté] {task.title}",
                            })
                            success_count += 1
                        except Exception as e:
                            errors.append(f"{task.title} : {e}")
                    # Marquer les tâches exportées par leur ID
                    for tid in exported_in_session:
                        if tid not in st.session_state.exported_task_ids:
                            st.session_state.exported_task_ids.append(tid)
                        progress.progress((i + 1) / len(blocks_to_export))

                    if success_count:
                        st.success(
                            f"🎉 {success_count} créneau(x) exporté(s) avec succès sur Google Calendar !"
                        )
                    if errors:
                        for err in errors:
                            st.error(f"Erreur : {err}")
                    st.rerun()
            else:
                st.success("✅ Tous les créneaux ont déjà été exportés !")

        # ── Résumé téléchargeable ──
        st.markdown("---")
        st.subheader("📄 Résumé du planning")
        summary_lines = [
            "PLANIFICATEUR INTELLIGENT DE TÂCHES",
            f"Généré le {date.today().strftime('%d/%m/%Y')}",
            "=" * 50,
            "",
            "TÂCHES PLANIFIÉES :",
        ]
        for task in result.scheduled_tasks:
            summary_lines.append(f"\n✅ {task.title} ({task.duration_hours:.1f}h — priorité {task.priority})")
            for block in task.scheduled_blocks:
                summary_lines.append(
                    f"   → {block['date'].strftime('%d/%m/%Y')} "
                    f"{block['start_time'].strftime('%H:%M')}–{block['end_time'].strftime('%H:%M')}"
                )

        if result.impossible_tasks:
            summary_lines += ["", "TÂCHES NON PLANIFIABLES :"]
            for task in result.impossible_tasks:
                summary_lines.append(f"\n❌ {task.title} — {task.impossible_reason}")

        summary_text = "\n".join(summary_lines)
        st.download_button(
            label="⬇️ Télécharger le résumé (.txt)",
            data=summary_text,
            file_name=f"planning_{date.today().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True,
        )
