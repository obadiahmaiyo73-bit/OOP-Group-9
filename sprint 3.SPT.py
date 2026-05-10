"""
╔══════════════════════════════════════════════════════════════════════════╗
║               STA 2240: Fundamentals of Object-Oriented Programming      ║
║                      Student Performance Tracker                         ║                                                                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  SECTION 1 │ MODELS     — GradeRecord, Student                           ║
║  SECTION 2 │ EXCEPTIONS — Custom exception hierarchy (10 classes)        ║
║  SECTION 3 │ PIPELINE   — Functional HOF pipeline, ScoreQueue (deque)    ║
║  SECTION 4 │ STORAGE    — Robust JSON (atomic+backup), CSV, text report  ║
║  SECTION 5 │ PATTERNS   — Observer, Strategy, Decorator (3 GoF patterns) ║
║  SECTION 6 │ REGISTRY   — Central domain service                         ║
║  SECTION 7 │ UI / MAIN  — Exception-safe terminal interface              ║
╚══════════════════════════════════════════════════════════════════════════╝

Run:
    python3 student_performance_tracker.py

Data is persisted to  students_data.json  in the same directory.
An audit log of every grade entry is written to  audit.log.
"""

from __future__ import annotations

import abc
import csv
import json
import os
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from functools import reduce
from statistics import mean, median, stdev
from typing import Callable, Iterable, Iterator


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — MODELS
#   GradeRecord  — value object for a single grade entry
#   Student      — entity with iterator protocol and generator methods
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GradeRecord:
    """
    Immutable value object representing one grade entry.

    Milestone 3: demonstrates dataclass, encapsulation, pure methods.
    Milestone 4: participates in Observer events and Strategy grading.
    """
    subject: str
    score:   float
    term:    str
    date:    str = field(default_factory=lambda: datetime.now().isoformat())
    notes:   str = ""

    def letter_grade(self) -> str:
        """
        Convert numeric score to letter grade.
        Pure function — no side-effects, always returns same output for same input.
        Uses the Standard scale by default; Registry overrides via Strategy.
        """
        for threshold, grade in [(90, "A"), (80, "B"), (70, "C"), (60, "D")]:
            if self.score >= threshold:
                return grade
        return "F"

    def is_passing(self) -> bool:
        """Return True when score meets the minimum passing threshold (60)."""
        return self.score >= 60

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "score":   self.score,
            "term":    self.term,
            "date":    self.date,
            "notes":   self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GradeRecord":
        return cls(**d)

    def __repr__(self) -> str:
        return f"GradeRecord({self.subject!r}, score={self.score}, term={self.term!r})"


class Student:
    """
    Core entity.  Owns an ordered list of GradeRecord objects.

    Milestone 3 features:
      • Python iterator protocol  (__iter__ / __len__)
      • Generator methods         (records_by_subject, rolling_averages)
      • Functional query helpers  (scores, subjects, best_record, worst_record)
      • Full JSON serialisation

    Milestone 4:
      • Wrapped by GPATrackingDecorator / ReadOnlyDecorator transparently
    """

    def __init__(self, student_id: str, name: str, created: str | None = None):
        self.student_id: str = student_id
        self.name:       str = name
        self.created:    str = created or datetime.now().isoformat()
        self._records:   list[GradeRecord] = []

    # ── Record management ─────────────────────────────────────────────────────
    def add_record(self, record: GradeRecord) -> None:
        self._records.append(record)

    def get_records(self) -> list[GradeRecord]:
        """Return a defensive copy of all records."""
        return list(self._records)

    # ── Iterator protocol  (Milestone 3) ─────────────────────────────────────
    def __iter__(self) -> Iterator[GradeRecord]:
        return iter(self._records)

    def __len__(self) -> int:
        return len(self._records)

    # ── Generators  (Milestone 3) ─────────────────────────────────────────────
    def records_by_subject(self, subject: str) -> Iterator[GradeRecord]:
        """Generator — yield records lazily filtered by subject name."""
        return (r for r in self._records if r.subject.lower() == subject.lower())

    def rolling_averages(self, window: int = 3) -> Iterator[float]:
        """Generator — yield rolling mean over a sliding window of scores."""
        scores = [r.score for r in self._records]
        for i in range(len(scores) - window + 1):
            yield sum(scores[i:i + window]) / window

    # ── Functional helpers  (Milestone 3) ─────────────────────────────────────
    def scores(self) -> list[float]:
        return [r.score for r in self._records]

    def subjects(self) -> set[str]:
        """Return unique subject names as a set."""
        return {r.subject for r in self._records}

    def best_record(self) -> GradeRecord | None:
        return max(self._records, key=lambda r: r.score, default=None)

    def worst_record(self) -> GradeRecord | None:
        return min(self._records, key=lambda r: r.score, default=None)

    # ── Serialisation ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "name":       self.name,
            "created":    self.created,
            "records":    [r.to_dict() for r in self._records],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Student":
        s = cls(d["student_id"], d["name"], d.get("created"))
        for rd in d.get("records", []):
            s.add_record(GradeRecord.from_dict(rd))
        return s

    def __repr__(self) -> str:
        return f"Student({self.name!r}, records={len(self._records)})"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — EXCEPTIONS  (Milestone 4)
#
#   TrackerError                    ← base for all domain errors
#     ├── ValidationError
#     │     ├── ScoreOutOfRangeError
#     │     └── EmptyFieldError
#     ├── StudentNotFoundError
#     ├── DuplicateStudentError
#     ├── NoRecordsError
#     └── StorageError
#           ├── CorruptDataError
#           └── FileNotFoundTrackerError
# ═══════════════════════════════════════════════════════════════════════════════

class TrackerError(Exception):
    """Base class — catch this to handle any tracker domain error."""


