from typing import Dict, Any, List
from backend.database import DeckRecord, SnippetRecord
from backend.runtimes.registry import runtime_registry


def check_deck_staleness(deck_id: str, db_session) -> Dict[str, Any]:
    """
    Staleness check: Re-runs the saved deck's snippets against the current pinned image
    or adapter and flags broken or degraded slides.
    """
    deck_record = db_session.query(DeckRecord).filter(DeckRecord.id == deck_id).first()
    if not deck_record:
        raise ValueError(f"Deck {deck_id} not found.")

    tech = deck_record.tech or "Programming"
    runner = runtime_registry.get_runner(tech.lower())

    snippets = db_session.query(SnippetRecord).filter(SnippetRecord.deck_id == deck_id).all()

    broken_slides: List[int] = []
    deprecated_slides: List[int] = []
    details: List[Dict[str, Any]] = []

    for snip in snippets:
        code = snip.source_code
        status = "healthy"
        msg = "Verified against pinned runtime"
        replacement_api = None

        if runner:
            try:
                res = runner.execute(code, timeout_sec=10)
                if res.status != "pass":
                    status = "broken"
                    msg = res.stderr or res.stdout or f"Status: {res.status}"
                    broken_slides.append(snip.slide_id)
                elif res.deprecations:
                    status = "deprecated"
                    msg = f"Deprecation: {', '.join(res.deprecations)}"
                    deprecated_slides.append(snip.slide_id)
                    replacement_api = _suggest_replacement_api(res.deprecations[0], tech)
                elif res.warnings:
                    status = "warning"
                    msg = f"Warning: {', '.join(res.warnings)}"
            except Exception as e:
                status = "broken"
                msg = str(e)
                broken_slides.append(snip.slide_id)

        details.append({
            "slide_id": snip.slide_id,
            "snippet_id": snip.id,
            "status": status,
            "message": msg,
            "replacement_api": replacement_api
        })

    is_stale = len(broken_slides) > 0 or len(deprecated_slides) > 0

    return {
        "deck_id": deck_id,
        "is_stale": is_stale,
        "total_checked": len(snippets),
        "broken_slide_ids": broken_slides,
        "deprecated_slide_ids": deprecated_slides,
        "healthy_count": len(snippets) - len(broken_slides) - len(deprecated_slides),
        "details": details
    }


def _suggest_replacement_api(deprecation_msg: str, tech: str) -> str:
    msg_low = deprecation_msg.lower()
    if "thread.suspend" in msg_low or "thread.resume" in msg_low:
        return "Use java.util.concurrent abstractions or Future.cancel()"
    if "javax." in msg_low:
        return "Migrate to jakarta.* (Jakarta EE 9+ / Spring Boot 3+)"
    if "imp" in msg_low:
        return "import importlib"
    if "datetime.utcnow" in msg_low:
        return "datetime.datetime.now(datetime.timezone.utc)"
    return f"Consult the pinned official {tech} migration guide for approved replacement."
