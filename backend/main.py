import json
import os
import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# ================= CONFIGURATION =================
app = FastAPI()

# Allow frontend to talk to backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "user_data.json"
START_DATE = datetime.date(2026, 1, 1)

# ================= DATA MODELS (Pydantic) =================
class LogEntry(BaseModel):
    date: str
    action_type: str  # 'academic', 'skill', 'workout', 'reflection'
    xp: int
    note: str

class ReflectionEntry(BaseModel):
    date: str
    academic_topic: str
    skill_topic: str
    # Removed 'score' and 'feedback' since AI is gone. 
    # Now we just store the user's raw thoughts.
    user_notes: str 

class UserProfile(BaseModel):
    username: str
    level: int = 1
    xp: int = 0
    xp_limit: int = 100
    logs: List[LogEntry] = []
    reflections: List[ReflectionEntry] = []

class ActionRequest(BaseModel):
    username: str
    action_type: str 

# ================= LOGIC ENGINES =================

def load_db():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def calculate_progression():
    """Calculates Gym Sets and Skill Phase based on 2026 date."""
    today = datetime.date.today()
    # Logic: If today is before 2026, treat it as Jan 1 2026 for testing
    calc_date = max(today, START_DATE)
    
    days_passed = (calc_date - START_DATE).days
    weeks_passed = days_passed // 7
    
    # 1. Gym Progression (Base 3, +1 every 3 weeks, Cap 6)
    gym_sets = min(6, 3 + (weeks_passed // 3))
    
    # 2. Skill Phase Logic (0=Jan, 1=Feb, 2=Mar, 3=Apr)
    current_month = calc_date.month 
    
    if calc_date.year > 2026: phase_idx = 3
    elif current_month == 1: phase_idx = 0
    elif current_month == 2: phase_idx = 1
    elif current_month == 3: phase_idx = 2
    else: phase_idx = 3 

    return {
        "days_passed": days_passed,
        "weeks_passed": weeks_passed,
        "gym_sets": gym_sets,
        "phase_index": phase_idx,
        "date_str": calc_date.strftime("%Y-%m-%d")
    }

# ================= API ENDPOINTS =================

@app.post("/login")
def login(user: UserProfile):
    db = load_db()
    if user.username not in db:
        db[user.username] = user.dict()
        save_db(db)
    return db[user.username]

@app.get("/dashboard/{username}")
def get_dashboard(username: str):
    db = load_db()
    if username not in db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = db[username]
    progression = calculate_progression()
    today_str = progression["date_str"]

    # Check Locks
    today_logs = [log for log in user['logs'] if log['date'] == today_str]
    locks = {
        "academic": any(l['action_type'] == 'academic' for l in today_logs),
        "skill": any(l['action_type'] == 'skill' for l in today_logs),
        "workout": any(l['action_type'] == 'workout' for l in today_logs),
        # Check if a reflection exists for today
        "reflection": any(r['date'] == today_str for r in user.get('reflections', []))
    }

    return {
        "user": user,
        "progression": progression,
        "locks": locks
    }

@app.post("/complete-task")
def complete_task(req: ActionRequest):
    db = load_db()
    if req.username not in db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = db[req.username]
    progression = calculate_progression()
    today_str = progression["date_str"]

    # Lock Check
    today_logs = [log for log in user['logs'] if log['date'] == today_str]
    if any(l['action_type'] == req.action_type for l in today_logs):
        raise HTTPException(status_code=400, detail="Task already completed today.")

    xp_gain = 30
    user['xp'] += xp_gain
    
    new_log = {
        "date": today_str,
        "action_type": req.action_type,
        "xp": xp_gain,
        "note": f"Completed {req.action_type}"
    }
    user['logs'].append(new_log)

    # Level Up Logic
    if user['xp'] >= user['xp_limit']:
        user['level'] += 1
        user['xp'] -= user['xp_limit']
        user['xp_limit'] = int(user['xp_limit'] * 1.5)

    save_db(db)
    return {"status": "success", "new_xp": user['xp'], "new_level": user['level']}

@app.post("/submit-reflection")
def submit_reflection(req: ReflectionEntry, username: str):
    db = load_db()
    if username not in db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = db[username]
    
    # Store the manual note
    user['reflections'].append(req.dict())
    
    # Award Bonus XP (Fixed amount since no AI scoring)
    xp_bonus = 20
    user['xp'] += xp_bonus
    user['logs'].append({
        "date": req.date,
        "action_type": "reflection",
        "xp": xp_bonus,
        "note": "Daily Reflection Submitted"
    })

    save_db(db)
    return {"status": "success"}

@app.get("/analytics/{username}")
def get_analytics(username: str):
    db = load_db()
    if username not in db: return {}
    user = db[username]
    
    # XP History
    logs = sorted(user['logs'], key=lambda x: x['date'])
    xp_labels = []
    xp_data = []
    running_xp = 0
    for log in logs:
        running_xp += log['xp']
        xp_labels.append(log['date'])
        xp_data.append(running_xp)

    # Reflections (Just count them for consistency chart)
    reflections = sorted(user['reflections'], key=lambda x: x['date'])
    # Since there is no "score", we chart "1" for completed, to show consistency
    consistency_labels = [r['date'] for r in reflections]
    consistency_data = [1 for _ in reflections] 

    return {
        "xp_chart": {"labels": xp_labels, "data": xp_data},
        "consistency_chart": {"labels": consistency_labels, "data": consistency_data}
    }