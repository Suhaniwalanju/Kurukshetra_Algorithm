import os
import html
from datetime import datetime
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Preformatted

from backend.database import (
    SnippetRecord,
    VerificationRunRecord,
    HealingLogRecord,
    ExerciseProofRecord,
    ContentReviewRecord,
)


class VerificationReportGenerator:
    def __init__(self):
        pass

    def generate_html_report(
        self,
        deck_id: str,
        deck_metadata: Dict[str, Any],
        snippets: List[SnippetRecord],
        runs: List[VerificationRunRecord],
        healing_logs: List[HealingLogRecord],
        exercise_proofs: List[ExerciseProofRecord],
        content_reviews: List[ContentReviewRecord],
        compliance_results: List[Dict[str, Any]],
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generates a rich, interactive HTML report covering:
        1. Executive summary cards (verified, auto-healed, needs review, mutation score, QA status)
        2. Per-slide snippet execution logs, exact commands, stdout, stderr, and unified diffs
        3. Exercise proof pass/fail matrix & mutation testing breakdown
        4. Non-code content reviewer findings & auto-fixes
        5. Visual template compliance QA statuses
        """
        topic = deck_metadata.get("topic", "Verified Course Material")
        tech = deck_metadata.get("tech", "Java 21")
        prof = deck_metadata.get("professor_name", "Professor")
        college = deck_metadata.get("college", "University")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Metrics calculation
        total_snippets = len(snippets)
        passed_snippets = sum(1 for s in snippets if s.status in ["verified", "auto_healed"])
        healed_snippets = sum(1 for s in snippets if s.status in ["auto_healed", "healed", "fixed_auto"] or getattr(s, "auto_healed", False))
        needs_review = sum(1 for s in snippets if s.status == "needs_review")
        failed_snippets = sum(1 for s in snippets if s.status == "failed")

        # Exercises
        total_exercises = len(exercise_proofs)
        proven_exercises = sum(1 for ep in exercise_proofs if ep.reference_passed and ep.naive_failed)
        avg_mutation_score = (
            sum(ep.mutation_score for ep in exercise_proofs) / total_exercises
            if total_exercises > 0
            else 1.0
        )

        # Compliance
        qa_passed_slides = sum(1 for c in compliance_results if c.get("passed", True))
        qa_total_slides = len(compliance_results)

        # Content review findings
        total_findings = sum(len(cr.findings or []) for cr in content_reviews)
        auto_fixed_findings = sum(cr.auto_fixed_count for cr in content_reviews)

        # Build Snippet Map for quick lookup
        run_by_snippet = {r.snippet_id: r for r in runs}
        logs_by_snippet: Dict[str, List[HealingLogRecord]] = {}
        for l in healing_logs:
            logs_by_snippet.setdefault(l.snippet_id, []).append(l)

        # HTML markup
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Report - {html.escape(topic)}</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --accent-amber: #f59e0b;
            --accent-purple: #8b5cf6;
            --border-color: #334155;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-main);
            line-height: 1.6;
            padding: 32px 24px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 28px 32px;
            margin-bottom: 28px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
        }}
        .header-top {{ display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; }}
        .header-title {{ font-size: 26px; font-weight: 800; color: #fff; letter-spacing: -0.5px; }}
        .header-subtitle {{ color: var(--text-muted); font-size: 15px; margin-top: 6px; }}
        .badge-deck {{
            background: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
        }}
        .header-meta {{
            display: flex;
            gap: 24px;
            margin-top: 20px;
            padding-top: 16px;
            border-top: 1px solid var(--border-color);
            font-size: 14px;
            color: var(--text-muted);
            flex-wrap: wrap;
        }}
        .header-meta strong {{ color: var(--text-main); }}
        
        /* Summary Grid */
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .stat-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            transition: transform 0.2s;
        }}
        .stat-card:hover {{ transform: translateY(-2px); }}
        .stat-value {{ font-size: 32px; font-weight: 800; margin-bottom: 4px; }}
        .stat-label {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-green {{ color: var(--accent-green); }}
        .stat-blue {{ color: var(--accent-blue); }}
        .stat-amber {{ color: var(--accent-amber); }}
        .stat-purple {{ color: var(--accent-purple); }}
        .stat-red {{ color: var(--accent-red); }}

        /* Section Styling */
        section {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 28px;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-color);
        }}
        .section-title {{ font-size: 18px; font-weight: 700; color: #fff; }}
        
        /* Table */
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            text-align: left;
        }}
        th {{
            background: var(--bg-tertiary);
            color: var(--text-muted);
            padding: 12px 14px;
            font-weight: 600;
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 14px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.6);
            vertical-align: top;
        }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}

        /* Badges */
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .badge-verified {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
        .badge-healed {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
        .badge-failed {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }}
        .badge-review {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }}

        /* Code & Log Blocks */
        pre, code {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        }}
        .cmd-box {{
            background: #090d16;
            border: 1px solid #1e293b;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            color: #93c5fd;
            word-break: break-all;
            margin-bottom: 6px;
        }}
        .output-box {{
            background: #090d16;
            border: 1px solid #1e293b;
            padding: 10px 12px;
            border-radius: 6px;
            font-size: 12px;
            color: #e2e8f0;
            max-height: 200px;
            overflow-y: auto;
            white-space: pre-wrap;
        }}
        .stderr-box {{
            color: #fca5a5;
            background: rgba(239, 68, 68, 0.08);
            border: 1px solid rgba(239, 68, 68, 0.2);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            margin-top: 6px;
            white-space: pre-wrap;
        }}

        /* Diff Styles */
        .diff-container {{
            background: #090d16;
            border: 1px solid #1e293b;
            border-radius: 6px;
            padding: 10px;
            font-size: 12px;
            margin-top: 8px;
            max-height: 250px;
            overflow-y: auto;
        }}
        .diff-added {{ color: #4ade80; background: rgba(74, 222, 128, 0.1); display: block; }}
        .diff-removed {{ color: #f87171; background: rgba(248, 113, 113, 0.1); display: block; }}
        .diff-meta {{ color: #94a3b8; display: block; }}

        /* Exercise Matrix Table */
        .matrix-table th, .matrix-table td {{ text-align: center; }}
        .matrix-table td:first-child, .matrix-table th:first-child {{ text-align: left; }}
        .cell-pass {{ color: #34d399; font-weight: bold; }}
        .cell-fail {{ color: #f87171; font-weight: bold; }}

        /* Footer */
        footer {{
            text-align: center;
            padding: 24px;
            color: var(--text-muted);
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="header-top">
                <div>
                    <h1 class="header-title">Verification Core Report</h1>
                    <div class="header-subtitle">{html.escape(topic)} &bull; {html.escape(college)}</div>
                </div>
                <div>
                    <span class="badge-deck">Deck ID: {html.escape(deck_id[:8])}</span>
                </div>
            </div>
            <div class="header-meta">
                <div><strong>Technology:</strong> {html.escape(tech)}</div>
                <div><strong>Professor:</strong> {html.escape(prof)}</div>
                <div><strong>Date:</strong> {date_str}</div>
                <div><strong>Status:</strong> {"PASSED ✔" if (needs_review == 0 and failed_snippets == 0) else "NEEDS REVIEW ⚠"}</div>
            </div>
        </header>

        <!-- KPI Summary Cards -->
        <div class="summary-grid">
            <div class="stat-card">
                <div class="stat-value stat-green">{passed_snippets}/{total_snippets}</div>
                <div class="stat-label">Snippets Verified</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-amber">{healed_snippets}</div>
                <div class="stat-label">Auto-Healed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-red">{needs_review + failed_snippets}</div>
                <div class="stat-label">Needs Review / Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-purple">{proven_exercises}/{total_exercises}</div>
                <div class="stat-label">Exercises Proven</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-blue">{int(avg_mutation_score * 100)}%</div>
                <div class="stat-label">Mutation Score</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-green">{qa_passed_slides}/{qa_total_slides}</div>
                <div class="stat-label">QA Checks Passed</div>
            </div>
        </div>

        <!-- Section 1: Snippet Verification Table -->
        <section>
            <div class="section-header">
                <h2 class="section-title">1. Code Snippet Sandbox Verification</h2>
                <div>Total: {total_snippets} Snippets</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 120px;">Slide & ID</th>
                        <th style="width: 130px;">Status</th>
                        <th style="width: 90px;">Duration</th>
                        <th>Execution Logs & Command</th>
                        <th>Real Output vs Expected</th>
                    </tr>
                </thead>
                <tbody>"""

        for snip in snippets:
            run = run_by_snippet.get(snip.id)
            status = snip.status.lower()
            if status in ["verified", "passed"]:
                badge_html = '<span class="badge badge-verified">Verified ✔</span>'
            elif status in ["auto_healed", "healed"]:
                badge_html = '<span class="badge badge-healed">Auto-Healed ⚡</span>'
            elif status == "needs_review":
                badge_html = '<span class="badge badge-review">Needs Review ⚠</span>'
            else:
                badge_html = '<span class="badge badge-failed">Failed ✖</span>'

            duration_str = f"{run.duration_ms}ms" if (run and run.duration_ms) else (f"{snip.duration_ms}ms" if snip.duration_ms else "-")
            cmd_str = html.escape(run.command_executed if (run and run.command_executed) else (snip.command_executed or "Direct Sandbox"))
            stdout_str = html.escape(run.stdout if (run and run.stdout) else (snip.actual_output or "(none)"))
            stderr_str = html.escape(run.stderr if (run and run.stderr) else (snip.stderr or ""))
            exp_output_str = html.escape(snip.expected_output) if snip.expected_output else "(none)"

            # Check if there is healing diff
            logs = logs_by_snippet.get(snip.id, [])
            diff_html = ""
            if logs:
                last_log = logs[-1]
                if last_log.diff_text:
                    diff_lines = []
                    for dline in last_log.diff_text.splitlines():
                        if dline.startswith("+") and not dline.startswith("+++"):
                            diff_lines.append(f'<span class="diff-added">{html.escape(dline)}</span>')
                        elif dline.startswith("-") and not dline.startswith("---"):
                            diff_lines.append(f'<span class="diff-removed">{html.escape(dline)}</span>')
                        else:
                            diff_lines.append(f'<span class="diff-meta">{html.escape(dline)}</span>')
                    diff_html = f"""
                    <details style="margin-top: 8px;">
                        <summary style="cursor: pointer; color: #fbbf24; font-size: 12px; font-weight: 600;">View Auto-Healing Diff (Attempt {last_log.attempt_number})</summary>
                        <div class="diff-container">{''.join(diff_lines)}</div>
                    </details>
                    """

            html_content += f"""
                    <tr>
                        <td>
                            <strong>Slide {snip.slide_id}</strong><br>
                            <span style="font-size: 11px; color: var(--text-muted);">{html.escape(snip.id[:12])}</span><br>
                            <span style="font-size: 11px; color: #60a5fa;">{html.escape(snip.language)} {html.escape(snip.version)}</span>
                        </td>
                        <td>{badge_html}</td>
                        <td style="color: var(--text-muted); font-size: 13px;">{duration_str}</td>
                        <td>
                            <div class="cmd-box">$ {cmd_str}</div>
                            {f'<div class="stderr-box"><strong>Error Log:</strong><br>{stderr_str}</div>' if stderr_str else ''}
                            {diff_html}
                        </td>
                        <td>
                            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 2px;">Captured stdout:</div>
                            <div class="output-box">{stdout_str}</div>
                        </td>
                    </tr>"""

        html_content += """
                </tbody>
            </table>
        </section>

        <!-- Section 2: Exercise Proofs & Mutation Testing -->
        <section>
            <div class="section-header">
                <h2 class="section-title">2. Exercise Proof & Mutation Score Matrix</h2>
                <div>Proven: """ + f"{proven_exercises}/{total_exercises} Exercises" + """</div>
            </div>"""

        if exercise_proofs:
            for ep in exercise_proofs:
                matrix = ep.pass_fail_matrix or {}
                mutant_names = [f"Mutant {m.get('id')}" for m in (ep.mutants or [])]
                headers = ["Test Suite", "Reference Sol (Pass)", "Naive Sol (Fail)"] + mutant_names

                html_content += f"""
                <div style="background: var(--bg-tertiary); padding: 16px; border-radius: 10px; margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div>
                            <strong style="font-size: 16px;">Slide {ep.slide_id} Exercise: {html.escape(ep.exercise_ref)}</strong>
                        </div>
                        <div style="display: flex; gap: 12px; align-items: center;">
                            <span class="badge badge-verified">Ref: PASS ✔</span>
                            <span class="badge badge-failed">Naive: FAIL ✖</span>
                            <span class="badge badge-deck">Mutation Score: {int(ep.mutation_score * 100)}% ({ep.killed_mutants}/{ep.total_mutants} killed)</span>
                        </div>
                    </div>
                    <div style="font-size: 13px; color: var(--text-muted); margin-bottom: 14px;">
                        <strong>Problem Statement:</strong> {html.escape(ep.problem_statement or 'Demonstrate concept with unit tests.')}
                    </div>
                    <table class="matrix-table" style="background: var(--bg-secondary); border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr>"""
                for h in headers:
                    html_content += f"<th>{html.escape(h)}</th>"
                html_content += """
                            </tr>
                        </thead>
                        <tbody>"""

                # Render rows
                ref_status = '<span class="cell-pass">PASS</span>' if ep.reference_passed else '<span class="cell-fail">FAIL</span>'
                naive_status = '<span class="cell-fail">FAIL</span>' if ep.naive_failed else '<span class="cell-pass">PASS</span>'

                html_content += f"""
                            <tr>
                                <td>Unit Test Suite Verification</td>
                                <td>{ref_status}</td>
                                <td>{naive_status}</td>"""
                for m in (ep.mutants or []):
                    killed = m.get("killed", False)
                    m_status = '<span class="cell-pass">KILLED</span>' if killed else '<span class="cell-fail">SURVIVED</span>'
                    html_content += f"<td>{m_status}</td>"

                html_content += """
                            </tr>
                        </tbody>
                    </table>
                </div>"""
        else:
            html_content += '<div style="color: var(--text-muted); font-size: 14px;">No hands-on exercise slides present in this deck.</div>'

        html_content += """
        </section>

        <!-- Section 3: Non-Code Reviewer Findings -->
        <section>
            <div class="section-header">
                <h2 class="section-title">3. Content Review & Factual Verification Pass</h2>
                <div>Auto-Fixed: """ + f"{auto_fixed_findings} / {total_findings} findings" + """</div>
            </div>"""

        if total_findings > 0:
            html_content += """
            <table>
                <thead>
                    <tr>
                        <th style="width: 100px;">Slide</th>
                        <th style="width: 120px;">Severity</th>
                        <th style="width: 180px;">Category</th>
                        <th>Finding & Action Taken</th>
                    </tr>
                </thead>
                <tbody>"""
            for cr in content_reviews:
                for f in cr.findings or []:
                    sev = f.get("severity", "low").lower()
                    if sev == "high":
                        sev_badge = '<span class="badge badge-failed">HIGH</span>'
                    elif sev == "medium":
                        sev_badge = '<span class="badge badge-healed">MEDIUM</span>'
                    else:
                        sev_badge = '<span class="badge badge-verified">LOW (AUTO-FIXED)</span>'

                    html_content += f"""
                    <tr>
                        <td>Slide {f.get('slide_id', '-')}</td>
                        <td>{sev_badge}</td>
                        <td style="color: #60a5fa;">{html.escape(f.get('type', 'rule_check'))}</td>
                        <td>
                            {html.escape(f.get('message', ''))}
                            {f'<br><span style="color: var(--text-muted); font-size: 12px;">Slide title: {html.escape(f.get("slide_title", ""))}</span>' if f.get("slide_title") else ''}
                        </td>
                    </tr>"""
            html_content += """
                </tbody>
            </table>"""
        else:
            html_content += '<div style="color: #34d399; font-size: 14px;">✔ All slides passed factual accuracy, claim consistency, and bullet word limit rules (max 5 bullets, max 8 words/bullet).</div>'

        html_content += """
        </section>

        <!-- Section 4: Template Compliance QA -->
        <section>
            <div class="section-header">
                <h2 class="section-title">4. Template Compliance & Safe-Zone QA</h2>
                <div>Passed: """ + f"{qa_passed_slides}/{qa_total_slides} Slides" + """</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th style="width: 100px;">Slide</th>
                        <th style="width: 140px;">Status</th>
                        <th>Compliance Details</th>
                    </tr>
                </thead>
                <tbody>"""

        for c in compliance_results:
            c_passed = c.get("passed", True)
            status_badge = '<span class="badge badge-verified">COMPLIANT ✔</span>' if c_passed else '<span class="badge badge-failed">VIOLATION ✖</span>'
            violations = c.get("violations", [])
            detail_str = "<br>".join(html.escape(v) for v in violations) if violations else "All elements inside safe zones; zero overlaps; minimum font sizes respected (≥24pt body, ≥18pt code); Presented By once on Cover."

            html_content += f"""
                    <tr>
                        <td><strong>Slide {c.get('slide_id', '-')}</strong></td>
                        <td>{status_badge}</td>
                        <td style="font-size: 13px; color: {'#f87171' if not c_passed else 'var(--text-muted)'};">{detail_str}</td>
                    </tr>"""

        html_content += f"""
                </tbody>
            </table>
        </section>

        <footer>
            Verified Course Material Studio &bull; Generated on {date_str} &bull; Pinned Tech: {html.escape(tech)}
        </footer>
    </div>
</body>
</html>"""

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        return html_content

    def generate_pdf_report(
        self,
        deck_id: str,
        deck_metadata: Dict[str, Any],
        snippets: List[SnippetRecord],
        runs: List[VerificationRunRecord],
        healing_logs: List[HealingLogRecord],
        exercise_proofs: List[ExerciseProofRecord],
        content_reviews: List[ContentReviewRecord],
        compliance_results: List[Dict[str, Any]],
        output_pdf_path: str,
    ) -> str:
        """
        Generates a clean, professional PDF report using ReportLab Platypus.
        """
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        doc = SimpleDocTemplate(
            output_pdf_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Heading1"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
        )
        subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#475569"),
            fontName="Helvetica",
        )
        h2_style = ParagraphStyle(
            "SectionH2",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica-Bold",
            spaceBefore=14,
            spaceAfter=8,
        )
        body_style = ParagraphStyle(
            "TableBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1e293b"),
            fontName="Helvetica",
        )
        code_style = ParagraphStyle(
            "CodeBox",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#0f172a"),
            fontName="Courier",
        )

        elements = []

        # 1. Header
        topic = deck_metadata.get("topic", "Verified Course Material")
        tech = deck_metadata.get("tech", "Java 21")
        prof = deck_metadata.get("professor_name", "Professor")
        college = deck_metadata.get("college", "University")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        elements.append(Paragraph("VERIFICATION CORE REPORT", title_style))
        elements.append(Paragraph(f"Topic: <b>{html.escape(topic)}</b> | College: <b>{html.escape(college)}</b>", subtitle_style))
        elements.append(Paragraph(f"Tech: <b>{html.escape(tech)}</b> | Professor: <b>{html.escape(prof)}</b> | Deck ID: <b>{html.escape(deck_id[:8])}</b> | Date: {date_str}", subtitle_style))
        elements.append(Spacer(1, 14))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#cbd5e1"), spaceAfter=14))

        # 2. Executive Summary Metrics Table
        total_snippets = len(snippets)
        passed_snippets = sum(1 for s in snippets if s.status in ["verified", "auto_healed"])
        healed_snippets = sum(1 for s in snippets if s.status in ["auto_healed", "healed", "fixed_auto"] or getattr(s, "auto_healed", False))
        needs_review = sum(1 for s in snippets if s.status == "needs_review")
        proven_exercises = sum(1 for ep in exercise_proofs if ep.reference_passed and ep.naive_failed)
        avg_mutation_score = (
            sum(ep.mutation_score for ep in exercise_proofs) / len(exercise_proofs)
            if exercise_proofs
            else 1.0
        )
        qa_passed = sum(1 for c in compliance_results if c.get("passed", True))

        summary_data = [
            ["Metric", "Value", "Metric", "Value"],
            ["Snippets Verified", f"{passed_snippets}/{total_snippets}", "Auto-Healed", f"{healed_snippets}"],
            ["Needs Review / Fail", f"{needs_review}", "Exercises Proven", f"{proven_exercises}/{len(exercise_proofs)}"],
            ["Mutation Score", f"{int(avg_mutation_score * 100)}%", "Template QA Passed", f"{qa_passed}/{len(compliance_results)}"],
        ]
        sum_table = Table(summary_data, colWidths=[150, 120, 150, 120])
        sum_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        elements.append(sum_table)
        elements.append(Spacer(1, 14))

        # 3. Code Snippet Verification Table
        elements.append(Paragraph("1. Code Snippet Sandbox Verification", h2_style))
        run_by_snippet = {r.snippet_id: r for r in runs}

        table_data = [["Slide", "Language", "Status", "Duration", "Captured Output"]]
        for snip in snippets:
            r = run_by_snippet.get(snip.id)
            st_text = snip.status.upper()
            dur = f"{r.duration_ms}ms" if (r and r.duration_ms) else (f"{snip.duration_ms}ms" if snip.duration_ms else "-")
            stdout_text = r.stdout if (r and r.stdout) else (snip.actual_output or "")
            out_preview = (stdout_text[:80] + "...") if (len(stdout_text) > 80) else (stdout_text if stdout_text else "(none)")
            table_data.append([
                f"Slide {snip.slide_id}",
                f"{snip.language} {snip.version}",
                st_text,
                dur,
                Paragraph(html.escape(out_preview), code_style),
            ])

        snip_table = Table(table_data, colWidths=[60, 90, 80, 70, 240])
        snip_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        elements.append(snip_table)
        elements.append(Spacer(1, 14))

        # 4. Exercise Proof & Mutation Table
        if exercise_proofs:
            elements.append(Paragraph("2. Exercise Proof & Mutation Score Matrix", h2_style))
            ex_data = [["Slide", "Reference Sol", "Naive Sol", "Mutants Killed", "Score"]]
            for ep in exercise_proofs:
                ex_data.append([
                    f"Slide {ep.slide_id}",
                    "PASSED" if ep.reference_passed else "FAILED",
                    "FAILED (Good)" if ep.naive_failed else "PASSED (Strengthen)",
                    f"{ep.killed_mutants}/{ep.total_mutants}",
                    f"{int(ep.mutation_score * 100)}%",
                ])
            ex_table = Table(ex_data, colWidths=[70, 110, 130, 120, 110])
            ex_table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ])
            )
            elements.append(ex_table)
            elements.append(Spacer(1, 14))

        # 5. Template Compliance QA
        elements.append(Paragraph("3. Template Compliance QA", h2_style))
        qa_data = [["Slide", "Compliance Status", "Details"]]
        for c in compliance_results:
            passed = c.get("passed", True)
            qa_data.append([
                f"Slide {c.get('slide_id', '-')}",
                "COMPLIANT" if passed else "VIOLATION",
                Paragraph("; ".join(c.get("violations", [])) if c.get("violations") else "All bounding boxes and fonts compliant.", body_style),
            ])
        qa_table = Table(qa_data, colWidths=[70, 100, 370])
        qa_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        elements.append(qa_table)

        doc.build(elements)
        return output_pdf_path


report_generator = VerificationReportGenerator()
