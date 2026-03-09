"""
Algorithme de planification greedy — approche "day-first".

Flux :
  1. Tâches à heure fixe (pin_datetime) planifiées en priorité.
  2. Pour chaque JOUR (et non tâche par tâche), distribue le temps entre toutes
     les tâches urgentes selon un budget quotidien intelligent.
  3. Les tâches récurrentes (not_before = deadline) ne sont planifiées que leur jour.
  4. Pauses automatiques de 15 min après les blocs ≥ 1h30.
  5. Les tâches non-planifiables sont marquées IMPOSSIBLE.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple


# ─── Structures de données ────────────────────────────────────────────────────

PRIORITY_VALUES = {"Haute": 3, "Normale": 2, "Basse": 1}
PRIORITY_COLORS = {
    "Haute": "#1a5276",
    "Normale": "#2980b9",
    "Basse": "#aed6f1",
}


@dataclass
class Task:
    title: str
    duration_hours: float
    deadline: date
    priority: str          # "Basse" | "Normale" | "Haute"
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Heure/date exacte imposée (ignore les contraintes horaires)
    pin_datetime: Optional[datetime] = None

    # Pas de planification avant cette date (utilisé pour les récurrences)
    not_before: Optional[date] = None

    # Marqueurs récurrence
    is_recurring: bool = False
    recurrence_label: str = ""

    # Statut UI (non copié dans le scheduler — mis à jour depuis app.py)
    is_new: bool = True          # True = ajoutée depuis le dernier planning
    schedule_warning: str = ""   # Avertissement si planifiée à ≥80% (temps partiel forcé)

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
    start_hour: int = 8
    end_hour: int = 22
    no_sunday: bool = True
    lunch_break: bool = True


# ─── Résultat de planification ─────────────────────────────────────────────────

@dataclass
class ScheduleResult:
    calendar: Dict[date, List[Dict]] = field(default_factory=dict)
    scheduled_tasks: List[Task] = field(default_factory=list)
    impossible_tasks: List[Task] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)


# ─── Scheduler ────────────────────────────────────────────────────────────────

class TaskScheduler:
    """
    Planificateur greedy — approche "day-first".

    Pour chaque jour, distribue le temps disponible entre TOUTES les tâches
    éligibles selon un budget quotidien intelligent. Cela évite qu'une seule
    tâche monopolise une journée entière.
    """

    MIN_BLOCK_HOURS = 0.5        # Bloc minimum : 30 min
    MAX_TASK_DAILY_HOURS = 4.0   # Max heures de la même tâche par jour
    BREAK_THRESHOLD_HOURS = 1.5  # Pause après un bloc ≥ 1h30
    BREAK_DURATION_HOURS = 0.25  # Pause de 15 min

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

        # ── Séparer tâches fixes et tâches greedy ─────────────────────────────
        pinned_tasks = [t for t in self.tasks if t.pin_datetime is not None]
        regular_tasks = [t for t in self.tasks if t.pin_datetime is None]

        # ── 1. Planifier les tâches à heure fixe en premier ───────────────────
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

        # ── 2. Pré-calculer les créneaux libres ───────────────────────────────
        free_slots: Dict[date, List[Tuple[time, time]]] = {}
        for i in range(self.horizon_days + 1):
            day = self.today + timedelta(days=i)
            if self._is_working_day(day):
                slots = self._compute_free_slots(day, pinned_occupied)
                if slots:
                    free_slots[day] = list(slots)

        # ── 3. Greedy day-first : chaque jour distribue entre plusieurs tâches ─
        sorted_tasks = self._sort_tasks(regular_tasks)

        for day in sorted(free_slots.keys()):
            if not free_slots[day]:
                continue

            already_used = self._task_hours_on_day(result.calendar, day)
            available_today = self.constraints.max_hours_per_day - already_used
            if available_today < self.MIN_BLOCK_HOURS:
                continue

            # Copie mutable des créneaux libres du jour (partagée entre les tâches)
            day_free = list(free_slots[day])

            for task in sorted_tasks:
                if task.remaining_hours() < 0.01:
                    continue
                if day > task.deadline:
                    continue
                # Filtre not_before (tâches récurrentes : seulement leur jour)
                if task.not_before is not None and day < task.not_before:
                    continue
                if available_today < self.MIN_BLOCK_HOURS:
                    break

                # Budget quotidien intelligent
                days_until_dl = max(1, (task.deadline - day).days + 1)
                ideal_daily = task.remaining_hours() / days_until_dl
                # Minimum requis aujourd'hui pour respecter la deadline
                min_needed = max(
                    0.0,
                    task.remaining_hours() - (days_until_dl - 1) * self.MAX_TASK_DAILY_HOURS,
                )
                # Plafond normal : 2× l'idéal mais max MAX_TASK_DAILY_HOURS
                normal_cap = max(
                    self.MIN_BLOCK_HOURS,
                    min(ideal_daily * 2.0, self.MAX_TASK_DAILY_HOURS),
                )
                daily_cap = min(
                    max(min_needed, normal_cap),
                    task.remaining_hours(),
                    available_today,
                )

                if daily_cap < self.MIN_BLOCK_HOURS:
                    continue

                allocated = 0.0
                new_day_free: List[Tuple[time, time]] = []

                for slot_start, slot_end in day_free:
                    budget_left = daily_cap - allocated
                    if budget_left < self.MIN_BLOCK_HOURS or available_today < self.MIN_BLOCK_HOURS:
                        new_day_free.append((slot_start, slot_end))
                        continue

                    slot_dur = _time_diff_hours(slot_start, slot_end)
                    if slot_dur < self.MIN_BLOCK_HOURS:
                        new_day_free.append((slot_start, slot_end))
                        continue

                    use = min(budget_left, slot_dur, available_today)
                    if use < self.MIN_BLOCK_HOURS:
                        new_day_free.append((slot_start, slot_end))
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

                    result.calendar.setdefault(day, []).append(block)
                    task.scheduled_blocks.append({
                        "date": day,
                        "start_time": slot_start,
                        "end_time": block_end,
                        "duration_hours": use,
                    })
                    result.messages.append(
                        f"✅ '{task.title}' → {day.strftime('%d/%m')} "
                        f"{slot_start.strftime('%H:%M')}-{block_end.strftime('%H:%M')} "
                        f"({_build_reason(task, day)})"
                    )

                    allocated += use
                    available_today -= use

                    # Pause intelligente après un long bloc
                    if use >= self.BREAK_THRESHOLD_HOURS:
                        pause_end = _add_hours_to_time(block_end, self.BREAK_DURATION_HOURS)
                        if pause_end < slot_end:
                            new_day_free.append((pause_end, slot_end))
                        # sinon le créneau est entièrement consommé (pause incluse)
                    else:
                        if block_end < slot_end:
                            new_day_free.append((block_end, slot_end))

                day_free = new_day_free

            free_slots[day] = day_free

        # ── 4. Verdict final pour chaque tâche régulière ──────────────────────
        FORCE_THRESHOLD = 0.80  # ≥80% planifié → forcer comme planifié

        for task in sorted_tasks:
            if task.remaining_hours() < 0.01:
                task.is_scheduled = True
                task.is_impossible = False
                result.scheduled_tasks.append(task)
            elif task.scheduled_hours() > 0:
                pct = task.scheduled_hours() / task.duration_hours
                if pct >= FORCE_THRESHOLD:
                    # ≥80% → forcer comme planifié, ajouter un avertissement
                    task.is_scheduled = True
                    task.is_impossible = False
                    task.schedule_warning = (
                        f"{task.scheduled_hours():.1f}h/{task.duration_hours:.1f}h planifiées "
                        f"({pct:.0%}) — pas assez de créneaux disponibles avant le "
                        f"{task.deadline.strftime('%d/%m/%Y')}."
                    )
                    result.scheduled_tasks.append(task)
                    result.messages.append(
                        f"⚠️ '{task.title}' forcé à {pct:.0%} — manque de créneaux."
                    )
                else:
                    # <80% → non planifiable
                    task.is_scheduled = False
                    task.is_impossible = True
                    task.impossible_reason = (
                        f"Seulement {task.scheduled_hours():.1f}h/{task.duration_hours:.1f}h "
                        f"planifiées ({pct:.0%}) — insuffisant. "
                        f"Réduisez la durée ou repoussez la deadline."
                    )
                    result.impossible_tasks.append(task)
                    result.messages.append(
                        f"❌ '{task.title}' : {pct:.0%} planifié — insuffisant, non retenu."
                    )
            else:
                task.is_scheduled = False
                task.is_impossible = True
                task.impossible_reason = self._explain_impossible(task, free_slots)
                result.impossible_tasks.append(task)
                result.messages.append(
                    f"❌ '{task.title}' — NON PLANIFIABLE : {task.impossible_reason}"
                )

        # ── 5. Ajouter les créneaux occupés au calendrier ─────────────────────
        for slot in self.occupied_slots:
            if slot.date not in result.calendar:
                result.calendar[slot.date] = []
            result.calendar[slot.date].append({
                "type": "occupied",
                "title": slot.title or slot.slot_type,
                "slot_type": slot.slot_type,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "color": "#e74c3c",
            })

        # ── 6. Trier chaque journée par heure de début ────────────────────────
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
        """Planifie une tâche à heure fixe. Ignore les contraintes horaires."""
        pin_date = task.pin_datetime.date()
        pin_start = task.pin_datetime.time().replace(second=0, microsecond=0)
        pin_end = _add_hours_to_time(pin_start, task.duration_hours)

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

        result.calendar.setdefault(pin_date, []).append(block)
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
        """Calcule les créneaux libres d'une journée."""
        s = time(self.constraints.start_hour, 0)
        e = time(self.constraints.end_hour, 0)
        slots = [(s, e)]

        if self.constraints.lunch_break:
            slots = _subtract_range(slots, time(12, 0), time(13, 0))

        for occ in self.occupied_slots:
            if occ.date == d:
                slots = _subtract_range(slots, occ.start_time, occ.end_time)

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
        # Cas spécial tâche récurrente liée à un jour précis
        if task.not_before is not None and task.not_before == task.deadline:
            if task.not_before not in free_slots:
                if not self._is_working_day(task.not_before):
                    return f"Le {task.not_before.strftime('%d/%m/%Y')} est un jour non travaillé."
                return f"Aucun créneau libre le {task.not_before.strftime('%d/%m/%Y')} (journée pleine)."

        total_free = sum(
            sum(_time_diff_hours(s, e) for s, e in slots)
            for d, slots in free_slots.items()
            if d <= task.deadline
            and (task.not_before is None or d >= task.not_before)
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
            not_before=t.not_before,
            is_recurring=t.is_recurring,
            recurrence_label=t.recurrence_label,
            # is_new et schedule_warning sont gérés côté app.py, pas dans le scheduler
        )


# ─── Utilitaires temps ─────────────────────────────────────────────────────────

def _time_diff_hours(a: time, b: time) -> float:
    minutes = (b.hour * 60 + b.minute) - (a.hour * 60 + a.minute)
    return max(0.0, minutes / 60.0)


def _add_hours_to_time(t: time, hours: float) -> time:
    total_minutes = t.hour * 60 + t.minute + int(round(hours * 60))
    total_minutes = min(total_minutes, 23 * 60 + 59)
    return time(total_minutes // 60, total_minutes % 60)


def _subtract_range(
    slots: List[Tuple[time, time]], rem_start: time, rem_end: time
) -> List[Tuple[time, time]]:
    result = []
    for s, e in slots:
        if rem_end <= s or rem_start >= e:
            result.append((s, e))
        elif rem_start <= s and rem_end >= e:
            pass
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
