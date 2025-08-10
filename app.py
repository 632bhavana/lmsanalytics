from flask import Flask, render_template, jsonify
import pandas as pd
import numpy as np
import os

app = Flask(__name__)

# ---------- CONFIG ----------
DATA_PATH = os.path.join("data", "dyashin_data_analytics_case_studies.xlsx")
SHEET_NAME = "LMSUsage"
# ----------------------------

def load_data():
    """Load and normalize LMSUsage sheet. Returns cleaned DataFrame."""
    df = pd.read_excel(DATA_PATH, sheet_name=SHEET_NAME)

    # Normalize column names: strip, lower, replace spaces with underscore
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    # Ensure expected columns exist (best-effort)
    expected = ["userid", "techno", "accessdate", "completionstatus", "time_spent", "device", "country"]
    # if some columns differ (e.g., techno vs course), try to find best matches
    # (simple heuristic)
    colmap = {}
    for c in df.columns:
        short = c.replace("_", "").lower()
        if "user" in short and "userid" not in df.columns:
            colmap[c] = "userid"
        if "tech" in short and "techno" not in df.columns:
            colmap[c] = "techno"
        if "access" in short and "accessdate" not in df.columns:
            colmap[c] = "accessdate"
        if "completion" in short and "completionstatus" not in df.columns:
            colmap[c] = "completionstatus"
        if "time" in short and "time_spent" not in df.columns:
            colmap[c] = "time_spent"
        if "device" in short and "device" not in df.columns:
            colmap[c] = "device"
        if "country" in short and "country" not in df.columns:
            colmap[c] = "country"
    if colmap:
        df = df.rename(columns=colmap)

    # Trim whitespace in string columns and lowercase completionstatus
    for c in df.select_dtypes(include="object").columns:
        df[c] = df[c].astype(str).str.strip()

    # Normalize completionstatus to lowercase trimmed form
    if "completionstatus" in df.columns:
        df["completionstatus"] = df["completionstatus"].str.strip().str.lower()

    # Parse dates
    if "accessdate" in df.columns:
        df["accessdate"] = pd.to_datetime(df["accessdate"], errors="coerce")

    # Ensure time_spent is numeric (minutes)
    if "time_spent" in df.columns:
        df["time_spent"] = pd.to_numeric(df["time_spent"], errors="coerce").fillna(0)

    return df

# load once at startup (re-load each request if you want "live" file edits)
lms_df = load_data()

# ----------------- API endpoints -----------------

@app.route("/")
def index():
    return render_template("index.html")  # frontend will be provided later

@app.route("/api/refresh")
def api_refresh():
    """Re-load data from file (useful during development)."""
    global lms_df
    lms_df = load_data()
    return jsonify({"status": "reloaded", "rows": len(lms_df)})

@app.route("/api/summary")
def api_summary():
    """Key KPIs: total users, most popular course, avg time overall, completions counts"""
    total_users = int(lms_df["userid"].nunique()) if "userid" in lms_df.columns else None
    most_popular = None
    if "techno" in lms_df.columns:
        vc = lms_df["techno"].value_counts()
        if not vc.empty:
            most_popular = vc.idxmax()

    avg_time_overall = float(lms_df["time_spent"].mean()) if "time_spent" in lms_df.columns else None

    completion_counts = {}
    if "completionstatus" in lms_df.columns:
        completion_counts = lms_df["completionstatus"].value_counts().to_dict()

    return jsonify({
        "total_users": total_users,
        "most_popular_course": most_popular,
        "avg_time_overall": round(avg_time_overall, 2) if avg_time_overall is not None else None,
        "completion_counts": completion_counts
    })

@app.route("/api/avg_time_per_course")
def api_avg_time_per_course():
    """Average time spent per course (minutes)"""
    if "techno" not in lms_df.columns or "time_spent" not in lms_df.columns:
        return jsonify({})
    s = lms_df.groupby("techno")["time_spent"].mean().round(2).sort_values(ascending=False)
    return jsonify(s.to_dict())

@app.route("/api/drop_offs")
def api_drop_offs():
    """
    Identify drop-off points: returns counts of non-completed per course and top drop-off courses.
    'drop-off' is any record where completionstatus != 'completed'
    """
    if "completionstatus" not in lms_df.columns or "techno" not in lms_df.columns:
        return jsonify({})
    mask = lms_df["completionstatus"] != "completed"
    drop_counts = lms_df[mask]["techno"].value_counts().to_dict()
    return jsonify({"drop_off_counts": drop_counts})

@app.route("/api/top_performing")
def api_top_performing():
    """Top performing courses based on number of completions"""
    if "completionstatus" not in lms_df.columns or "techno" not in lms_df.columns:
        return jsonify({})
    completed = lms_df[lms_df["completionstatus"] == "completed"]
    top = completed["techno"].value_counts().to_dict()
    return jsonify(top)

@app.route("/api/course_completion_percentages")
def api_course_completion_percentages():
    """Course-wise completion percentages"""
    if "techno" not in lms_df.columns or "completionstatus" not in lms_df.columns:
        return jsonify({})
    result = {}
    grouped = lms_df.groupby("techno")
    for course, g in grouped:
        total = len(g)
        completed = int((g["completionstatus"] == "completed").sum())
        result[course] = {
            "total": total,
            "completed": completed,
            "completion_percent": round((completed / total) * 100, 2) if total > 0 else 0.0
        }
    return jsonify(result)

@app.route("/api/most_least_time")
def api_most_least_time():
    """Return course where learners spend most and least (by mean time)"""
    if "techno" not in lms_df.columns or "time_spent" not in lms_df.columns:
        return jsonify({})
    mean_time = lms_df.groupby("techno")["time_spent"].mean()
    if mean_time.empty:
        return jsonify({})
    most = mean_time.idxmax()
    least = mean_time.idxmin()
    return jsonify({
        "most_time_course": most,
        "most_time_minutes": round(float(mean_time.max()), 2),
        "least_time_course": least,
        "least_time_minutes": round(float(mean_time.min()), 2)
    })

@app.route("/api/monthly_trends")
def api_monthly_trends():
    """Time-series: course accesses per month (overall and per course optionally)"""
    if "accessdate" not in lms_df.columns:
        return jsonify({})
    # overall accesses per month
    df = lms_df.copy()
    df["month"] = df["accessdate"].dt.to_period("M").astype(str)
    overall = df.groupby("month").size().sort_index().to_dict()

    # optional: top 5 courses monthly breakdown
    top_courses = lms_df["techno"].value_counts().index[:5].tolist() if "techno" in lms_df.columns else []
    per_course = {}
    for c in top_courses:
        per_course[c] = df[df["techno"] == c].groupby("month").size().sort_index().to_dict()

    return jsonify({"overall": overall, "per_course_top5": per_course})

@app.route("/api/device_usage")
def api_device_usage():
    """Device usage counts (desktop/mobile/tablet...)"""
    if "device" not in lms_df.columns:
        return jsonify({})
    return jsonify(lms_df["device"].value_counts().to_dict())

@app.route("/api/raw")
def api_raw():
    """Return raw records (careful – could be large)."""
    # convert timestamps to strings for JSON serialisation
    df = lms_df.copy()
    if "accessdate" in df.columns:
        df["accessdate"] = df["accessdate"].astype(str)
    return jsonify(df.to_dict(orient="records"))

# -------------------------------------------------

if __name__ == "__main__":
    # Quick startup check
    if not os.path.exists(DATA_PATH):
        raise SystemExit(f"Data file not found at {DATA_PATH}")
    print("Loaded rows:", len(lms_df))
    app.run(debug=True)