class ValidationError(TrackerError):
    """Raised when user-supplied data fails a validation rule."""
    def __init__(self, field: str, reason: str):
        self.field  = field
        self.reason = reason
        super().__init__(f"Validation failed for '{field}': {reason}")


class ScoreOutOfRangeError(ValidationError):
    """Score is not within the valid [0, 100] range."""
    def __init__(self, score: float):
        super().__init__("score", f"{score} is not in [0, 100]")
        self.score = score


class EmptyFieldError(ValidationError):
    """A required field was submitted empty."""
    def __init__(self, field: str):
        super().__init__(field, "field must not be empty")


class StudentNotFoundError(TrackerError):
    """Requested student ID does not exist in the registry."""
    def __init__(self, student_id: str):
        self.student_id = student_id
        super().__init__(f"Student '{student_id}' not found.")


class DuplicateStudentError(TrackerError):
    """Attempt to register a student that already exists."""
    def __init__(self, student_id: str):
        self.student_id = student_id
        super().__init__(f"Student '{student_id}' is already registered.")


class NoRecordsError(TrackerError):
    """Operation requires grade records, but none exist for this student."""
    def __init__(self, student_name: str):
        super().__init__(f"No grade records found for '{student_name}'.")


class StorageError(TrackerError):
    """File read/write operation failed."""
    def __init__(self, filepath: str, detail: str):
        self.filepath = filepath
        super().__init__(f"Storage error [{filepath}]: {detail}")


class CorruptDataError(StorageError):
    """Persisted data could not be deserialised (e.g., broken JSON)."""


class FileNotFoundTrackerError(StorageError):
    """A required input file does not exist on disk."""
    def __init__(self, filepath: str):
        super().__init__(filepath, "file does not exist")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — PIPELINE  (Milestone 3)
#
#   Primitive HOFs : filter_records, map_scores, group_by, reduce_scores
#   Composites     : passing_rate, top_n_students, subject_statistics,
#                    term_progression, score_distribution, improvement_pipeline
#   Data structure : ScoreQueue  (deque-backed sliding window)
# ═══════════════════════════════════════════════════════════════════════════════

# ── Primitive higher-order pipeline stages ────────────────────────────────────

def filter_records(
    students: Iterable[Student],
    predicate: Callable[[GradeRecord], bool],
) -> Iterator[tuple[Student, GradeRecord]]:
    """
    Generator — lazily yield (student, record) pairs where predicate holds.
    Example:  filter_records(students, lambda r: r.score >= 80)
    """
    for student in students:
        for record in student:
            if predicate(record):
                yield student, record


def map_scores(
    records: Iterable[GradeRecord],
    transform: Callable[[float], float],
) -> Iterator[float]:
    """Apply a transformation function to every score, lazily."""
    return (transform(r.score) for r in records)


def group_by(
    students: Iterable[Student],
    key_fn: Callable[[GradeRecord], str],
) -> dict[str, list[float]]:
    """
    Partition all scores across all students by an arbitrary key.
    Returns  {key: [score, score, …]}
    Example:  group_by(students, lambda r: r.subject)
    """
    groups: dict[str, list[float]] = defaultdict(list)
    for student in students:
        for record in student:
            groups[key_fn(record)].append(record.score)
    return dict(groups)


def reduce_scores(
    scores: Iterable[float],
    reducer: Callable[[float, float], float],
    initial: float = 0.0,
) -> float:
    """Collapse a stream of scores with a binary reducer (functional fold)."""
    return reduce(reducer, scores, initial)


# ── Composite pipeline functions ──────────────────────────────────────────────

def passing_rate(students: list[Student]) -> float:
    """Return percentage of all grade records with a passing score (≥ 60)."""
    total = sum(len(s) for s in students)
    if total == 0:
        return 0.0
    passing = sum(1 for _, r in filter_records(students, lambda r: r.is_passing()))
    return passing / total * 100


def top_n_students(
    students: list[Student], n: int = 5
) -> list[tuple[Student, float]]:
    """Return top-N students ranked by overall average, highest first."""
    averages = [(s, mean(s.scores())) for s in students if s.scores()]
    return sorted(averages, key=lambda x: x[1], reverse=True)[:n]


def subject_statistics(students: list[Student]) -> dict[str, dict]:
    """
    Compute per-subject statistics across all students.
    Returns  {subject: {count, mean, median, stdev, min, max, pass_rate}}
    """
    grouped = group_by(students, lambda r: r.subject)
    stats: dict[str, dict] = {}
    for subject, scores in grouped.items():
        stats[subject] = {
            "count":     len(scores),
            "mean":      mean(scores),
            "median":    median(scores),
            "stdev":     stdev(scores) if len(scores) > 1 else 0.0,
            "min":       min(scores),
            "max":       max(scores),
            "pass_rate": sum(1 for s in scores if s >= 60) / len(scores) * 100,
        }
    return stats


def term_progression(students: list[Student]) -> dict[str, float]:
    """Return class-wide average score per term, sorted chronologically."""
    grouped = group_by(students, lambda r: r.term)
    return {term: mean(scores) for term, scores in sorted(grouped.items())}


def score_distribution(students: list[Student]) -> dict[str, int]:
    """Count records in each letter-grade band across all students."""
    bands: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for student in students:
        for record in student:
            bands[record.letter_grade()] += 1
    return bands


def improvement_pipeline(student: Student) -> list[dict]:
    """
    Generator-based pipeline: per-subject improvement report.
    Compares first vs last score; sorted by delta (biggest gains first).
    """
    reports = []
    for subject in student.subjects():
        recs = list(student.records_by_subject(subject))
        if len(recs) < 2:
            continue
        first, last = recs[0].score, recs[-1].score
        reports.append({
            "subject":     subject,
            "first_score": first,
            "last_score":  last,
            "delta":       last - first,
            "trend":       "improving" if last > first
                           else "declining" if last < first
                           else "stable",
        })
    return sorted(reports, key=lambda r: r["delta"], reverse=True)


