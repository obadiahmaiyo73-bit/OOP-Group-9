# OOP-Group-9
OOP Group project 
STUDENT PERFOMANCE TRACKER :

✓ It manages students, their grades, and generates analytics — all from the command line.

---

The 7 sections and what each does

Section 1 — Models
Two core classes: GradeRecord stores a single grade entry (subject, score, term, date, notes) and converts scores to letter grades (A–F). Student holds a list of grade records and supports iteration, filtering by subject, rolling averages, and best/worst record lookups.

Section 2 — Exceptions
A 10-class custom exception hierarchy. Examples: ScoreOutOfRangeError (score not in 0–100), StudentNotFoundError, DuplicateStudentError, CorruptDataError. This makes error messages precise and meaningful.

Section 3 — Pipeline
Uses functional programming (higher-order functions, reduce) and a ScoreQueue built on Python's deque to compute a sliding moving average of the last 5 scores per student.

Section 4 — Storage
Data is saved/loaded as JSON (with atomic writes and automatic backups), exportable to CSV, and printable as a plain-text report. An audit.log records every grade entry ever made.

Section 5 — Design Patterns (3 GoF)

Observer — notifies listeners whenever a grade is added (e.g. for logging)

Strategy — swappable grading scales (Standard, Strict, Lenient)

Decorator — wraps a Student with extra behaviour like GPA tracking or read-only enforcement (archived students)

Section 6 — Registry
A central service (REGISTRY) that manages all students — adding, removing, archiving, looking up, computing class averages, and importing CSV data.

Section 7 — UI / Main Menu
A colour-coded terminal interface with 10 menu options:

#	Option

1	Add Student
2	Add Grade Record
3	View Student Report
4	Class Overview (ranked leaderboard)
5	Subject Analysis (avg, median, pass rate)
6	Change Grading Scale
7	Archive / Unarchive Student
8	Import from CSV
9	Export to CSV or text report
10	Delete Student
