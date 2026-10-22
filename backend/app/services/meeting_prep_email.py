from __future__ import annotations

import html as html_mod

from app.core.config import settings


def compose_prep_email(
    meeting: dict,
    briefs: list[dict],
    talking_points: str,
) -> tuple[str, str]:
    """Render the meeting-prep email as (subject, html_body).

    Parameters
    ----------
    meeting:
        Dict with ``title``, ``occurred_at``, ``contact_ids``.
    briefs:
        List of attendee brief dicts from :func:`build_prep_brief`.
    talking_points:
        AI-generated talking points (may be empty).

    Returns
    -------
    A ``(subject, html_body)`` tuple.
    """
    esc = html_mod.escape
    base_url = settings.FRONTEND_URL
    title = esc(meeting.get("title", "Untitled meeting"))
    raw_title = meeting.get("title", "Untitled meeting")
    subject = f"Meeting prep: {raw_title} in 30 minutes"
    subject = subject.replace("\r", "").replace("\n", " ")  # prevent CRLF header injection

    # --- Attendee cards ---
    attendee_cards = ""
    for b in briefs:
        name = esc(b.get("name") or "Unknown")
        job_title = esc(b.get("title") or "")
        company = esc(b.get("company") or "")
        score = b.get("score", 0)
        score_label = esc(b.get("score_label", "Cold"))

        # Score badge colour
        if score >= 7:
            badge_color = "#16a34a"  # green
        elif score >= 4:
            badge_color = "#d97706"  # amber
        else:
            badge_color = "#6b7280"  # gray

        # Subtitle line
        subtitle_parts = [p for p in [job_title, company] if p]
        subtitle = " at ".join(subtitle_parts) if subtitle_parts else ""

        # Bio lines — only show platform-specific bios with correct labels
        bio_lines_html = ""
        if b.get("twitter_bio"):
            bio_lines_html += f'<p style="margin:4px 0;font-size:13px;color:#6b7280;"><strong>Twitter:</strong> {esc(b["twitter_bio"][:200])}</p>'
        if b.get("linkedin_headline"):
            bio_lines_html += f'<p style="margin:4px 0;font-size:13px;color:#6b7280;"><strong>LinkedIn:</strong> {esc(b["linkedin_headline"][:200])}</p>'
        if b.get("telegram_bio"):
            bio_lines_html += f'<p style="margin:4px 0;font-size:13px;color:#6b7280;"><strong>Telegram:</strong> {esc(b["telegram_bio"][:200])}</p>'

        # Recent interactions
        recent_html = ""
        for ri in b.get("recent_interactions", [])[:3]:
            preview = esc((ri.get("preview") or "")[:120])
            platform = esc(ri.get("platform", ""))
            date_val = ri.get("date")
            if hasattr(date_val, "strftime"):
                date_str = date_val.strftime("%b %d")
            else:
                date_str = str(date_val)[:10] if date_val else ""
            recent_html += (
                f'<tr>'
                f'<td style="padding:4px 8px;font-size:12px;color:#9ca3af;white-space:nowrap;">{esc(date_str)}</td>'
                f'<td style="padding:4px 8px;font-size:12px;color:#9ca3af;white-space:nowrap;">{platform}</td>'
                f'<td style="padding:4px 8px;font-size:13px;color:#374151;">{preview}</td>'
                f'</tr>'
            )

        recent_table = ""
        if recent_html:
            recent_table = (
                f'<table style="width:100%;border-collapse:collapse;margin-top:12px;">'
                f'<tr style="border-bottom:1px solid #e5e7eb;">'
                f'<th style="text-align:left;padding:4px 8px;font-size:11px;color:#9ca3af;font-weight:600;">Date</th>'
                f'<th style="text-align:left;padding:4px 8px;font-size:11px;color:#9ca3af;font-weight:600;">Channel</th>'
                f'<th style="text-align:left;padding:4px 8px;font-size:11px;color:#9ca3af;font-weight:600;">Preview</th>'
                f'</tr>'
                f'{recent_html}'
                f'</table>'
            )

        attendee_cards += f"""
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
          <p style="margin:0;font-size:18px;font-weight:600;color:#111827;">{name}</p>
          {'<p style="margin:2px 0 0;font-size:13px;color:#6b7280;">' + esc(subtitle) + '</p>' if subtitle else ''}
          <span style="display:inline-block;margin-top:6px;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:600;color:#ffffff;background:{badge_color};">{score_label} ({score}/10)</span>
          {('<div style="margin-top:10px;">' + bio_lines_html + '</div>') if bio_lines_html else ''}
          {recent_table}
        </div>
        """

    # --- Talking points section ---
    talking_points_section = ""
    if talking_points:
        # Convert markdown **bold** to <strong> and bullet points to <li>
        tp_html = ""
        for line in talking_points.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            # Strip leading bullet markers
            clean = line.lstrip("•-* ").strip()
            if not clean:
                continue
            # Convert **bold** to <strong>
            import re
            clean = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', clean)
            tp_html += f'<li style="margin-bottom:8px;">{clean}</li>'

        if tp_html:
            talking_points_section = f"""
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin-bottom:20px;">
              <h2 style="margin:0 0 12px;font-size:16px;color:#166534;">Suggested Talking Points</h2>
              <ul style="margin:0;padding-left:20px;font-size:14px;color:#374151;line-height:1.5;">{tp_html}</ul>
            </div>
            """

    # --- Full HTML ---
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8" /></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table style="width:100%;background:#f3f4f6;padding:20px 0;" cellpadding="0" cellspacing="0">
    <tr><td align="center">
      <table style="width:600px;max-width:100%;background:#ffffff;border-radius:12px;overflow:hidden;" cellpadding="0" cellspacing="0">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#0d9488,#14b8a6);padding:24px 32px;">
            <h1 style="margin:0;font-size:20px;color:#ffffff;">Meeting Prep</h1>
            <p style="margin:4px 0 0;font-size:14px;color:#ccfbf1;">{title}</p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:24px 32px;">
            <h2 style="margin:0 0 16px;font-size:16px;color:#374151;">Attendees</h2>
            {attendee_cards}
            {talking_points_section}
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;text-align:center;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
              Sent by <a href="{esc(base_url)}" style="color:#0d9488;text-decoration:none;">PingCRM</a>
              &middot;
              <a href="{esc(base_url)}/settings" style="color:#0d9488;text-decoration:none;">Manage preferences</a>
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return subject, html_body
