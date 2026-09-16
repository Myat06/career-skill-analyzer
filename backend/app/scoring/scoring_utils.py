"""Small generic scoring helpers shared across scoring modules. Extracted from
the now-removed career_readiness.py (the blended Career Readiness score was
dropped as unreliable on fixture data), since these two helpers are generic
math, not specific to that feature: compute_gpa is also used standalone by
api/students.py's /profile endpoint, and weighted_average by resume_score.py.
"""

from app.models import Enrollment


def compute_gpa(graded: list[Enrollment], course_credits: dict[str, int]) -> float | None:
    """Credit-weighted GPA over already-completed, already-graded enrollments."""
    total_credits = sum(course_credits.get(e.course_code, 0) for e in graded)
    if not total_credits:
        return None
    return round(sum(e.grade_point * course_credits.get(e.course_code, 0) for e in graded) / total_credits, 2)


def weighted_average(components: list[tuple[float, float]]) -> float:
    """Weighted average over whichever (score, weight) components are
    actually present -- renormalizes over just those weights rather than
    assuming every component is always available, so a missing one degrades
    the result gracefully instead of requiring a caller-side special case."""
    total_weight = sum(w for _, w in components)
    return round(sum(s * w for s, w in components) / total_weight, 1) if total_weight else 0.0
