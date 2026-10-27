import os
import re
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, g

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "brandguard.db")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-demo-secret-key")


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    connection = sqlite3.connect(DATABASE)
    connection.execute("""CREATE TABLE IF NOT EXISTS rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        rule_text TEXT NOT NULL,
        term TEXT DEFAULT '',
        replacement TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        revised_content TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'Needs review',
        findings_json TEXT NOT NULL DEFAULT '[]',
        reviewer_comment TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    count = connection.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    if count == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        defaults = [
            ("Terminology", "Use “customer” instead of “user” in customer-facing copy.", "user", "customer"),
            ("Restricted wording", "Avoid absolute guarantees such as “100% guaranteed”.", "100% guaranteed", ""),
            ("Tone", "Avoid exaggerated claims such as “best in the world”.", "best in the world", ""),
            ("Claims", "Claims with numbers or superlatives should be supported by an approved fact.", "fastest", ""),
            ("Accessibility", "Use a clear call to action and avoid excessively long copy.", "", ""),
        ]
        connection.executemany(
            "INSERT INTO rules (category, rule_text, term, replacement, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            [(a, b, c, d, now) for a, b, c, d in defaults]
        )
    connection.commit()
    connection.close()


def analyze_content(content, rules):
    findings = []
    lower = content.lower()
    for rule in rules:
        term = (rule["term"] or "").strip()
        if term and term.lower() in lower:
            replacement = (rule["replacement"] or "").strip()
            if replacement:
                suggestion = re.sub(re.escape(term), replacement, content, flags=re.IGNORECASE)
                action = f"Consider replacing “{term}” with “{replacement}”."
            else:
                suggestion = content
                action = f"Remove or substantiate “{term}”."
            findings.append({
                "category": rule["category"],
                "severity": "Review",
                "matched": term,
                "rule": rule["rule_text"],
                "evidence": f"Matched configured rule #{rule['id']}: {rule['rule_text']}",
                "evidence_status": "Rule matched",
                "suggestion": action,
                "suggested_text": suggestion
            })

    # Heuristic: mark claims as unverified unless the approved facts are explicitly configured.
    claim_patterns = [
        r"\b\d+\s*%\b", r"\b\d+\s*(?:million|billion|thousand|k\+|users|customers)\b",
        r"\b(?:guaranteed|number one|no\.?\s*1|world's leading|world’s leading|instant results)\b"
    ]
    for pattern in claim_patterns:
        for match in re.finditer(pattern, content, flags=re.IGNORECASE):
            term = match.group(0)
            if any(f["matched"].lower() == term.lower() for f in findings):
                continue
            findings.append({
                "category": "Claims",
                "severity": "Verify",
                "matched": term,
                "rule": "Promotional or quantitative claims need an approved supporting fact.",
                "evidence": "No approved source library is configured for this claim in the MVP.",
                "evidence_status": "Unverified — not automatically false",
                "suggestion": "Add an approved source, soften the wording, or remove the claim.",
                "suggested_text": content
            })

    words = re.findall(r"\b[\w'-]+\b", content)
    if len(words) > 100:
        findings.append({
            "category": "Accessibility",
            "severity": "Suggestion",
            "matched": f"{len(words)} words",
            "rule": "Keep customer-facing copy concise and easy to scan.",
            "evidence": f"The draft contains {len(words)} words; the prototype uses 100 words as a review prompt.",
            "evidence_status": "Heuristic check",
            "suggestion": "Consider shortening the draft and splitting long sentences.",
            "suggested_text": content
        })

    if not content.strip():
        return []
    return findings


@app.route("/")
def index():
    connection = db()
    total = connection.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    pending = connection.execute("SELECT COUNT(*) FROM reviews WHERE status != 'Approved'").fetchone()[0]
    approved = connection.execute("SELECT COUNT(*) FROM reviews WHERE status = 'Approved'").fetchone()[0]
    recent = connection.execute("SELECT * FROM reviews ORDER BY id DESC LIMIT 5").fetchall()
    rules_count = connection.execute("SELECT COUNT(*) FROM rules WHERE active = 1").fetchone()[0]
    return render_template("index.html", total=total, pending=pending, approved=approved,
                           recent=recent, rules_count=rules_count)


@app.route("/rules", methods=["GET", "POST"])
def rules():
    connection = db()
    if request.method == "POST":
        category = request.form.get("category", "").strip()
        rule_text = request.form.get("rule_text", "").strip()
        term = request.form.get("term", "").strip()
        replacement = request.form.get("replacement", "").strip()
        if not category or not rule_text:
            flash("Category and rule description are required.", "error")
        else:
            connection.execute(
                "INSERT INTO rules (category, rule_text, term, replacement, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
                (category, rule_text, term, replacement, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            connection.commit()
            flash("Brand rule added successfully.", "success")
        return redirect(url_for("rules"))
    rows = connection.execute("SELECT * FROM rules ORDER BY active DESC, id DESC").fetchall()
    return render_template("rules.html", rules=rows)


@app.post("/rules/<int:rule_id>/toggle")
def toggle_rule(rule_id):
    connection = db()
    connection.execute("UPDATE rules SET active = CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?", (rule_id,))
    connection.commit()
    flash("Rule status updated.", "success")
    return redirect(url_for("rules"))


@app.route("/review", methods=["GET", "POST"])
def new_review():
    if request.method == "POST":
        title = request.form.get("title", "").strip() or "Untitled content"
        content = request.form.get("content", "").strip()
        if not content:
            flash("Paste some content before running the review.", "error")
            return render_template("review.html", title=title, content=content, findings=None, review_id=None)
        rules = db().execute("SELECT * FROM rules WHERE active = 1 ORDER BY id").fetchall()
        findings = analyze_content(content, rules)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor = db().execute(
            "INSERT INTO reviews (title, content, revised_content, status, findings_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (title, content, content, "Needs review" if findings else "Ready for human review",
             json.dumps(findings, ensure_ascii=False), now, now)
        )
        db().commit()
        return redirect(url_for("review_detail", review_id=cursor.lastrowid))
    return render_template("review.html", title="", content="", findings=None, review_id=None)


@app.route("/review/<int:review_id>", methods=["GET", "POST"])
def review_detail(review_id):
    connection = db()
    review = connection.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if review is None:
        flash("Review not found.", "error")
        return redirect(url_for("history"))
    findings = json.loads(review["findings_json"] or "[]")
    if request.method == "POST":
        action = request.form.get("action", "")
        revised = request.form.get("revised_content", review["revised_content"] or review["content"]).strip()
        comment = request.form.get("reviewer_comment", "").strip()
        if action == "save_revision":
            status = "Needs review"
            message = "Revision saved. Run a fresh check if you changed the text."
        elif action == "request_changes":
            status = "Changes requested"
            message = "Changes requested and saved to review history."
        elif action == "approve":
            status = "Approved"
            message = "Human approval recorded."
        elif action == "reject":
            status = "Rejected"
            message = "Rejection recorded."
        else:
            flash("Unknown review action.", "error")
            return redirect(url_for("review_detail", review_id=review_id))
        connection.execute(
            "UPDATE reviews SET revised_content = ?, status = ?, reviewer_comment = ?, updated_at = ? WHERE id = ?",
            (revised, status, comment, datetime.now().strftime("%Y-%m-%d %H:%M"), review_id)
        )
        connection.commit()
        flash(message, "success")
        return redirect(url_for("review_detail", review_id=review_id))
    return render_template("detail.html", review=review, findings=findings)


@app.route("/history")
def history():
    rows = db().execute("SELECT * FROM reviews ORDER BY id DESC").fetchall()
    return render_template("history.html", reviews=rows)


@app.route("/review/<int:review_id>/recheck", methods=["POST"])
def recheck(review_id):
    connection = db()
    review = connection.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
    if review is None:
        flash("Review not found.", "error")
        return redirect(url_for("history"))
    content = request.form.get("revised_content", "").strip() or review["revised_content"] or review["content"]
    active_rules = connection.execute("SELECT * FROM rules WHERE active = 1 ORDER BY id").fetchall()
    findings = analyze_content(content, active_rules)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = "Needs review" if findings else "Ready for human review"
    connection.execute(
        "UPDATE reviews SET revised_content = ?, findings_json = ?, status = ?, updated_at = ? WHERE id = ?",
        (content, json.dumps(findings, ensure_ascii=False), status, now, review_id)
    )
    connection.commit()
    flash("Content checked again against the active rules.", "success")
    return redirect(url_for("review_detail", review_id=review_id))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