# ── Sliding-window queue  (collections.deque) ─────────────────────────────────

class ScoreQueue:
    """
    Fixed-size queue keeping only the N most recent scores per student.
    Uses collections.deque for O(1) append and automatic eviction.

    Milestone 3: advanced data structures requirement.
    """
    def __init__(self, maxlen: int = 5):
        self._store: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=maxlen)
        )
        self.maxlen = maxlen

    def push(self, student_id: str, score: float) -> None:
        self._store[student_id].append(score)

    def recent(self, student_id: str) -> list[float]:
        return list(self._store[student_id])

    def moving_average(self, student_id: str) -> float | None:
        q = self._store[student_id]
        return mean(q) if q else None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — STORAGE  (Milestones 3 & 4)
#
#   RobustJSONStore   — atomic writes + corrupt-file backup (Milestone 4)
#   export_csv        — flat CSV export
#   import_csv        — CSV import via lazy generator
#   export_text_report — plain-text report via generator pipeline
# ═══════════════════════════════════════════════════════════════════════════════

CSV_HEADER = ["student_id", "name", "subject", "score", "term", "date", "notes"]


class RobustJSONStore:
    """
    Exception-safe JSON persistence layer.

    Milestone 3: file handling and data persistence.
    Milestone 4: exception-safe, atomic write, corrupt-file backup.
    """

    def __init__(self, filepath: str = "students_data.json"):
        self.filepath = filepath

    def load(self) -> dict[str, Student]:
        """
        Load all students from disk.
        Raises FileNotFoundTrackerError, CorruptDataError, or StorageError.
        """
        if not os.path.exists(self.filepath):
            return {}
        try:
            with open(self.filepath, encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundTrackerError(self.filepath)
        except json.JSONDecodeError as exc:
            # Save a backup before wiping so data is not lost
            backup = self.filepath + ".corrupt"
            try:
                os.replace(self.filepath, backup)
            except OSError:
                pass
            raise CorruptDataError(
                self.filepath,
                f"JSON parse error – backup saved as {backup}: {exc}"
            )
        except OSError as exc:
            raise StorageError(self.filepath, str(exc))

        if not isinstance(raw, dict):
            raise CorruptDataError(self.filepath, "expected a JSON object at root")

        students: dict[str, Student] = {}
        for sid, d in raw.items():
            try:
                students[sid] = Student.from_dict(d)
            except (KeyError, TypeError, ValueError) as exc:
                raise CorruptDataError(
                    self.filepath, f"bad record for student '{sid}': {exc}"
                )
        return students

    def save(self, students: dict[str, Student]) -> None:
        """
        Write atomically: serialise to .tmp, then os.replace (POSIX-atomic).
        Raises StorageError on disk failure.
        """
        payload = {sid: s.to_dict() for sid, s in students.items()}
        tmp = self.filepath + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, self.filepath)
        except OSError as exc:
            raise StorageError(self.filepath, str(exc))
        finally:
            # Clean up .tmp if os.replace failed
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def export_csv(students: dict[str, Student], filepath: str) -> int:
    """Write all grade records to a flat CSV. Returns number of data rows."""
    rows = 0
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        for sid, student in students.items():
            for record in student:
                writer.writerow({
                    "student_id": sid,
                    "name":       student.name,
                    "subject":    record.subject,
                    "score":      record.score,
                    "term":       record.term,
                    "date":       record.date,
                    "notes":      record.notes,
                })
                rows += 1
    return rows


def import_csv(filepath: str) -> dict[str, Student]:
    """
    Reconstruct Student objects from a flat CSV.
    Uses a generator internally to stream rows without loading all into memory.
    """
    def _rows(reader: csv.DictReader) -> Iterator[dict]:
        yield from reader   # lazy generator

    students: dict[str, Student] = {}
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in _rows(reader):
            sid = row["student_id"]
            if sid not in students:
                students[sid] = Student(sid, row["name"])
            students[sid].add_record(GradeRecord(
                subject=row["subject"],
                score=float(row["score"]),
                term=row["term"],
                date=row.get("date", datetime.now().isoformat()),
                notes=row.get("notes", ""),
            ))
    return students


def _report_lines(students: dict[str, Student]) -> Iterator[str]:
    """Generator — yield formatted report lines one at a time (memory-efficient)."""
    yield "STUDENT PERFORMANCE REPORT"
    yield f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    yield "=" * 72
    for sid, student in students.items():
        yield ""
        yield f"  Student : {student.name}  (ID: {sid})"
        yield f"  Since   : {student.created[:10]}"
        if not student.get_records():
            yield "  No records."; continue
        for record in student:
            yield (f"    {record.term:<14} {record.subject:<20} "
                   f"{record.score:6.1f}  [{record.letter_grade()}]  {record.notes}")
        avg  = mean(student.scores())
        best = student.best_record()
        yield f"  Overall avg : {avg:.1f}  [{best.letter_grade() if best else '-'}]"
        yield "  " + "-" * 68


