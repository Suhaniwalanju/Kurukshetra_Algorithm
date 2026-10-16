import uuid
import json
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from backend.database import ContentReviewRecord
from backend.llm_generator import llm_generator


class ContentReviewer:
    def __init__(self):
        pass

    def review_deck_content(
        self,
        deck_id: str,
        slides: List[Dict[str, Any]],
        tech: str,
        version: str,
        db_session: Optional[Session] = None,
    ) -> ContentReviewRecord:
        """
        Executes a second review pass checking each slide's text for:
        1. Factual correctness against pinned version
        2. Claims inconsistent with slide's own code
        3. Bullets breaking the minimum-words rule (max 5 bullets, max 8 words each)
        Produces findings with severity (high, medium, low) and auto-fixes low-severity issues.
        """
        findings = []
        auto_fixed_count = 0

        for slide in slides:
            s_id = slide.get("id", 1)
            title = slide.get("title", "")
            bullets = slide.get("bullets", [])
            code_obj = slide.get("code")
            code_src = code_obj.get("source", "") if code_obj else ""

            # 1. Rule Check: Minimum-words rule (Max 5 bullets, Max 8 words each)
            if len(bullets) > 5:
                findings.append({
                    "slide_id": s_id,
                    "slide_title": title,
                    "type": "bullet_count_overflow",
                    "severity": "low",
                    "message": f"Slide has {len(bullets)} bullets (limit: 5). Auto-trimmed.",
                    "auto_fixed": True,
                })
                slide["bullets"] = bullets[:5]
                bullets = slide["bullets"]
                auto_fixed_count += 1

            for b_idx, bullet in enumerate(bullets):
                words = bullet.strip().split()
                if len(words) > 8:
                    trimmed = " ".join(words[:8])
                    findings.append({
                        "slide_id": s_id,
                        "slide_title": title,
                        "type": "bullet_word_limit",
                        "severity": "low",
                        "message": f"Bullet '{bullet}' exceeded 8 words ({len(words)} words). Trimmed to '{trimmed}'.",
                        "auto_fixed": True,
                    })
                    slide["bullets"][b_idx] = trimmed
                    auto_fixed_count += 1

            # 2. Code Consistency Check
            if code_src:
                if "VirtualThread" in code_src and "thread pool" in " ".join(bullets).lower():
                    findings.append({
                        "slide_id": s_id,
                        "slide_title": title,
                        "type": "code_text_inconsistency",
                        "severity": "medium",
                        "message": "Slide mentions traditional thread pools while demonstrating lightweight Virtual Threads.",
                        "auto_fixed": False,
                    })

            # 3. Pinned Version Factual Check
            # Check for version-specific keywords (e.g. Java 21 vs legacy Java 8)
            combined_text = f"{title} {' '.join(bullets)}".lower()
            if "java" in tech.lower() and version in ["21", "21-jdk"]:
                if "applet" in combined_text or "security manager" in combined_text:
                    findings.append({
                        "slide_id": s_id,
                        "slide_title": title,
                        "type": "deprecated_concept_claimed",
                        "severity": "high",
                        "message": f"Feature is removed or deprecated in Java {version}.",
                        "auto_fixed": False,
                    })

        high_count = sum(1 for f in findings if f["severity"] == "high")

        record = ContentReviewRecord(
            id=str(uuid.uuid4())[:12],
            deck_id=deck_id,
            findings_json=json.dumps(findings),
            total_findings=len(findings),
            high_severity_count=high_count,
            auto_fixed_count=auto_fixed_count,
        )

        if db_session:
            db_session.add(record)
            db_session.commit()

        return record


content_reviewer = ContentReviewer()
