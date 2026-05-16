from pipeline.nemotron_reasoning.engine import IncidentReport


def generate(report: IncidentReport) -> dict[str, str]:
    """
    Falls back to template-generated text if Nemotron didn't produce notifications.
    Returns {'short', 'medium', 'long'}.
    """
    n = report.notifications or {}

    short = n.get("short") or (
        "Suspicious activity detected." if report.incident_confirmed
        else "Security alert — please review."
    )

    medium = n.get("medium") or (
        f"Incident: {report.incident_type.replace('_', ' ').title()}. "
        f"Risk: {report.risk_level.upper()}. Action: {report.recommended_action.replace('_', ' ')}."
    )

    long = n.get("long") or (
        f"[{report.incident_id}] {report.summary} "
        f"Objects involved: {', '.join(report.objects_involved) or 'unknown'}. "
        f"Confidence: {report.confidence:.0%}. "
        f"Recommended action: {report.recommended_action.replace('_', ' ')}."
    )

    return {"short": short, "medium": medium, "long": long}