def export_text_report(students: dict[str, Student], filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        for line in _report_lines(students):
            f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — DESIGN PATTERNS  (Milestone 4)
#
#   Pattern 1 – OBSERVER   : GradeEvent, GradeObserver (ABC),
#                            FailingGradeAlert, AuditLogger, GradeEventBus
#   Pattern 2 – STRATEGY   : GradingStrategy (ABC),
#                            StandardGrading, StrictGrading, PassFailGrading
#   Pattern 3 – DECORATOR  : StudentDecorator, GPATrackingDecorator,
#                            ReadOnlyDecorator
# ═══════════════════════════════════════════════════════════════════════════════

# ── PATTERN 1: OBSERVER ───────────────────────────────────────────────────────

class GradeEvent:
    """Payload object passed to every observer when a grade is recorded."""
    def __init__(self, student_name: str, subject: str,
                 score: float, term: str):
        self.student_name = student_name
        self.subject      = subject
        self.score        = score
        self.term         = term

    def __repr__(self) -> str:
        return (f"GradeEvent({self.student_name!r}, "
                f"{self.subject!r}, {self.score})")


class GradeObserver(abc.ABC):
    """Abstract observer — subclass and implement on_grade_added."""
    @abc.abstractmethod
    def on_grade_added(self, event: GradeEvent) -> None: ...


class FailingGradeAlert(GradeObserver):
    """Prints a red alert whenever a student records a failing grade (< 60)."""
    def on_grade_added(self, event: GradeEvent) -> None:
        if event.score < 60:
            print(
                f"\033[91m  ⚠  ALERT: {event.student_name} scored "
                f"{event.score:.1f} in {event.subject} "
                f"({event.term}) — FAILING\033[0m"
            )


class AuditLogger(GradeObserver):
    """Appends every grade event to a persistent audit log file."""
    def __init__(self, log_path: str = "audit.log"):
        self.log_path = log_path

    def on_grade_added(self, event: GradeEvent) -> None:
        line = (
            f"{datetime.now().isoformat()}  |  "
            f"{event.student_name:<20} |  "
            f"{event.subject:<18} |  "
            f"{event.score:6.1f}  |  {event.term}\n"
        )
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)


class GradeEventBus:
    """
    Subject / publisher.
    The Registry calls notify() after every successful grade insertion;
    all subscribed observers react automatically.
    """
    def __init__(self):
        self._observers: list[GradeObserver] = []

    def subscribe(self, observer: GradeObserver) -> None:
        self._observers.append(observer)

    def unsubscribe(self, observer: GradeObserver) -> None:
        self._observers.remove(observer)

    def notify(self, event: GradeEvent) -> None:
        for obs in self._observers:
            obs.on_grade_added(event)


# ── PATTERN 2: STRATEGY ───────────────────────────────────────────────────────

class GradingStrategy(abc.ABC):
    """
    Abstract strategy — swap grading scales at runtime without modifying
    Student or Registry.
    """
    @abc.abstractmethod
    def letter_grade(self, score: float) -> str: ...

    @abc.abstractmethod
    def gpa_points(self, score: float) -> float: ...

    @property
    @abc.abstractmethod
    def name(self) -> str: ...


class StandardGrading(GradingStrategy):
    """US 10-point scale: A ≥ 90 | B ≥ 80 | C ≥ 70 | D ≥ 60 | F < 60"""
    @property
    def name(self) -> str:
        return "Standard (A≥90 / B≥80 / C≥70 / D≥60)"

    def letter_grade(self, score: float) -> str:
        for t, g in [(90, "A"), (80, "B"), (70, "C"), (60, "D")]:
            if score >= t:
                return g
        return "F"

    def gpa_points(self, score: float) -> float:
        return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}[
            self.letter_grade(score)
        ]


class StrictGrading(GradingStrategy):
    """East African university scale: A ≥ 70 | B ≥ 60 | C ≥ 50 | D ≥ 40"""
    @property
    def name(self) -> str:
        return "Strict (A≥70 / B≥60 / C≥50 / D≥40)"

    def letter_grade(self, score: float) -> str:
        for t, g in [(70, "A"), (60, "B"), (50, "C"), (40, "D")]:
            if score >= t:
                return g
        return "F"

    def gpa_points(self, score: float) -> float:
        return {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0, "F": 0.0}[
            self.letter_grade(score)
        ]


class PassFailGrading(GradingStrategy):
    """Binary scale: Pass (P) ≥ 50 | Fail (F) < 50"""
    @property
    def name(self) -> str:
        return "Pass / Fail  (P ≥ 50)"

    def letter_grade(self, score: float) -> str:
        return "P" if score >= 50 else "F"

    def gpa_points(self, score: float) -> float:
        return 4.0 if score >= 50 else 0.0


# Convenience registry of available strategies
GRADING_STRATEGIES: dict[str, GradingStrategy] = {
    "standard":  StandardGrading(),
    "strict":    StrictGrading(),
    "pass_fail": PassFailGrading(),
}


# ── PATTERN 3: DECORATOR ──────────────────────────────────────────────────────

class StudentDecorator(Student):
    """
    Base decorator — wraps a Student and transparently forwards every call.
    Subclasses override only the methods they augment.

    Uses __getattr__ as a fallback for any attribute not explicitly forwarded.
    """
    def __init__(self, wrapped: Student):
        # Do NOT call super().__init__(); delegate to wrapped instead.
        self._wrapped = wrapped

    # Fallback proxy
    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)

    # Magic methods Python won't route through __getattr__
    def __iter__(self):     return iter(self._wrapped)
    def __len__(self):      return len(self._wrapped)
    def __repr__(self):     return f"{self.__class__.__name__}({self._wrapped!r})"

    # Explicit forwarding for core interface
    @property
    def student_id(self):   return self._wrapped.student_id
    @property
    def name(self):         return self._wrapped.name
    @property
    def created(self):      return self._wrapped.created

    def add_record(self, record: GradeRecord) -> None:
        self._wrapped.add_record(record)

    def get_records(self):  return self._wrapped.get_records()
    def scores(self):       return self._wrapped.scores()
    def subjects(self):     return self._wrapped.subjects()
    def best_record(self):  return self._wrapped.best_record()
    def worst_record(self): return self._wrapped.worst_record()
    def to_dict(self):      return self._wrapped.to_dict()

    def records_by_subject(self, subject: str):
        return self._wrapped.records_by_subject(subject)

    def rolling_averages(self, window: int = 3):
        return self._wrapped.rolling_averages(window)


