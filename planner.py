import streamlit as st
from datetime import datetime, time, timedelta
import os
import json
from dateutil import parser
from fpdf import FPDF

DEFAULTS_FILE = "saved_default_calendars.json"

st.set_page_config(page_title="AI Planner", layout="wide")

st.markdown("""
<style>
.stApp {
    background: #000000;
    color: #ffffff;
}
html, body, [class*="css"] {
    color: #ffffff;
}
h1, h2, h3, h4, h5, h6, p, label, div, span {
    color: #ffffff !important;
}
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="base-input"] > div,
textarea,
input {
    background-color: #0d0d0d !important;
    color: #ffffff !important;
    border: 1px solid #2b2b2b !important;
    border-radius: 12px !important;
}
.stButton > button, .stDownloadButton > button {
    background: #111111 !important;
    color: #ffffff !important;
    border: 1px solid #333333 !important;
    border-radius: 12px !important;
    font-weight: 600 !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: #1a1a1a !important;
    color: #ffffff !important;
    border: 1px solid #666666 !important;
}
.block-container {
    max-width: 1250px;
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}
.schedule-card {
    border: 1px solid #222222;
    border-radius: 16px;
    padding: 16px 18px;
    background: #050505;
    margin-bottom: 12px;
}
.olive-text {
    color: #808000 !important;
    font-weight: 600 !important;
}
.calendar-text {
    color: #87ceeb !important;
    font-weight: 600 !important;
}
.default-card {
    border: 1px solid #202020;
    border-radius: 14px;
    padding: 12px 14px;
    background: #070707;
    margin-bottom: 10px;
}
.small-muted {
    color: #bbbbbb !important;
    font-size: 0.9rem;
}
hr {
    border-color: #1d1d1d !important;
}
</style>
""", unsafe_allow_html=True)


