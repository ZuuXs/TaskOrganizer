"""
Algorithme de planification greedy.

Flux :
  1. Tâches à heure fixe (pin_datetime) planifiées en priorité.
  2. Trie les tâches régulières (deadline proche → priorité haute → durée courte).
  3. Pour chaque tâche, parcourt les jours disponibles et remplit les créneaux libres.
  4. Les tâches non-planifiables sont marquées IMPOSSIBLE.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple


# ─── Structures de données ────────────────────────────────────────────────────

PRIORITY_VALUES = {"Haute": 3, "Normale": 2, "Basse": 1}
PRIORITY_COLORS = {
    "Haute": "#1a5276",   # bleu foncé
    "Normale": "#2980b9", # bleu moyen
    "Basse": "#aed6f1",   # bleu clair
}


@dataclass
class Task:
    title: str
    duration_hours: float
    deadline: date
    priority: str          # "Basse" | "Normale" | "Haute"
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Heure/date exacte imposée (la tâche DOIT commencer à ce moment)
    pin_datetime: Optional[datetime] = None

    # Marqueurs pour tâches répétitives
    is_recurring: bool = False
    recurrence_label: str = ""  # Titre de la série pour regroupement

    # Rempli après planification
    scheduled_blocks: List[Dict] = field(default_factory=list)
    is_scheduled: bool = False
    is_impossible: bool = False
    impossible_reason: str = ""

    def priority_value(self) -> int:
        return PRIORITY_VALUES.get(self.priority, 2)

    def scheduled_hours(self) -> float:
        return sum(b["duration_hours"] for b in self.scheduled_blocks)

    def remaining_hours(self) -> float:
        return max(0.0, self.duration_hours - self.scheduled_hours())

    def color(self) -> str:
        return PRIORITY_COLORS.get(self.priority, "#2980b9")


@dataclass
class OccupiedSlot:
    date: date
    start_time: time
    end_time: time
    slot_type: str = "Autre"
    title: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class Constraints:
    max_hours_per_day: float = 8.0
    start_hour: int = 8     # Pas de travail avant 8h
    end_hour: int = 22      # Pas de travail après 22h
    no_sunday: bool = True
    lunch_break: bool = True  # Pause repas 12h-13h


# ─── Résultat de planification ─────────────────────────────────────────────────

@dataclass
class ScheduleResult:
    # date → liste d'items (occupied ou task blocks)
    calendar: Dict[date, List[Dict]] = field(default_factory=dict)
    scheduled_tasks: List[Task] = field(default_factory=list)
    impossible_tasks: List[Task] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


# ─── Scheduler ────────────────────────────────────────────────────────────────

class TaskScheduler:
    """
    Planificateur greedy avec support des tâches à heure fixe.

    Paramètres
    ----------
    tasks          : liste des tâches à planifier
    occupied_slots : créneaux déjà occupés (Google Calendar + manuel + exports)
    constraints    : contraintes de travail
    horizon_days   : nombre de jours à planifier (défaut 30)
    """

    MIN_BLOCK_HOURS = 0.5  # Bloc minimum de 30 minutes

    def __init__(
        self,
        tasks: List[Task],
        occupied_slots: List[OccupiedSlot],
        constraints: Constraints,
        horizon_days: int = 30,
    ):
        self.tasks = [self._copy_task(t) for t in tasks]
        self.occupied_slots = occupied_slots
        self.constraints = constraints
        self.today = date.today()
        self.horizon_days = horizon_days

    def generate_schedule(self) -> ScheduleResult:
        result = ScheduleResult()

        # ── Séparer tâches fixes et tâches greedy ──────────────────────────────
        pinned_tasks = [t for t in self.tasks if t.pin_datetime is not None]
        regular_tasks = [t for t in self.tasks if t.pin_datetime is None]

        # ── 1. Planifier les tâches à heure fixe en premier ────────────────────
        pinned_occupied: List[Tuple[date, time, time]] = []
        for task in sorted(pinned_tasks, key=lambda t: t.pin_datetime):
            ok = self._schedule_pinned_task(task, result, pinned_occupied)
            if ok:
                task.is_scheduled = True
                task.is_impossible = False
                result.scheduled_tasks.append(task)
                p_date = task.pin_datetime.date()
                p_start = task.pin_datetime.time().replace(second=0, microsecond=0)
                p_end = _add_hours_to_time(p_start, task.duration_hours)
                pinned_occupied.append((p_date, p_start, p_end))
                result.messages.append(
                    f"📌 '{task.title}' → {task.pin_datetime.strftime('%d/%m à %H:%M')} "
                    f"({task.duration_hours:.1f}h)"
                )
            else:
                task.is_scheduled = False
                task.is_impossible = True
                result.impossible_tasks.append(task)
                result.messages.append(
                    f"❌ '{task.title}' (heure fixe) — IMPOSSIBLE : {task.impossible_reason}"
                )

        # ── 2. Pré-calculer les créneaux libres (excluant les blocs fixes) ─────
        free_slots: Dict[date, List[Tuple[time, time]]] = {}
        for i in range(self.horizon_days + 1):
            day = self.today + timedelta(days=i)
            if self._is_working_day(day):
                slots = self._compute_free_slots(day, pinned_occupied)
                if slots:
                    free_slots[day] = slots

        # ── 3. Trier et planifier les tâches régulières (greedy) ───────────────
        sorted_tasks = self._sort_tasks(regular_tasks)

        for task in sorted_tasks:
            days_in_order = sorted(free_slots.keys())

            for day in days_in_order:
                if day > task.deadline:
                    break

                if task.remaining_hours() < 0.01:
                    break

                already_used = self._task_hours_on_day(result.calendar, day)
                available_today = self.constraints.max_hours_per_day - already_used
                if available_today < self.MIN_BLOCK_HOURS:
                    continue

                updated_slots = []
                for slot_start, slot_end in free_slots[day]:
                    if task.remaining_hours() < 0.01 or available_today < self.MIN_BLOCK_HOURS:
                        updated_slots.append((slot_start, slot_end))
                        continue

                    slot_dur = _time_diff_hours(slot_start, slot_end)
                    if slot_dur < self.MIN_BLOCK_HOURS:
                        updated_slots.append((slot_start, slot_end))
                        continue

                    use = min(task.remaining_hours(), slot_dur, available_today)
                    if use < self.MIN_BLOCK_HOURS:
                        updated_slots.append((slot_start, slot_end))
                        continue

                    block_end = _add_hours_to_time(slot_start, use)

                    block = {
                        "type": "task",
                        "task_id": task.id,
                        "title": task.title,
                        "start_time": slot_start,
                        "end_time": block_end,
                        "duration_hours": use,
                        "priority": task.priority,
                        "color": task.color(),
                        "reason": _build_reason(task, day),
                    }

                    if day not in result.calendar:
                        result.calendar[day] = []
                    result.calendar[day].append(block)

                    task.scheduled_blocks.append(
                        {"date": day, "start_time": slot_start, "end_time": block_end, "duration_hours": use}
                    )
                    result.messages.append(
                        f"✅ '{task.title}' → {day.strftime('%d/%m')} "
                        f"{slot_start.strftime('%H:%M')}-{block_end.strftime('%H:%M')} "
                        f"({_build_reason(task, day)})"
                    )

                    available_today -= use

                    if block_end < slot_end:
                        updated_slots.append((block_end, slot_end))

                free_slots[day] = updated_slots

            # Verdict final
            if task.remaining_hours() < 0.01:
                task.is_scheduled = True
                task.is_impossible = False
                result.scheduled_tasks.append(task)
            elif task.scheduled_hours() > 0:
                task.is_scheduled = False
                task.is_impossible = True
                task.impossible_reason = (
                    f"Seulement {task.scheduled_hours():.1f}h/{task.duration_hours:.1f}h planifiées "
                    f"avant la deadline du {task.deadline.strftime('%d/%m/%Y')}."
                )
                result.impossible_tasks.append(task)
                result.messages.append(
                    f"⚠️ '{task.title}' partiellement planifiée "
                    f"({task.scheduled_hours():.1f}h/{task.duration_hours:.1f}h) — NON PLANIFIABLE entièrement."
                )
            else:
                task.is_scheduled = False
                task.is_impossible = True
                task.impossible_reason = self._explain_impossible(task, free_slots)
                result.impossible_tasks.append(task)
                result.messages.append(
                    f"❌ '{task.title}' — NON PLANIFIABLE : {task.impossible_reason}"
                )

        # ── 4. Ajouter les créneaux occupés au calendrier ──────────────────────
        for slot in self.occupied_slots:
            if slot.date not in result.calendar:
                result.calendar[slot.date] = []
            result.calendar[slot.date].append(
                {
                    "type": "occupied",
                    "title": slot.title or slot.slot_type,
                    "slot_type": slot.slot_type,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "color": "#e74c3c",
                }
            )

        # ── 5. Trier chaque journée par heure de début ─────────────────────────
        for day in result.calendar:
            result.calendar[day].sort(key=lambda x: x["start_time"])

        return result

    # ─── Planification à heure fixe ───────────────────────────────────────────

    def _schedule_pinned_task(
        self,
        task: Task,
        result: ScheduleResult,
        pinned_occupied: List[Tuple[date, time, time]],
    ) -> bool:
        """Planifie une tâche à heure fixe. Retourne True si succès."""
        pin_date = task.pin_datetime.date()
        pin_start = task.pin_datetime.time().replace(second=0, microsecond=0)
        pin_end = _add_hours_to_time(pin_start, task.duration_hours)

        # Vérifier plage horaire autorisée
        if pin_start < time(self.constraints.start_hour, 0) or pin_end > time(self.constraints.end_hour, 0):
            task.impossible_reason = (
                f"Heure hors plage de travail "
                f"({self.constraints.start_hour}h–{self.constraints.end_hour}h)"
            )
            return False

        # Vérifier conflits avec créneaux occupés
        for occ in self.occupied_slots:
            if occ.date == pin_date:
                if not (pin_end <= occ.start_time or pin_start >= occ.end_time):
                    task.impossible_reason = (
                        f"Conflit avec '{occ.title or occ.slot_type}' "
                        f"({occ.start_time.strftime('%H:%M')}–{occ.end_time.strftime('%H:%M')})"
                    )
                    return False

        # Vérifier conflits avec tâches fixes déjà planifiées
        for p_date, p_start, p_end in pinned_occupied:
            if p_date == pin_date:
                if not (pin_end <= p_start or pin_start >= p_end):
                    task.impossible_reason = (
                        f"Conflit avec une autre tâche fixe "
                        f"({p_start.strftime('%H:%M')}–{p_end.strftime('%H:%M')})"
                    )
                    return False

        # Planifier le bloc
        block = {
            "type": "task",
            "task_id": task.id,
            "title": task.title,
            "start_time": pin_start,
            "end_time": pin_end,
            "duration_hours": task.duration_hours,
            "priority": task.priority,
            "color": task.color(),
            "reason": f"📌 Heure fixée — {_build_reason(task, pin_date)}",
        }

        if pin_date not in result.calendar:
            result.calendar[pin_date] = []
        result.calendar[pin_date].append(block)

        task.scheduled_blocks.append({
            "date": pin_date,
            "start_time": pin_start,
            "end_time": pin_end,
            "duration_hours": task.duration_hours,
        })
        return True

    # ─── Helpers privés ───────────────────────────────────────────────────────

    def _sort_tasks(self, tasks: Optional[List[Task]] = None) -> List[Task]:
        """Trie : deadline proche → priorité haute → durée courte."""
        t = tasks if tasks is not None else self.tasks

        def key(t_: Task):
            days_left = (t_.deadline - self.today).days
            return (days_left, -t_.priority_value(), t_.duration_hours)

        return sorted(t, key=key)

    def _is_working_day(self, d: date) -> bool:
        if self.constraints.no_sunday and d.weekday() == 6:
            return False
        return True

    def _compute_free_slots(
        self,
        d: date,
        pinned_occupied: Optional[List[Tuple[date, time, time]]] = None,
    ) -> List[Tuple[time, time]]:
        """Calcule les créneaux libres d'une journée (contraintes + occupés + fixes)."""
        s = time(self.constraints.start_hour, 0)
        e = time(self.constraints.end_hour, 0)
        slots = [(s, e)]

        if self.constraints.lunch_break:
            slots = _subtract_range(slots, time(12, 0), time(13, 0))

        for occ in self.occupied_slots:
            if occ.date == d:
                slots = _subtract_range(slots, occ.start_time, occ.end_time)

        # Soustraire les blocs de tâches fixes déjà planifiées
        if pinned_occupied:
            for p_date, p_start, p_end in pinned_occupied:
                if p_date == d:
                    slots = _subtract_range(slots, p_start, p_end)

        return [(a, b) for a, b in slots if _time_diff_hours(a, b) >= self.MIN_BLOCK_HOURS]

    def _task_hours_on_day(self, calendar: Dict[date, List[Dict]], d: date) -> float:
        if d not in calendar:
            return 0.0
        return sum(
            item["duration_hours"]
            for item in calendar[d]
            if item["type"] == "task"
        )

    def _explain_impossible(self, task: Task, free_slots: Dict[date, List[Tuple[time, time]]]) -> str:
        total_free = sum(
            sum(_time_diff_hours(s, e) for s, e in slots)
            for d, slots in free_slots.items()
            if d <= task.deadline
        )
        if total_free < task.duration_hours:
            return (
                f"Pas assez de créneaux libres avant le {task.deadline.strftime('%d/%m/%Y')} "
                f"({total_free:.1f}h disponibles, {task.duration_hours:.1f}h nécessaires)."
            )
        return f"Deadline dépassée ou planning surchargé avant le {task.deadline.strftime('%d/%m/%Y')}."

    @staticmethod
    def _copy_task(t: Task) -> Task:
        return Task(
            title=t.title,
            duration_hours=t.duration_hours,
            deadline=t.deadline,
            priority=t.priority,
            notes=t.notes,
            id=t.id,
            pin_datetime=t.pin_datetime,
            is_recurring=t.is_recurring,
            recurrence_label=t.recurrence_label,
        )