class GPATrackingDecorator(StudentDecorator):
    """
    Augments Student with GPA computation using a pluggable GradingStrategy.
    Also annotates each new record with its letter grade in the notes field
    if notes were left blank.

    Usage:
        student = GPATrackingDecorator(raw_student, strategy=StrictGrading())
    """
    def __init__(self, wrapped: Student, strategy: GradingStrategy | None = None):
        super().__init__(wrapped)
        self._strategy: GradingStrategy = strategy or StandardGrading()

    def gpa(self) -> float:
        """Compute GPA using the current strategy."""
        sc = self.scores()
        if not sc:
            return 0.0
        return mean(self._strategy.gpa_points(s) for s in sc)

    def letter_grade_for(self, score: float) -> str:
        return self._strategy.letter_grade(score)

    def grading_scale(self) -> str:
        return self._strategy.name

    def add_record(self, record: GradeRecord) -> None:
        """Intercept add to annotate the notes with letter grade."""
        if not record.notes:
            record.notes = f"[{self._strategy.letter_grade(record.score)}]"
        super().add_record(record)


class ReadOnlyDecorator(StudentDecorator):
    """
    Prevents any modification to an archived student.
    All write operations raise PermissionError.
    """
    def add_record(self, record: GradeRecord) -> None:
        raise PermissionError(
            f"Student '{self.name}' is archived and cannot be modified."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — REGISTRY  (Milestone 4)
#
#   Central domain service.  Integrates:
#     • Observer   → GradeEventBus.notify() after every add_grade()
#     • Strategy   → swappable grading scale injected into GPATrackingDecorator
#     • Decorator  → get_student() wraps raw Student transparently
#     • Exceptions → every public method documents its exception contract
# ═══════════════════════════════════════════════════════════════════════════════

class StudentRegistry:
    """
    Manages the full lifecycle of students and grade records.
    All application code interacts with students through this service.
    """

    def __init__(
        self,
        store:            RobustJSONStore | None = None,
        grading_strategy: GradingStrategy  | None = None,
    ):
        self._store    = store or RobustJSONStore()
        self._strategy = grading_strategy or StandardGrading()
        self._students: dict[str, Student] = {}
        self._archived: set[str]           = set()
        self._bus      = GradeEventBus()

        # Default observers wired at startup
        self._bus.subscribe(FailingGradeAlert())
        self._bus.subscribe(AuditLogger("audit.log"))

        # Load persisted data; tolerate a missing file silently
        try:
            self._students = self._store.load()
        except FileNotFoundTrackerError:
            pass
        except (CorruptDataError, StorageError) as exc:
            print(f"\033[91m  ⚠  {exc}\033[0m")

    # ── Observer ──────────────────────────────────────────────────────────────
    def subscribe(self, observer: GradeObserver) -> None:
        self._bus.subscribe(observer)

    def unsubscribe(self, observer: GradeObserver) -> None:
        self._bus.unsubscribe(observer)

    # ── Strategy ──────────────────────────────────────────────────────────────
    def set_grading_strategy(self, strategy: GradingStrategy) -> None:
        self._strategy = strategy

    def current_strategy(self) -> str:
        return self._strategy.name

    # ── Student CRUD ──────────────────────────────────────────────────────────
    def register_student(self, name: str) -> Student:
        """
        Raises:
            EmptyFieldError       – name is blank
            DuplicateStudentError – student already registered
            StorageError          – disk write failure
        """
        if not name or not name.strip():
            raise EmptyFieldError("name")
        sid = name.strip().lower().replace(" ", "_")
        if sid in self._students:
            raise DuplicateStudentError(sid)
        student = Student(sid, name.strip())
        self._students[sid] = student
        self._save()
        return student

    def archive_student(self, student_id: str) -> None:
        """Lock a student as read-only.  Raises StudentNotFoundError."""
        self._get_raw(student_id)
        self._archived.add(student_id)

    def unarchive_student(self, student_id: str) -> None:
        self._archived.discard(student_id)

    def remove_student(self, student_id: str) -> None:
        """
        Permanently delete a student and all their records.
        Raises:
            StudentNotFoundError – student does not exist
            StorageError         – disk write failure
        """
        self._get_raw(student_id)
        del self._students[student_id]
        self._archived.discard(student_id)
        self._save()

    def get_student(self, student_id: str) -> GPATrackingDecorator:
        """
        Return a GPA-aware decorator view of the student.
        Archived students are wrapped in ReadOnlyDecorator instead.
        Raises:
            StudentNotFoundError – student does not exist
        """
        raw = self._get_raw(student_id)
        if student_id in self._archived:
            return ReadOnlyDecorator(raw)          # type: ignore[return-value]
        return GPATrackingDecorator(raw, self._strategy)

    def all_students(self) -> list[GPATrackingDecorator]:
        return [self.get_student(sid) for sid in self._students]

    def student_ids(self) -> list[str]:
        return list(self._students.keys())

    def is_archived(self, student_id: str) -> bool:
        return student_id in self._archived

    # ── Grade records ─────────────────────────────────────────────────────────
    def add_grade(
        self,
        student_id: str,
        subject:    str,
        score:      float,
        term:       str,
        notes:      str = "",
    ) -> GradeRecord:
        """
        Validate, persist, and publish a grade event.
        Raises:
            StudentNotFoundError  – unknown student
            EmptyFieldError       – subject or term is blank
            ScoreOutOfRangeError  – score not in [0, 100]
            PermissionError       – student is archived (read-only)
            StorageError          – disk write failure
        """
        student = self.get_student(student_id)  # raises if absent / archived check

        if not subject or not subject.strip():
            raise EmptyFieldError("subject")
        if not term or not term.strip():
            raise EmptyFieldError("term")
        if not (0.0 <= score <= 100.0):
            raise ScoreOutOfRangeError(score)

        record = GradeRecord(
            subject=subject.strip(),
            score=round(score, 2),
            term=term.strip(),
            notes=notes.strip(),
        )
        student.add_record(record)   # may raise PermissionError for archived
        self._save()

        # Observer notification — non-fatal: log but never abort on observer failure
        try:
            self._bus.notify(GradeEvent(student.name, subject, score, term))
        except Exception as exc:
            print(f"\033[93m  ⚠  Observer error (non-fatal): {exc}\033[0m")

        return record

    # ── Analytics ─────────────────────────────────────────────────────────────
    def student_average(self, student_id: str) -> float:
        """
        Raises:
            StudentNotFoundError – unknown student
            NoRecordsError       – student has no grades yet
        """
        student = self.get_student(student_id)
        sc = student.scores()
        if not sc:
            raise NoRecordsError(student.name)
        return mean(sc)

    def class_average(self) -> float:
        """Return mean over all records from all students (0.0 if empty)."""
        all_scores = [s for st in self.all_students() for s in st.scores()]
        return mean(all_scores) if all_scores else 0.0

    # ── Export ────────────────────────────────────────────────────────────────
    def export_csv(self, filepath: str) -> int:
        try:
            return export_csv(self._students, filepath)
        except OSError as exc:
            raise StorageError(filepath, str(exc))

    def export_report(self, filepath: str) -> None:
        try:
            export_text_report(self._students, filepath)
        except OSError as exc:
            raise StorageError(filepath, str(exc))

    def import_csv_data(self, filepath: str) -> int:
        """Import from CSV, merge into registry. Returns count of new students."""
        try:
            imported = import_csv(filepath)
        except OSError as exc:
            raise StorageError(filepath, str(exc))
        new_count = 0
        for sid, student in imported.items():
            if sid not in self._students:
                self._students[sid] = student
                new_count += 1
            else:
                for rec in student:
                    self._students[sid].add_record(rec)
        self._save()
        return new_count

    # ── Private helpers ───────────────────────────────────────────────────────
    def _get_raw(self, student_id: str) -> Student:
        if student_id not in self._students:
            raise StudentNotFoundError(student_id)
        return self._students[student_id]

    def _save(self) -> None:
        self._store.save(self._students)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — UI / MAIN
#
#   ANSI colour helpers, terminal UI primitives, menu action functions,
#   and the main application loop.
#
#   Every menu action is wrapped with @_handle which catches all TrackerErrors
#   and displays a friendly message — no raw tracebacks ever reach the user.
# ═══════════════════════════════════════════════════════════════════════════════

# ── ANSI colour palette ───────────────────────────────────────────────────────
class C:
    R   = "\033[0m"
    B   = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GRN = "\033[92m"
    YLW = "\033[93m"
    BLU = "\033[94m"
    MAG = "\033[95m"
    CYN = "\033[96m"


def col(text, *codes) -> str:
    return "".join(codes) + str(text) + C.R


def grade_col(score: float) -> str:
    if score >= 90: return C.GRN
    if score >= 80: return C.CYN
    if score >= 70: return C.YLW
    if score >= 60: return C.MAG
    return C.RED


def bar(score: float, width: int = 18) -> str:
    filled = int(score / 100 * width)
    return col("█" * filled, grade_col(score)) + col("░" * (width - filled), C.DIM)


# ── UI primitives ─────────────────────────────────────────────────────────────
def header(title: str) -> None:
    print()
    w = 66
    print(col("╔" + "═" * (w - 2) + "╗", C.CYN, C.B))
    print(col("║" + title.center(w - 2) + "║", C.CYN, C.B))
    print(col("╚" + "═" * (w - 2) + "╝", C.CYN, C.B))
    print()


def divider() -> None:
    print(col("─" * 66, C.DIM))


def ok(msg: str)   -> None: print(col(f"  ✔  {msg}", C.GRN))
def err(msg: str)  -> None: print(col(f"  ✘  {msg}", C.RED))
def warn(msg: str) -> None: print(col(f"  ⚠  {msg}", C.YLW))
def ask(msg: str)  -> str:  return input(col(f"  {msg}: ", C.CYN, C.B)).strip()
def pause()        -> None: input(col("\n  Press Enter to continue…", C.DIM))


# ── Global application state ──────────────────────────────────────────────────
REGISTRY = StudentRegistry(store=RobustJSONStore("students_data.json"))
QUEUE    = ScoreQueue(maxlen=5)


# ── Exception-safe action wrapper (Milestone 4 – Decorator pattern on functions)
def _handle(fn: Callable) -> Callable:
    """
    Function decorator — catches every TrackerError subclass and maps it to
    a user-friendly terminal message.  No raw Python tracebacks are shown.
    """
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except PermissionError        as e: err(str(e))
        except StorageError           as e: err(f"Storage failure: {e}")
        except DuplicateStudentError  as e: warn(str(e))
        except StudentNotFoundError   as e: err(str(e))
        except NoRecordsError         as e: warn(str(e))
        except ValidationError        as e: err(f"Invalid input — {e.field}: {e.reason}")
        except TrackerError           as e: err(str(e))
    return wrapper


# ── Shared helper ─────────────────────────────────────────────────────────────
def _pick_student() -> tuple[str, GPATrackingDecorator] | None:
    """Display a numbered student list and return (sid, student) or None."""
    ids = REGISTRY.student_ids()
    if not ids:
        warn("No students on record.")
        pause()
        return None
    for i, sid in enumerate(ids, 1):
        s     = REGISTRY.get_student(sid)
        label = s.name
        if REGISTRY.is_archived(sid):
            label += col("  [archived]", C.DIM)
        print(f"  {col(i, C.CYN, C.B)}. {label}")
    print()
    try:
        sid = ids[int(ask("Select student #")) - 1]
        return sid, REGISTRY.get_student(sid)
    except (ValueError, IndexError):
        err("Invalid selection.")
        pause()
        return None


# ── Menu actions ──────────────────────────────────────────────────────────────

@_handle
def action_add_student() -> None:
    header("ADD STUDENT")
    name = ask("Full name")
    student = REGISTRY.register_student(name)
    ok(f"Registered: {student.name}  (ID: {student.student_id})")
    pause()


@_handle
def action_add_record() -> None:
    header("ADD GRADE RECORD")
    result = _pick_student()
    if not result:
        return
    sid, student = result

    subject   = ask("Subject")
    raw_score = ask("Score (0–100)")
    try:
        score = float(raw_score)
    except ValueError:
        err("Score must be a number.")
        pause()
        return

    term  = ask("Term / Period  (e.g. 2024-Q1, Semester 2)") or datetime.now().strftime("%Y-%m")
    notes = ask("Notes  (optional)")

    rec = REGISTRY.add_grade(sid, subject, score, term, notes)
    QUEUE.push(sid, score)
    ok(f"Recorded: {rec.subject}  {rec.score:.1f}  [{rec.letter_grade()}]")
    pause()


@_handle
def action_view_student() -> None:
    header("STUDENT REPORT")
    result = _pick_student()
    if not result:
        return
    sid, student = result

    print()
    print(col(f"  Name         : {student.name}", C.B))
    print(col(f"  ID           : {student.student_id}", C.DIM))
    print(col(f"  Registered   : {student.created[:10]}", C.DIM))
    print(col(f"  Grading scale: {REGISTRY.current_strategy()}", C.DIM))
    archived_tag = col("  [ARCHIVED – read-only]", C.YLW) if REGISTRY.is_archived(sid) else ""
    if archived_tag:
        print(archived_tag)

    if not student.get_records():
        warn("No grade records yet.")
        pause()
        return

    avg = REGISTRY.student_average(sid)
    gpa = student.gpa()
    print(f"\n  Overall avg  : {col(f'{avg:.1f}', grade_col(avg), C.B)}"
          f"   GPA: {col(f'{gpa:.2f}', grade_col(avg), C.B)}"
          f"   Records: {len(student.get_records())}")
    divider()

    for subject in sorted(student.subjects()):
        recs   = list(student.records_by_subject(subject))
        scores = [r.score for r in recs]
        savg   = mean(scores)
        print(col(f"\n  {subject}", C.YLW, C.B))
        print(f"  {bar(savg)}  avg {col(f'{savg:.1f}', grade_col(savg), C.B)}")
        print(col("  Term            Score  Grade  Notes", C.DIM))
        for r in recs:
            ltr = col(r.letter_grade(), grade_col(r.score), C.B)
            sc  = col(f"{r.score:5.1f}", grade_col(r.score))
            nt  = col(f"  {r.notes}", C.DIM) if r.notes else ""
            print(f"  {r.term:<15} {sc}   {ltr}  {nt}")

    # Improvement pipeline (Milestone 3)
    imps = improvement_pipeline(student)
    if imps:
        print()
        divider()
        print(col("  Subject Trends  (first score → latest score)", C.B))
        for imp in imps:
            arrow = (col("▲▲", C.GRN) if imp["delta"] > 5
                     else col("▲",  C.GRN) if imp["delta"] > 0
                     else col("▼▼", C.RED) if imp["delta"] < -5
                     else col("▼",  C.RED) if imp["delta"] < 0
                     else "─")
            print(f"  {imp['subject']:<22} "
                  f"{imp['first_score']:.1f} → {imp['last_score']:.1f}  "
                  f"{arrow}  {col(imp['trend'], C.DIM)}")

    # Rolling averages generator (Milestone 3)
    rolls = list(student.rolling_averages(window=3))
    if rolls:
        print()
        print(col("  3-record rolling averages: ", C.DIM) +
              "  ".join(col(f"{r:.1f}", grade_col(r)) for r in rolls))

    # Sliding-window queue (Milestone 3)
    recent = QUEUE.recent(sid)
    if recent:
        mv = QUEUE.moving_average(sid)
        print(col("  Recent 5 scores (queue):  ", C.DIM) +
              "  ".join(col(f"{s:.1f}", grade_col(s)) for s in recent) +
              col(f"  | moving avg: {mv:.1f}", C.DIM))
    pause()


@_handle
def action_class_overview() -> None:
    header("CLASS OVERVIEW")
    students_list = REGISTRY.all_students()
    if not students_list:
        warn("No students.")
        pause()
        return

    tops    = top_n_students(students_list, n=len(students_list))
    pr      = passing_rate(students_list)
    cls_avg = REGISTRY.class_average()

    print(col(f"  {'#':<4}{'Name':<22}{'GPA':>5}{'Avg':>8}  Grade  Performance", C.DIM))
    divider()
    for rank, (student, avg) in enumerate(tops, 1):
        gpa = student.gpa() if hasattr(student, "gpa") else 0.0
        ltr = GradeRecord("", avg, "").letter_grade()
        arc = col(" ⊘", C.DIM) if REGISTRY.is_archived(student.student_id) else "  "
        print(f"  {rank:<4}{student.name:<22}"
              f"{col(f'{gpa:5.2f}', grade_col(avg), C.B)}"
              f"{col(f'{avg:8.1f}', grade_col(avg), C.B)}"
              f"  {col(ltr, grade_col(avg), C.B):>5}  {bar(avg)}{arc}")

    divider()
    print(f"  Class avg  : {col(f'{cls_avg:.1f}', grade_col(cls_avg), C.B)}"
          f"   Passing rate: {col(f'{pr:.1f}%', C.GRN if pr >= 60 else C.RED, C.B)}"
          f"   Students: {len(students_list)}")

    dist = score_distribution(students_list)
    print(col("\n  Grade distribution:", C.DIM))
    for grade, count in dist.items():
        filled = "█" * count
        print(f"    {grade}: {col(filled, C.CYN)}  {count}")
    pause()


@_handle
def action_subject_analysis() -> None:
    header("SUBJECT ANALYSIS")
    students_list = REGISTRY.all_students()
    if not students_list:
        warn("No students.")
        pause()
        return
    stats = subject_statistics(students_list)
    if not stats:
        warn("No grade records found.")
        pause()
        return

    print(col(f"  {'Subject':<22}{'Avg':>7}{'Med':>7}{'SD':>6}{'Min':>6}{'Max':>6}  Pass%", C.DIM))
    divider()
    for subj in sorted(stats):
        s   = stats[subj]
        avg = s["mean"]
        pr  = s["pass_rate"]
        print(f"  {subj:<22}"
              f"{col(f'{avg:7.1f}', grade_col(avg), C.B)}"
              f"{s['median']:7.1f}"
              f"{s['stdev']:6.1f}"
              f"{s['min']:6.1f}"
              f"{s['max']:6.1f}"
              f"  {col(str(round(pr)) + '%', C.GRN if pr >= 60 else C.RED)}")

    prog = term_progression(students_list)
    if prog:
        print()
        print(col("  Class average by term:", C.B))
        for term, avg in prog.items():
            print(f"    {term:<16}  {bar(avg, 16)}  {col(f'{avg:.1f}', grade_col(avg))}")
    pause()


@_handle
def action_change_scale() -> None:
    header("CHANGE GRADING SCALE")
    print(f"  Current scale: {col(REGISTRY.current_strategy(), C.YLW, C.B)}\n")
    options = list(GRADING_STRATEGIES.items())
    for i, (_, strat) in enumerate(options, 1):
        print(f"  {col(i, C.CYN, C.B)}. {strat.name}")
    print()
    try:
        key = options[int(ask("Select scale #")) - 1][0]
        REGISTRY.set_grading_strategy(GRADING_STRATEGIES[key])
        ok(f"Grading scale updated to: {REGISTRY.current_strategy()}")
    except (ValueError, IndexError):
        err("Invalid selection.")
    pause()


@_handle
def action_archive_student() -> None:
    header("ARCHIVE / UNARCHIVE STUDENT")
    result = _pick_student()
    if not result:
        return
    sid, student = result
    if REGISTRY.is_archived(sid):
        REGISTRY.unarchive_student(sid)
        ok(f"'{student.name}' is now active again.")
    else:
        REGISTRY.archive_student(sid)
        ok(f"'{student.name}' is now archived (read-only).")
    pause()


@_handle
def action_import_csv() -> None:
    header("IMPORT FROM CSV")
    path = ask("CSV file path")
    if not os.path.exists(path):
        err("File not found.")
        pause()
        return
    count = REGISTRY.import_csv_data(path)
    ok(f"Import complete — {count} new student(s) added.")
    pause()


@_handle
def action_export() -> None:
    header("EXPORT DATA")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"  {col(1, C.CYN, C.B)}. Export to CSV")
    print(f"  {col(2, C.CYN, C.B)}. Export plain-text report")
    print()
    choice = ask("Option")
    if choice == "1":
        path = f"export_{ts}.csv"
        rows = REGISTRY.export_csv(path)
        ok(f"CSV saved: {path}  ({rows} records)")
    elif choice == "2":
        path = f"report_{ts}.txt"
        REGISTRY.export_report(path)
        ok(f"Report saved: {path}")
    else:
        err("Invalid option.")
    pause()