def load_default_calendars():
    if os.path.exists(DEFAULTS_FILE):
        try:
            with open(DEFAULTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_default_calendars(defaults):
    with open(DEFAULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(defaults, f, indent=2)


def save_current_as_default(name, schedule):
    defaults = load_default_calendars()
    defaults = [d for d in defaults if d["name"] != name]
    defaults.append({
        "name": name,
        "schedule": schedule,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_default_calendars(defaults)


def get_calendar_service():
    return None


def get_todays_events():
    service = get_calendar_service()

    if service is None:
        st.warning("Google Calendar sync is available only in the local version right now.")
        return []

    try:
        now = datetime.now().astimezone()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)

        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return events_result.get("items", [])
    except Exception as e:
        return f"Error: {e}"


def parse_iso(raw):
    try:
        return parser.isoparse(raw).astimezone()
    except Exception:
        return None


def fmt_time(dt_obj):
    return dt_obj.strftime("%I:%M %p")


def overlaps(slot_start, slot_end, event_start, event_end):
    return max(slot_start, event_start) < min(slot_end, event_end)


def build_pdf(lines):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", size=12)

    for line in lines:
        safe_line = line.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 8, safe_line)

    return pdf.output(dest="S").encode("latin-1")


def get_sort_datetime(item_time):
    try:
        if item_time == "All Day":
            return datetime.strptime("12:00 AM", "%I:%M %p")
        if " - " in item_time:
            first = item_time.split(" - ")[0]
        else:
            first = item_time
        return datetime.strptime(first, "%I:%M %p")
    except Exception:
        return datetime.strptime("11:59 PM", "%I:%M %p")


def parse_all_day_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


today = datetime.now().strftime("%A, %d %B %Y")
today_date = datetime.now().date()

if "generated_schedule" not in st.session_state:
    st.session_state.generated_schedule = []
if "final_schedule" not in st.session_state:
    st.session_state.final_schedule = []
if "edit_mode" not in st.session_state:
    st.session_state.edit_mode = False

st.title("AI Planner")
st.caption(today)

main_left, main_right = st.columns([1, 1])

with main_left:
    st.subheader("Tasks")

    task_count = st.number_input(
        "Number of tasks",
        min_value=3,
        max_value=12,
        value=3,
        step=1
    )

    tasks = []
    for i in range(task_count):
        task = st.text_input(f"Task {i+1}", key=f"task_{i}")
        if task.strip():
            tasks.append(task.strip())

    st.subheader("Meals")
    lunch_time = st.time_input("Lunch", value=time(12, 30))
    dinner_time = st.time_input("Dinner", value=time(18, 30))

    st.subheader("Calendar")

    c1, c2 = st.columns([1, 1])
    with c1:
        refresh_clicked = st.button("Refresh Calendar")
    with c2:
        st.markdown("<div class='small-muted'>Refresh after adding something to Google Calendar</div>", unsafe_allow_html=True)

    if refresh_clicked:
        st.rerun()

    events = get_todays_events()
    busy_ranges = []
    calendar_schedule_items = []

    if isinstance(events, str):
        st.error(events)
    elif not events:
        st.write("No calendar events today.")
    else:
        for event in events:
            start_obj = event.get("start", {})
            end_obj = event.get("end", {})
            title = event.get("summary", "No title")

            if "dateTime" in start_obj and "dateTime" in end_obj:
                start_dt = parse_iso(start_obj["dateTime"])
                end_dt = parse_iso(end_obj["dateTime"])

                if start_dt and end_dt:
                    busy_ranges.append((start_dt, end_dt))
                    st.write(f"{fmt_time(start_dt)} - {fmt_time(end_dt)}  |  {title}")

                    calendar_schedule_items.append({
                        "time": f"{fmt_time(start_dt)} - {fmt_time(end_dt)}",
                        "task": title,
                        "type": "calendar"
                    })

            elif "date" in start_obj and "date" in end_obj:
                start_date = parse_all_day_date(start_obj["date"])
                end_date = parse_all_day_date(end_obj["date"])

                if start_date and end_date:
                    end_date_inclusive = end_date - timedelta(days=1)
                    if start_date <= today_date <= end_date_inclusive:
                        st.write(f"All Day  |  {title}")
                        calendar_schedule_items.append({
                            "time": "All Day",
                            "task": title,
                            "type": "calendar_all_day"
                        })

    st.subheader("Default calendars")
    saved_defaults = load_default_calendars()

    if not saved_defaults:
        st.write("No saved default calendars yet.")
    else:
        for idx, default in enumerate(saved_defaults):
            st.markdown(
                f"<div class='default-card'><b>{default['name']}</b><br><span class='small-muted'>Saved at: {default['saved_at']}</span></div>",
                unsafe_allow_html=True
            )
            col_a, col_b = st.columns([1, 1])
            with col_a:
                if st.button(f"Load {default['name']}", key=f"load_default_{idx}"):
                    st.session_state.final_schedule = default["schedule"]
                    st.session_state.generated_schedule = default["schedule"]
                    st.session_state.edit_mode = False
                    st.rerun()
            with col_b:
                if st.button(f"Delete {default['name']}", key=f"delete_default_{idx}"):
                    updated = [d for d in saved_defaults if d["name"] != default["name"]]
                    save_default_calendars(updated)
                    st.rerun()

    if st.button("Create My Schedule"):
        slot_defs = [
            ("7:00 AM - 8:30 AM", datetime.combine(today_date, time(7, 0)).astimezone(), datetime.combine(today_date, time(8, 30)).astimezone()),
            ("8:45 AM - 10:15 AM", datetime.combine(today_date, time(8, 45)).astimezone(), datetime.combine(today_date, time(10, 15)).astimezone()),
            ("10:30 AM - 12:00 PM", datetime.combine(today_date, time(10, 30)).astimezone(), datetime.combine(today_date, time(12, 0)).astimezone()),
            ("2:00 PM - 4:00 PM", datetime.combine(today_date, time(14, 0)).astimezone(), datetime.combine(today_date, time(16, 0)).astimezone()),
            ("4:15 PM - 5:45 PM", datetime.combine(today_date, time(16, 15)).astimezone(), datetime.combine(today_date, time(17, 45)).astimezone()),
            ("7:15 PM - 8:30 PM", datetime.combine(today_date, time(19, 15)).astimezone(), datetime.combine(today_date, time(20, 30)).astimezone()),
        ]

        lunch_dt = datetime.combine(today_date, lunch_time).astimezone()
        dinner_dt = datetime.combine(today_date, dinner_time).astimezone()

        available_slots = []
        for label, start_dt, end_dt in slot_defs:
            blocked = False
            for event_start, event_end in busy_ranges:
                if overlaps(start_dt, end_dt, event_start, event_end):
                    blocked = True
                    break
            if not blocked:
                available_slots.append((label, start_dt, end_dt))

        generated = []

        for cal_item in calendar_schedule_items:
            generated.append(cal_item)

        task_index = 0
        for label, start_dt, end_dt in available_slots:
            if task_index < len(tasks):
                generated.append({
                    "time": label,
                    "task": tasks[task_index],
                    "type": "task"
                })
                task_index += 1

        generated.append({
            "time": lunch_dt.strftime("%I:%M %p"),
            "task": "Lunch",
            "type": "meal"
        })
        generated.append({
            "time": dinner_dt.strftime("%I:%M %p"),
            "task": "Dinner",
            "type": "meal"
        })

        generated = sorted(generated, key=lambda x: get_sort_datetime(x["time"]))

        st.session_state.generated_schedule = generated
        st.session_state.final_schedule = generated.copy()
        st.session_state.edit_mode = False

with main_right:
    st.subheader("Final schedule")

    final_schedule = st.session_state.final_schedule

    if not final_schedule:
        st.write("No schedule yet.")
    else:
        pdf_lines = ["AI Planner", today, "", "Final Schedule:", ""]

        if not st.session_state.edit_mode:
            for item in final_schedule:
                if item["type"] == "meal":
                    st.markdown(
                        f"<div class='schedule-card'><span class='olive-text'>{item['time']} → {item['task']}</span></div>",
                        unsafe_allow_html=True
                    )
                elif item["type"] in ["calendar", "calendar_all_day"]:
                    st.markdown(
                        f"<div class='schedule-card'><span class='calendar-text'>{item['time']} → {item['task']}</span></div>",
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"<div class='schedule-card'>{item['time']} → {item['task']}</div>",
                        unsafe_allow_html=True
                    )
                pdf_lines.append(f"{item['time']} -> {item['task']}")

            pdf_bytes = build_pdf(pdf_lines)

            button_col1, button_col2 = st.columns(2)

            with button_col1:
                st.download_button(
                    label="Download PDF",
                    data=pdf_bytes,
                    file_name="today_plan.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            with button_col2:
                if st.button("Edit Schedule", use_container_width=True):
                    st.session_state.edit_mode = True
                    st.rerun()

            save_as_default = st.checkbox("Save this schedule as default")

            if save_as_default:
                default_name = st.text_input(
                    "Default calendar name",
                    placeholder="Example: JEE Revision Day"
                )

                if st.button("Save Default", use_container_width=True):
                    if default_name.strip():
                        save_current_as_default(default_name.strip(), final_schedule)
                        st.success("Default calendar saved.")
                    else:
                        st.warning("Please enter a name for the default calendar.")

        else:
            edited = []

            for i, item in enumerate(final_schedule):
                c1, c2 = st.columns([1, 2])
                with c1:
                    new_time = st.text_input("Time", value=item["time"], key=f"time_{i}")
                with c2:
                    new_task = st.text_input("Task", value=item["task"], key=f"task_edit_{i}")

                edited.append({
                    "time": new_time,
                    "task": new_task,
                    "type": item["type"]
                })

            if st.button("Save Changes"):
                edited_sorted = sorted(edited, key=lambda x: get_sort_datetime(x["time"]))
                st.session_state.final_schedule = edited_sorted
                st.session_state.edit_mode = False
                st.rerun()