# ─── Utilitaires temps ─────────────────────────────────────────────────────────

def _time_diff_hours(a: time, b: time) -> float:
    """Différence en heures entre deux time (b - a). Retourne 0 si b <= a."""
    minutes = (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)
    return max(0.0, minutes / 60.0)


def _add_hours_to_time(t: time, hours: float) -> time:
    """Ajoute des heures à un time (sans dépasser minuit)."""
    total_minutes = t.hour * 60 + t.minute + int(round(hours * 60))
    total_minutes = min(total_minutes, 23 * 60 + 59)
    return time(total_minutes // 60, total_minutes % 60)


def _subtract_range(
    slots: List[Tuple[time, time]], rem_start: time, rem_end: time
) -> List[Tuple[time, time]]:
    """Soustrait un intervalle [rem_start, rem_end] d'une liste de créneaux libres."""
    result = []
    for s, e in slots:
        if rem_end <= s or rem_start >= e:
            result.append((s, e))
        elif rem_start <= s and rem_end >= e:
            pass  # entièrement recouvert
        elif rem_start > s and rem_end < e:
            result.append((s, rem_start))
            result.append((rem_end, e))
        elif rem_start <= s:
            if rem_end < e:
                result.append((rem_end, e))
        else:
            result.append((s, rem_start))
    return result


def _build_reason(task: Task, day: date) -> str:
    days_left = (task.deadline - day).days
    if days_left <= 1:
        urgency = "deadline DEMAIN"
    elif days_left <= 3:
        urgency = f"deadline dans {days_left}j"
    else:
        urgency = f"deadline le {task.deadline.strftime('%d/%m')}"
    return f"priorité {task.priority}, {urgency}"
