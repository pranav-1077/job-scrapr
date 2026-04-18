import os
import smtplib
from collections import defaultdict
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class EmailNotifier:
    def __init__(self, config: dict):
        self.config = config

    def send(self, jobs: list[dict], email_only_companies: list[dict] | None = None,
             removed_jobs: list[dict] | None = None):
        password = os.environ.get("SMTP_PASSWORD") or self.config.get("smtp_password", "")
        if not password:
            raise RuntimeError(
                "SMTP_PASSWORD is not set. "
                "Add it to your .env file (Gmail App Password)."
            )

        msg = MIMEMultipart("alternative")
        today = date.today().strftime("%B %d, %Y")
        removed_jobs = removed_jobs or []
        parts = []
        if jobs:
            parts.append(f"{len(jobs)} new posting(s)")
        if removed_jobs:
            parts.append(f"{len(removed_jobs)} removed")
        msg["Subject"] = f"[job-scrapr] {', '.join(parts)} — {today}"
        msg["From"] = self.config["sender"]
        recipients = self.config["recipients"]
        msg["To"] = ", ".join(recipients)

        email_only_companies = email_only_companies or []
        msg.attach(MIMEText(self._build_plain(jobs, email_only_companies, removed_jobs), "plain"))
        msg.attach(MIMEText(self._build_html(jobs, email_only_companies, removed_jobs), "html"))

        with smtplib.SMTP(
            self.config.get("smtp_host", "smtp.gmail.com"),
            self.config.get("smtp_port", 587),
        ) as server:
            server.ehlo()
            server.starttls()
            server.login(self.config["sender"], password)
            server.sendmail(self.config["sender"], recipients, msg.as_string())

    # ── Plain text ──────────────────────────────────────────────────────────────
    def _build_plain(self, jobs: list[dict], email_only: list[dict],
                     removed_jobs: list[dict] | None = None) -> str:
        by_company: dict[str, list] = defaultdict(list)
        for j in jobs:
            by_company[j["company"]].append(j)

        lines = [f"New job postings — {date.today().isoformat()}", ""]
        for company in sorted(by_company):
            lines.append(f"── {company} ──")
            for j in by_company[company]:
                loc = f" [{j['location']}]" if j.get("location") else ""
                posted = f" · posted {j['posted_at']}" if j.get("posted_at") else ""
                lines.append(f"  • {j['title']}{loc}{posted}")
                lines.append(f"    {j['url']}")
            lines.append("")

        if removed_jobs:
            removed_by_company: dict[str, list] = defaultdict(list)
            for r in removed_jobs:
                removed_by_company[r["company"]].append(r)
            lines += ["", "─" * 60, "Removed postings (no longer listed):", ""]
            for company in sorted(removed_by_company):
                lines.append(f"── {company} ──")
                for r in removed_by_company[company]:
                    loc = f" [{r['location']}]" if r.get("location") else ""
                    lines.append(f"  ✕ {r['title']}{loc}")
                    if r.get("url"):
                        lines.append(f"    {r['url']}")
                lines.append("")

        if email_only:
            lines += ["", "─" * 60, "Email-only companies (apply directly):", ""]
            for co in sorted(email_only, key=lambda c: c["name"]):
                email = co.get("resume_email", "")
                url = co.get("careers_url", "")
                parts = [f"  • {co['name']}"]
                if email:
                    parts.append(f"    Email: {email}")
                if url:
                    parts.append(f"    Web:   {url}")
                lines += parts

        return "\n".join(lines)

    # ── HTML ────────────────────────────────────────────────────────────────────
    def _build_html(self, jobs: list[dict], email_only: list[dict],
                    removed_jobs: list[dict] | None = None) -> str:
        by_company: dict[str, list] = defaultdict(list)
        for j in jobs:
            by_company[j["company"]].append(j)

        rows = []
        for company in sorted(by_company):
            first = True
            for j in by_company[company]:
                dept = j.get("department") or ""
                loc = j.get("location") or ""
                posted = j.get("posted_at") or ""
                co_cell = (
                    f'<td rowspan="{len(by_company[company])}" style="{TD} font-weight:600;'
                    f'vertical-align:top;border-right:2px solid #e5e7eb;">{company}</td>'
                    if first else ""
                )
                rows.append(
                    f"<tr>"
                    f"{co_cell}"
                    f'<td style="{TD}"><a href="{j["url"]}" style="color:#2563eb;text-decoration:none;">'
                    f'{j["title"]}</a></td>'
                    f'<td style="{TD} color:#6b7280;">{loc}</td>'
                    f'<td style="{TD} color:#6b7280;">{dept}</td>'
                    f'<td style="{TD} color:#6b7280;">{posted}</td>'
                    f"</tr>"
                )
                first = False

        today = date.today().strftime("%B %d, %Y")
        table_rows = "\n".join(rows)
        new_jobs_html = f"""
    <div style="padding:24px;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#f3f4f6;">
            <th style="{TH}">Company</th>
            <th style="{TH}">Role</th>
            <th style="{TH}">Location</th>
            <th style="{TH}">Department</th>
            <th style="{TH}">Posted</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>
    </div>""" if jobs else ""

        removed_html = ""
        if removed_jobs:
            removed_by_company: dict[str, list] = defaultdict(list)
            for r in removed_jobs:
                removed_by_company[r["company"]].append(r)
            removed_rows = []
            for company in sorted(removed_by_company):
                first = True
                for r in removed_by_company[company]:
                    loc = r.get("location") or ""
                    dept = r.get("department") or ""
                    co_cell = (
                        f'<td rowspan="{len(removed_by_company[company])}" style="{TD} font-weight:600;'
                        f'vertical-align:top;border-right:2px solid #fecaca;color:#6b7280;">{company}</td>'
                        if first else ""
                    )
                    title_cell = (
                        f'<a href="{r["url"]}" style="color:#9ca3af;text-decoration:line-through;">'
                        f'{r["title"]}</a>'
                        if r.get("url") else
                        f'<span style="color:#9ca3af;text-decoration:line-through;">{r["title"]}</span>'
                    )
                    removed_rows.append(
                        f"<tr style='background:#fef2f2;'>"
                        f"{co_cell}"
                        f'<td style="{TD}">{title_cell}</td>'
                        f'<td style="{TD} color:#9ca3af;">{loc}</td>'
                        f'<td style="{TD} color:#9ca3af;">{dept}</td>'
                        f"</tr>"
                    )
                    first = False
            removed_html = f"""
    <div style="padding:24px;border-top:1px solid #fecaca;">
      <p style="margin:0 0 12px;font-size:12px;font-weight:600;color:#9ca3af;
                text-transform:uppercase;letter-spacing:.05em;">
        Removed postings &mdash; no longer listed
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:14px;">
        <thead>
          <tr style="background:#fef2f2;">
            <th style="{TH} color:#6b7280;">Company</th>
            <th style="{TH} color:#6b7280;">Role</th>
            <th style="{TH} color:#6b7280;">Location</th>
            <th style="{TH} color:#6b7280;">Department</th>
          </tr>
        </thead>
        <tbody>
          {chr(10).join(removed_rows)}
        </tbody>
      </table>
    </div>"""

        email_only_html = ""
        if email_only:
            co_items = []
            for co in sorted(email_only, key=lambda c: c["name"]):
                email_addr = co.get("resume_email", "")
                url = co.get("careers_url", "")
                email_part = (
                    f' &mdash; <a href="mailto:{email_addr}" style="color:#2563eb;text-decoration:none;">'
                    f'{email_addr}</a>' if email_addr else ""
                )
                url_part = (
                    f' &mdash; <a href="{url}" style="color:#2563eb;text-decoration:none;">'
                    f'website</a>' if url else ""
                )
                co_items.append(
                    f'<li style="margin:4px 0;">{co["name"]}{email_part}{url_part}</li>'
                )
            email_only_html = f"""
    <div style="padding:16px 24px;border-top:1px solid #e5e7eb;background:#f9fafb;">
      <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#6b7280;
                text-transform:uppercase;letter-spacing:.05em;">
        Email-only companies &mdash; apply directly
      </p>
      <ul style="margin:0;padding-left:16px;font-size:12px;color:#374151;list-style:disc;">
        {"".join(co_items)}
      </ul>
    </div>"""

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             background:#f9fafb;margin:0;padding:24px;">
  <div style="max-width:860px;margin:0 auto;background:#fff;border-radius:8px;
              box-shadow:0 1px 3px rgba(0,0,0,.1);overflow:hidden;">
    <div style="background:#1e40af;color:#fff;padding:20px 24px;">
      <h1 style="margin:0;font-size:20px;">job-scrapr</h1>
      <p style="margin:4px 0 0;opacity:.85;font-size:14px;">
        {len(jobs)} new posting(s){f" &mdash; {len(removed_jobs)} removed" if removed_jobs else ""} &mdash; {today}
      </p>
    </div>
    {new_jobs_html}
    {removed_html}
    {email_only_html}
    <div style="padding:12px 24px;border-top:1px solid #e5e7eb;
                font-size:12px;color:#9ca3af;text-align:center;">
      job-scrapr &mdash; edit companies.yaml or config.yaml to customise
    </div>
  </div>
</body>
</html>"""


TD = "padding:10px 12px;border-bottom:1px solid #e5e7eb;"
TH = "padding:10px 12px;text-align:left;font-weight:600;border-bottom:2px solid #e5e7eb;"