@_handle
def action_delete_student() -> None:
    header("DELETE STUDENT")
    result = _pick_student()
    if not result:
        return
    sid, student = result
    print()
    warn(f"This will permanently delete '{student.name}' and all their records.")
    confirm = ask("Type  YES  to confirm")
    if confirm == "YES":
        REGISTRY.remove_student(sid)
        ok(f"Deleted: {student.name}")
    else:
        warn("Deletion cancelled.")
    pause()


# ── Main menu ─────────────────────────────────────────────────────────────────
MENU = [
    ("Add Student",                   action_add_student),
    ("Add Grade Record",              action_add_record),
    ("View Student Report",           action_view_student),
    ("Class Overview",                action_class_overview),
    ("Subject Analysis",              action_subject_analysis),
    ("Change Grading Scale",          action_change_scale),
    ("Archive / Unarchive Student",   action_archive_student),
    ("Import from CSV",               action_import_csv),
    ("Export Data",                   action_export),
    ("Delete Student",                action_delete_student),
]


def main() -> None:
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        header("STA 2240  —  STUDENT PERFORMANCE TRACKER  (M3 & M4)")
        for i, (label, _) in enumerate(MENU, 1):
            print(f"  {col(i, C.CYN, C.B)}. {label}")
        print(f"\n  {col(0, C.RED, C.B)}. Exit")
        print()
        choice = ask("Select option")
        if choice == "0":
            print(col("\n  Goodbye!\n", C.CYN, C.B))
            sys.exit(0)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(MENU):
                MENU[idx][1]()
            else:
                err("Invalid option.")
                pause()
        except ValueError:
            err("Please enter a number.")
            pause()


if __name__ == "__main__":
    main()
