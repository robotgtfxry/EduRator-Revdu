# app.py
import os
import sqlite3
import secrets
import re
from datetime import datetime, timedelta
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for, g
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask import Markup

app = Flask(__name__)
app.secret_key = os.urandom(24)

DATABASE = "database.db"

# Role constants
ROLE_USER = 0
ROLE_TEACHER = 1
ROLE_REGIONAL_TEACHER = 2
ROLE_ADMIN = 3


app.config['UPLOAD_FOLDER'] = 'static/profile_pictures'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB
app.config.update(
    SESSION_COOKIE_SECURE=False,  # Jeśli NIE używasz HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)


# Polish voivodeships with coordinates
VOIVODESHIPS = {
    "dolnośląskie": {"coords": (51.1, 16.9)},
    "kujawsko-pomorskie": {"coords": (53.0, 18.5)},
    "lubelskie": {"coords": (51.2, 22.6)},
    "lubuskie": {"coords": (52.0, 15.5)},
    "łódzkie": {"coords": (51.8, 19.5)},
    "małopolskie": {"coords": (50.0, 19.9)},
    "mazowieckie": {"coords": (52.2, 21.0)},
    "opolskie": {"coords": (50.7, 17.9)},
    "podkarpackie": {"coords": (50.0, 22.0)},
    "podlaskie": {"coords": (53.1, 23.1)},
    "pomorskie": {"coords": (54.4, 18.5)},
    "śląskie": {"coords": (50.3, 19.0)},
    "świętokrzyskie": {"coords": (50.9, 20.6)},
    "warmińsko-mazurskie": {"coords": (53.8, 20.5)},
    "wielkopolskie": {"coords": (52.4, 16.9)},
    "zachodniopomorskie": {"coords": (53.4, 15.0)}
}

# List of school subjects
SCHOOL_SUBJECTS = [
    "Język polski", "Matematyka", "Język angielski", "Język niemiecki",
    "Język francuski", "Język hiszpański", "Język rosyjski", "Historia",
    "Wiedza o społeczeństwie", "Geografia", "Biologia", "Chemia",
    "Fizyka", "Informatyka", "Technika", "Plastyka", "Muzyka",
    "Wychowanie fizyczne", "Edukacja dla bezpieczeństwa",
    "Wiedza o kulturze", "Filozofia", "Etyka", "Religia",
    "Wychowanie do życia w rodzinie", "Ekonomia w praktyce",
    "Podstawy przedsiębiorczości", "Historia i społeczeństwo",
    "Przyroda", "Edukacja regionalna", "Zajęcia artystyczne",
    "Zajęcia techniczne", "Wychowanie komunikacyjne",
    "Edukacja zdrowotna", "Doradztwo zawodowe", "Psycholog"
]

# Teaching modes
TEACHING_MODES = ['online', 'in_person']

SUBJECT_COLORS = {
    "Język polski": "#FF5733",
    "Matematyka": "#33FF57",
    "Język angielski": "#3357FF",
    "Język niemiecki": "#F333FF",
    "Język francuski": "#FF33A1",
    "Język hiszpański": "#33FFF6",
    "Język rosyjski": "#F6FF33",
    "Historia": "#8C33FF",
    "Wiedza o społeczeństwie": "#00f2ff",
    "Geografia": "#33FF8C",
    "Biologia": "#338CFF",
    "Chemia": "#FF338C",
    "Fizyka": "#8CFF33",
    "Informatyka": "#FF3333",
    "Technika": "#33FF33",
    "Plastyka": "#3333FF",
    "Muzyka": "#FFFF33",
    "Wychowanie fizyczne": "#33FFFF",
    "Edukacja dla bezpieczeństwa": "#FF33FF",
    "Wiedza o kulturze": "#FF5733",
    "Filozofia": "#57FF33",
    "Etyka": "#5733FF",
    "Religia": "#FF3357",
    "Wychowanie do życia w rodzinie": "#33FF57",
    "Ekonomia w praktyce": "#3357FF",
    "Podstawy przedsiębiorczości": "#F357FF",
    "Historia i społeczeństwo": "#FF57A1",
    "Przyroda": "#57FFF6",
    "Edukacja regionalna": "#F6FF57",
    "Zajęcia artystyczne": "#8C57FF",
    "Zajęcia techniczne": "#FF8C57",
    "Wychowanie komunikacyjne": "#57FF8C",
    "Edukacja zdrowotna": "#578CFF",
    "Doradztwo zawodowe": "#FF578C",
    "Psycholog": "#8CFF57"
}

DEFAULT_PIN_COLOR = "#4285F4"


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def normalize_time(time_str):
    """Convert time string to HH:MM format"""
    try:
        t = datetime.strptime(time_str, '%H:%M')
        return t.strftime('%H:%M')
    except:
        return time_str

@app.template_filter('format_datetime')
def format_datetime(value, format='%d.%m.%Y %H:%M'):
    """Format a datetime object to a string."""
    if value is None:
        return ""
    try:
        return value.strftime(format)
    except AttributeError:
        return value

def normalize_time_slot(time_slot):
    """Normalize a time slot string to HH:MM - HH:MM"""
    parts = time_slot.split(' - ')
    if len(parts) != 2:
        return time_slot
    start = normalize_time(parts[0].strip())
    end = normalize_time(parts[1].strip())
    return f"{start} - {end}"

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_dict_list(rows):
    return [dict(row) for row in rows] if rows else []


def get_day_name(day_of_week):
    days = ['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek', 'Sobota', 'Niedziela']
    return days[day_of_week] if 0 <= day_of_week < 7 else 'Nieznany'


def format_time_slot(start_time, end_time):
    return f"{start_time} - {end_time}"


@app.context_processor
def utility_processor():
    return dict(
        get_day_name=get_day_name,
        get_role_name=get_role_name,
        datetime=datetime,
        timedelta=timedelta,
        format_time_slot=format_time_slot
    )


@app.route("/api/mark_notification_read/<int:notification_id>", methods=["POST"])
def mark_notification_read(notification_id):
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    db = get_db()

    try:
        db.execute("""
            UPDATE notifications 
            SET is_read = 1 
            WHERE id = ? AND user_id = ?
        """, (notification_id, user_id))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def index():
    db = get_db()

    # Pobierz pinezki z informacją o przedmiotach nauczyciela
    pins_rows = db.execute("""
        SELECT p.*, u.username as creator, u.email as creator_email, u.subjects
        FROM pins p
        JOIN users u ON p.created_by = u.id
    """).fetchall()

    # Przygotuj dane pinezek z kolorami
    pins = []
    for row in pins_rows:
        pin = dict(row)
        # Przypisz kolor na podstawie pierwszego przedmiotu nauczyciela
        if pin['subjects']:
            subjects = pin['subjects'].split(',')
            if subjects:
                first_subject = subjects[0].strip()
                pin['color'] = SUBJECT_COLORS.get(first_subject, DEFAULT_PIN_COLOR)
                pin['first_subject'] = first_subject
        else:
            pin['color'] = DEFAULT_PIN_COLOR
            pin['first_subject'] = None
        pins.append(pin)

    # Get online teachers (max 3)
    online_teachers = db.execute("""
        SELECT id, first_name, last_name, subjects, availability_hours, teaching_modes, is_online, last_online
        FROM users 
        WHERE role IN (?, ?) AND is_online = 1
        ORDER BY last_online DESC
        LIMIT 3
    """, (ROLE_TEACHER, ROLE_REGIONAL_TEACHER)).fetchall()

    online_teachers = rows_to_dict_list(online_teachers)

    teacher_has_pin = False
    role = None
    managed_teachers = []
    unread_notifications = 0
    user_profile_picture = None  # Dodane

    if "user_id" in session:
        user_id = session["user_id"]
        role = session.get("user_role", "user")

        # Pobierz zdjęcie profilowe użytkownika
        user_row = db.execute("SELECT profile_picture FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_row and user_row['profile_picture']:
            user_profile_picture = user_row['profile_picture']

        if role in ["teacher", "regional_teacher"]:
            existing_pin = db.execute("SELECT * FROM pins WHERE created_by = ?", (user_id,)).fetchone()
            teacher_has_pin = existing_pin is not None

        # For regional teachers, get their managed teachers
        if role == "regional_teacher":
            managed_teachers_rows = db.execute("""
                SELECT id, username, email, voivodeship 
                FROM users 
                WHERE regional_teacher_id = ? AND role = ?
                ORDER BY username
            """, (user_id, ROLE_TEACHER)).fetchall()
            managed_teachers = rows_to_dict_list(managed_teachers_rows)

        # Get unread notification count
        unread_notifications = db.execute("""
            SELECT COUNT(*) as count
            FROM notifications
            WHERE user_id = ? AND is_read = 0
        """, (user_id,)).fetchone()["count"]

    return render_template(
        "index.html",
        pins=pins,
        online_teachers=online_teachers,
        teacher_has_pin=teacher_has_pin,
        role=role,
        logged_in="user_id" in session,
        managed_teachers=managed_teachers,
        unread_notifications=unread_notifications,
        school_subjects=SCHOOL_SUBJECTS,
        user_profile_picture=user_profile_picture  # Dodane
    )


@app.route("/api/booking_stats", methods=["GET"])
def get_booking_stats():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    user_role = session.get("user_role", "user")
    db = get_db()

    stats = {
        "total_lessons": 0,
        "scheduled": 0,
        "completed": 0,
        "cancelled": 0,
        "total_hours": 0.0,
        "completed_lessons": [],  # Nowe dane
        "cancelled_lessons": []  # Nowe dane
    }

    try:
        # Determine which column to use based on role
        if user_role in ["teacher", "regional_teacher"]:
            column = "teacher_id"
        else:
            column = "student_id"

        # Pobierz wszystkie rezerwacje
        bookings = db.execute(f"""
            SELECT b.id, b.booking_date, b.day_of_week, b.time_slot, b.status, b.notes,
                   u_student.username AS student_name, u_student.email AS student_email,
                   u_teacher.username AS teacher_name, u_teacher.email AS teacher_email
            FROM bookings b
            LEFT JOIN users u_student ON b.student_id = u_student.id
            LEFT JOIN users u_teacher ON b.teacher_id = u_teacher.id
            WHERE {column} = ?
        """, (user_id,)).fetchall()

        # Zlicz statystyki
        stats["total_lessons"] = len(bookings)

        total_hours = 0.0

        for booking in bookings:
            status = booking["status"].lower()

            # Dodaj do odpowiedniej listy
            if status in ["completed", "przeprowadzona"]:
                stats["completed_lessons"].append(dict(booking))
            elif status in ["cancelled", "odwolana"]:
                stats["cancelled_lessons"].append(dict(booking))

            # Zliczanie statusów
            if status in ["scheduled", "zaplanowana"]:
                stats["scheduled"] += 1
            elif status in ["completed", "przeprowadzona"]:
                stats["completed"] += 1

                # Oblicz czas trwania lekcji
                time_slot = booking["time_slot"]
                parts = time_slot.split(' - ')
                if len(parts) == 2:
                    try:
                        start_str = parts[0].strip()
                        end_str = parts[1].strip()

                        # Parsuj czas
                        start_time = datetime.strptime(start_str, '%H:%M')
                        end_time = datetime.strptime(end_str, '%H:%M')

                        # Oblicz różnicę w godzinach
                        duration = end_time - start_time
                        duration_hours = duration.total_seconds() / 3600
                        total_hours += duration_hours
                    except ValueError as e:
                        print(f"Błąd parsowania czasu: {time_slot}, {e}")
            elif status in ["cancelled", "odwolana"]:
                stats["cancelled"] += 1

        # Zaokrąglij do 2 miejsc po przecinku
        stats["total_hours"] = round(total_hours, 2)

    except Exception as e:
        print(f"Błąd podczas pobierania statystyk rezerwacji: {e}")
        return jsonify({"error": "Nie udało się pobrać statystyk"}), 500

    return jsonify(stats)


@app.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    regional_teachers = db.execute("""
        SELECT id, username, email, voivodeship 
        FROM users 
        WHERE role = ? 
        ORDER BY voivodeship, username
    """, (ROLE_REGIONAL_TEACHER,)).fetchall()

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        role_str = request.form.get("role", "user")
        voivodeship = request.form.get("voivodeship", "").strip()
        regional_teacher_id = request.form.get("regional_teacher_id", "").strip()
        teaching_modes = request.form.getlist("teaching_modes")
        parental_email = request.form.get("parental_email", "").strip()

        # New profile fields
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        school = request.form.get("school", "").strip()
        subjects = request.form.getlist("subjects")
        experience_years = request.form.get("experience_years", "0").strip()
        bio = request.form.get("bio", "").strip()
        tmethod = request.form.get("tmethod", "").strip()
        availability_hours = request.form.get("availability_hours", "8").strip()

        role_mapping = {
            "user": ROLE_USER,
            "teacher": ROLE_TEACHER,
            "regional_teacher": ROLE_REGIONAL_TEACHER,
            "admin": ROLE_ADMIN
        }
        role = role_mapping.get(role_str.lower(), ROLE_USER)

        # Validation
        if not username or not email or not password:
            flash("Musisz podać nazwę użytkownika, email i hasło", "error")
            return redirect(url_for("register"))

        if not is_valid_email(email):
            flash("Podaj prawidłowy adres email", "error")
            return redirect(url_for("register"))

        existing_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if existing_user:
            flash("Użytkownik o tej nazwie już istnieje", "error")
            return redirect(url_for("register"))

        existing_email = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing_email:
            flash("Użytkownik z tym adresem email już istnieje", "error")
            return redirect(url_for("register"))

        # Parental email validation
        if role == ROLE_USER and parental_email and not is_valid_email(parental_email):
            flash("Podaj prawidłowy adres email opiekuna", "error")
            return redirect(url_for("register"))
        elif role != ROLE_USER:
            parental_email = None

        if role == ROLE_USER:
            if not voivodeship or voivodeship not in VOIVODESHIPS:
                flash("Musisz wybrać prawidłowe województwo", "error")
                return redirect(url_for("register"))
        elif role == ROLE_TEACHER:
            if not regional_teacher_id:
                flash("Musisz wybrać nauczyciela regionalnego", "error")
                return redirect(url_for("register"))
            regional_teacher = db.execute("SELECT * FROM users WHERE id = ? AND role = ?",
                                          (regional_teacher_id, ROLE_REGIONAL_TEACHER)).fetchone()
            if not regional_teacher:
                flash("Wybrany nauczyciel regionalny nie istnieje", "error")
                return redirect(url_for("register"))
        elif role == ROLE_REGIONAL_TEACHER:
            if not voivodeship or voivodeship not in VOIVODESHIPS:
                flash("Nauczyciel regionalny musi wybrać województwo", "error")
                return redirect(url_for("register"))

        hash_pw = generate_password_hash(password)
        rt_id = regional_teacher_id if role == ROLE_TEACHER and regional_teacher_id else None

        try:
            experience = int(experience_years) if experience_years else 0
            availability = int(availability_hours) if availability_hours else 8
        except ValueError:
            experience = 0
            availability = 8

        # Convert list of subjects to comma-separated string
        subjects_str = ", ".join(subjects) if subjects else ""
        teaching_modes_str = ", ".join(teaching_modes) if teaching_modes else "online"

        db.execute("""
            INSERT INTO users (
                username, email, hash, role, voivodeship, regional_teacher_id,
                first_name, last_name, phone, school, subjects, experience_years, bio,
                teaching_modes, availability_hours, parental_email
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            username, email, hash_pw, role, voivodeship, rt_id,
            first_name, last_name, phone, school, subjects_str, experience, bio,
            teaching_modes_str, availability, parental_email
        ))
        db.commit()
        flash("Rejestracja zakończona sukcesem, możesz się teraz zalogować", "success")
        return redirect(url_for("login"))

    return render_template("register.html", voivodeships=VOIVODESHIPS.keys(),
                           regional_teachers=regional_teachers, school_subjects=SCHOOL_SUBJECTS,
                           teaching_modes=TEACHING_MODES)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user is None or not check_password_hash(user["hash"], password):
            flash("Nieprawidłowa nazwa użytkownika lub hasło", "error")
            return redirect(url_for("login"))

        # Update online status
        db.execute("UPDATE users SET is_online = 1, last_online = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))
        db.commit()

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["user_email"] = user["email"] if user["email"] else None
        session["user_role"] = get_role_name(user["role"])
        session["user_voivodeship"] = user["voivodeship"] if user["voivodeship"] else None

        if user["voivodeship"] and user["voivodeship"] in VOIVODESHIPS:
            session["user_region_coords"] = VOIVODESHIPS[user["voivodeship"]]["coords"]

        if user["role"] in [ROLE_TEACHER, ROLE_REGIONAL_TEACHER]:
            pin = db.execute("SELECT id FROM pins WHERE created_by = ?", (user["id"],)).fetchone()
            if pin:
                session["assigned_pin_id"] = pin["id"]

        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    if "user_id" in session:
        db = get_db()
        db.execute("UPDATE users SET is_online = 0 WHERE id = ?", (session['user_id'],))
        db.commit()

    session.clear()
    return redirect(url_for("login"))


@app.route("/lesson/<int:booking_id>")
def lesson(booking_id):
    if "user_id" not in session:
        flash("Musisz być zalogowany", "error")
        return redirect(url_for("login"))

    db = get_db()
    booking = db.execute("""
        SELECT b.*, 
               u_student.username as student_name, u_student.email as student_email,
               u_teacher.username as teacher_name, u_teacher.email as teacher_email,
               p.title as pin_title, p.address as pin_address
        FROM bookings b
        JOIN users u_student ON b.student_id = u_student.id
        JOIN users u_teacher ON b.teacher_id = u_teacher.id
        LEFT JOIN pins p ON u_teacher.id = p.created_by
        WHERE b.id = ?
    """, (booking_id,)).fetchone()

    if not booking:
        flash("Rezerwacja nie istnieje", "error")
        return redirect(url_for("index"))

    # Check if user has access to this booking
    user_id = session["user_id"]
    if booking["student_id"] != user_id and booking["teacher_id"] != user_id:
        flash("Nie masz dostępu do tej lekcji", "error")
        return redirect(url_for("index"))

    # Parse booking date and time
    booking_date = datetime.strptime(booking["booking_date"], "%Y-%m-%d")
    time_slot_parts = booking["time_slot"].split(" - ")
    start_time = datetime.strptime(time_slot_parts[0], "%H:%M")

    # Combine date and time
    lesson_start = datetime.combine(booking_date, start_time.time())

    # Calculate time remaining
    now = datetime.now()
    time_remaining = lesson_start - now if lesson_start > now else timedelta(0)

    # Format time remaining
    hours, remainder = divmod(time_remaining.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_remaining_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # Determine lesson mode and location
    lesson_mode = booking["lesson_mode"]
    location = "Online" if lesson_mode == "online" else booking["pin_address"]

    return render_template("lesson.html",
                           booking=booking,
                           lesson_start=lesson_start,
                           time_remaining=time_remaining_str,
                           location=location,
                           is_teacher=(booking["teacher_id"] == user_id))


@app.route("/lesson_crm/<int:booking_id>")
def lesson_crm(booking_id):
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    db = get_db()
    booking = db.execute("""
        SELECT b.*, 
               u_student.username as student_name, u_student.email as student_email,
               u_teacher.username as teacher_name, u_teacher.email as teacher_email,
               p.title as pin_title, p.address as pin_address
        FROM bookings b
        JOIN users u_student ON b.student_id = u_student.id
        JOIN users u_teacher ON b.teacher_id = u_teacher.id
        LEFT JOIN pins p ON u_teacher.id = p.created_by
        WHERE b.id = ? AND b.teacher_id = ?
    """, (booking_id, session["user_id"])).fetchone()

    if not booking:
        flash("Rezerwacja nie istnieje", "error")
        return redirect(url_for("index"))

    # Parse booking date and time
    booking_date = datetime.strptime(booking["booking_date"], "%Y-%m-%d")
    time_slot_parts = booking["time_slot"].split(" - ")
    start_time = datetime.strptime(time_slot_parts[0], "%H:%M")
    end_time = datetime.strptime(time_slot_parts[1], "%H:%M")

    # Combine date and time
    lesson_start = datetime.combine(booking_date, start_time.time())
    lesson_end = datetime.combine(booking_date, end_time.time())

    # Calculate time remaining
    now = datetime.now()
    time_remaining = lesson_start - now if lesson_start > now else timedelta(0)

    # Format time remaining
    if time_remaining.total_seconds() > 0:
        total_seconds = int(time_remaining.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_remaining_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        time_remaining_str = "00:00:00"

    # Determine lesson mode and location
    lesson_mode = booking["lesson_mode"]
    location = "Online" if lesson_mode == "online" else booking["pin_address"]

    return render_template("lesson_crm.html",
                           booking=booking,
                           lesson_start=lesson_start,
                           lesson_end=lesson_end,
                           time_remaining=time_remaining_str,
                           location=location)


@app.route("/api/update_lesson_status", methods=["POST"])
def update_lesson_status():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    booking_id = data.get("booking_id")
    status = data.get("status")
    reason = data.get("reason", "")

    if not booking_id or not status:
        return jsonify({"error": "Missing required fields"}), 400

    db = get_db()

    booking = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    user_id = session["user_id"]
    if booking["student_id"] != user_id and booking["teacher_id"] != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    # Zaktualizuj status w formacie PL
    valid_statuses = {"zaplanowana", "przeprowadzona", "odwolana"}
    if status not in valid_statuses:
        return jsonify({"error": "Invalid status value"}), 400

    try:
        db.execute("""
            UPDATE bookings 
            SET status = ?, cancellation_reason = ?
            WHERE id = ?
        """, (status, reason if status == "odwolana" else "", booking_id))

        # Tworzenie powiadomienia
        if booking["teacher_id"] == user_id:
            message = f"Status lekcji {booking_id} zmieniony na '{status}' przez nauczyciela"
            target = booking["student_id"]
        else:
            message = f"Status lekcji {booking_id} zmieniony na '{status}' przez ucznia"
            target = booking["teacher_id"]

        db.execute("""
            INSERT INTO notifications (user_id, sender_id, message)
            VALUES (?, ?, ?)
        """, (target, user_id, message))

        db.commit()
        return jsonify({"success": True, "message": "Status lekcji zaktualizowany"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/update_lesson_notes", methods=["POST"])
def update_lesson_notes():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    booking_id = data.get("booking_id")
    notes = data.get("notes", "")

    if not booking_id:
        return jsonify({"error": "Missing booking ID"}), 400

    db = get_db()

    # Check if user has permission to update this booking
    booking = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    user_id = session["user_id"]
    if booking["student_id"] != user_id and booking["teacher_id"] != user_id:
        return jsonify({"error": "Unauthorized"}), 403

    # Update booking notes
    try:
        db.execute("""
            UPDATE bookings 
            SET notes = ?
            WHERE id = ?
        """, (notes, booking_id))
        db.commit()
        return jsonify({"success": True, "message": "Notatki zaktualizowane"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/users", methods=["GET"])
def users():
    """Admin endpoint to view all users and their emails"""
    if "user_id" not in session or session.get("user_role") != "admin":
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    db = get_db()
    users_rows = db.execute("""
        SELECT u.id, u.username, u.email, u.role, u.voivodeship, u.parental_email,
               rt.username as regional_teacher_name,
               rt.email as regional_teacher_email
        FROM users u
        LEFT JOIN users rt ON u.regional_teacher_id = rt.id
        ORDER BY u.role DESC, u.username
    """).fetchall()

    users_list = rows_to_dict_list(users_rows)

    # Add role names for display
    for user in users_list:
        user['role_name'] = get_role_name(user['role'])

    return render_template("users.html", users=users_list)


@app.route("/profile", methods=["GET", "POST"])
def profile():
    """User profile page to view and edit personal information"""
    if "user_id" not in session:
        flash("Musisz być zalogowany", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    db = get_db()

    if request.method == "POST":
        new_email = request.form.get("email", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        phone = request.form.get("phone", "").strip()
        school = request.form.get("school", "").strip()
        subjects = request.form.getlist("subjects")
        experience_years = request.form.get("experience_years", "0").strip()
        bio = request.form.get("bio", "").strip()
        tmethod = request.form.get("tmethod", "").strip()
        parental_email = request.form.get("parental_email", "").strip()

        if not new_email:
            flash("Email nie może być pusty", "error")
            return redirect(url_for("profile"))

        if not is_valid_email(new_email):
            flash("Podaj prawidłowy adres email", "error")
            return redirect(url_for("profile"))

        existing_email = db.execute("SELECT * FROM users WHERE email = ? AND id != ?", (new_email, user_id)).fetchone()
        if existing_email:
            flash("Ten adres email jest już używany przez innego użytkownika", "error")
            return redirect(url_for("profile"))

        # Handle parental email based on role
        user_row = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if user_row and user_row["role"] == ROLE_USER:  # Student
            if parental_email and not is_valid_email(parental_email):
                flash("Podaj prawidłowy adres email opiekuna", "error")
                return redirect(url_for("profile"))
        else:
            # Set to null for non-student users
            parental_email = None

        try:
            experience = int(experience_years) if experience_years else 0
        except ValueError:
            experience = 0

        # Convert list of subjects to comma-separated string
        subjects_str = ", ".join(subjects) if subjects else ""

        # Handle profile picture upload
        profile_picture = None
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file.filename != '' and allowed_file(file.filename):
                # Delete old picture if exists
                old_pic = db.execute("SELECT profile_picture FROM users WHERE id = ?", (user_id,)).fetchone()
                if old_pic and old_pic['profile_picture']:
                    try:
                        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], old_pic['profile_picture']))
                    except OSError:
                        pass

                # Save new picture
                filename = secure_filename(
                    f"{user_id}_{secrets.token_hex(8)}.{file.filename.rsplit('.', 1)[1].lower()}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                profile_picture = filename

        # Update user data
        update_data = [
            new_email, first_name, last_name, phone, school,
            subjects_str, experience, bio, parental_email, tmethod, user_id
        ]

        if profile_picture:
            update_query = """
                UPDATE users SET 
                    email = ?, first_name = ?, last_name = ?, phone = ?,
                    school = ?, subjects = ?, experience_years = ?, bio = ?,
                    parental_email = ?, tmethod = ?, profile_picture = ?
                WHERE id = ?
            """
            update_data.insert(-1, profile_picture)  # Add before user_id
        else:
            update_query = """
                UPDATE users SET 
                    email = ?, first_name = ?, last_name = ?, phone = ?,
                    school = ?, subjects = ?, experience_years = ?, bio = ?,
                    parental_email = ?, tmethod = ?
                WHERE id = ?
            """

        db.execute(update_query, update_data)
        db.commit()

        session["user_email"] = new_email
        flash("Profil został zaktualizowany", "success")
        return redirect(url_for("profile"))

    # Get user data
    user_row = db.execute("""
        SELECT u.*, rt.username as regional_teacher_name, rt.email as regional_teacher_email
        FROM users u
        LEFT JOIN users rt ON u.regional_teacher_id = rt.id
        WHERE u.id = ?
    """, (user_id,)).fetchone()

    user = row_to_dict(user_row)
    user['role_name'] = get_role_name(user['role'])

    return render_template("profile.html", user=user, school_subjects=SCHOOL_SUBJECTS)

@app.route("/pin/<int:pin_id>")
def pin(pin_id):
    db = get_db()
    pin_row = db.execute("""
        SELECT p.*, u.username as creator, u.email as creator_email, u.role as creator_role
        FROM pins p
        JOIN users u ON p.created_by = u.id
        WHERE p.id = ?
    """, (pin_id,)).fetchone()

    if not pin_row:
        flash("Pinezka nie istnieje", "error")
        return redirect(url_for("index"))

    pin = row_to_dict(pin_row)

    # Check if creator is a teacher to show calendar
    show_calendar = pin['creator_role'] in [ROLE_TEACHER, ROLE_REGIONAL_TEACHER]

    # Get teacher's availability if they are a teacher
    availability = {}
    if show_calendar:
        availability_rows = db.execute("""
            SELECT day_of_week, start_time, end_time, is_available, teaching_mode
            FROM teacher_availability
            WHERE teacher_id = ?
        """, (pin['created_by'],)).fetchall()

        for row in availability_rows:
            day = row['day_of_week']
            if day not in availability:
                availability[day] = {}

            time_slot = f"{row['start_time']} - {row['end_time']}"
            availability[day][time_slot] = {
                'available': row['is_available'],
                'mode': row['teaching_mode']
            }

        return render_template("pin.html", pin=pin, show_calendar=show_calendar,
                               availability=availability, time_slots=generate_time_slots(), datetime=datetime)


@app.route("/crm/register", methods=["GET", "POST"])
def crm_register():
    """CRM endpoint for teachers to register new clients"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        # Extract form data
        username = request.form["username"]
        email = request.form["email"]
        first_name = request.form["first_name"]
        last_name = request.form["last_name"]
        phone = request.form.get("phone", "").strip()
        school = request.form.get("school", "").strip()
        subjects = request.form.getlist("subjects")
        voivodeship = request.form["voivodeship"]
        parental_email = request.form.get("parental_email", "").strip()

        # Validation
        if not all([username, email, first_name, last_name, voivodeship]):
            flash("Wypełnij wszystkie wymagane pola", "error")
            return redirect(url_for("crm_register"))

        if not is_valid_email(email):
            flash("Podaj prawidłowy adres email", "error")
            return redirect(url_for("crm_register"))

        db = get_db()

        # Check if username or email already exists
        existing_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if existing_user:
            flash("Użytkownik o tej nazwie już istnieje", "error")
            return redirect(url_for("crm_register"))

        existing_email = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing_email:
            flash("Użytkownik z tym adresem email już istnieje", "error")
            return redirect(url_for("crm_register"))

        # Parental email validation
        if parental_email and not is_valid_email(parental_email):
            flash("Podaj prawidłowy adres email opiekuna", "error")
            return redirect(url_for("crm_register"))

        # Convert list of subjects to comma-separated string
        subjects_str = ", ".join(subjects) if subjects else ""

        # Generate password setup token
        token = secrets.token_urlsafe(32)
        token_expiry = datetime.now() + timedelta(days=2)  # Token valid for 2 days

        # Generate temporary password
        temp_password = secrets.token_urlsafe(12)
        hash_pw = generate_password_hash(temp_password)

        # Create user
        try:
            db.execute("""
                INSERT INTO users (
                    username, email, hash, first_name, last_name, phone, school, 
                    subjects, voivodeship, parental_email, role, 
                    password_setup_token, token_expiry
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username, email, hash_pw, first_name, last_name, phone, school,
                subjects_str, voivodeship, parental_email, ROLE_USER,
                token, token_expiry
            ))
            db.commit()

            # Get the new user ID
            user_row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            user_id = user_row["id"]

            # Generate password setup link
            setup_link = url_for('setup_password', token=token, _external=True)

            flash(f"Klient został zarejestrowany! Wyślij mu ten link do ustawienia hasła: {setup_link}", "success")
            return redirect(url_for("crm"))
        except Exception as e:
            flash(f"Błąd podczas rejestracji klienta: {str(e)}", "error")
            return redirect(url_for("crm_register"))

    return render_template("crm_register.html",
                           voivodeships=VOIVODESHIPS.keys(),
                           school_subjects=SCHOOL_SUBJECTS)


@app.route("/setup_password/<token>", methods=["GET", "POST"])
def setup_password(token):
    """Page for users to set their password after CRM registration"""
    db = get_db()

    # Find user by token
    user = db.execute("""
        SELECT id, username, token_expiry 
        FROM users 
        WHERE password_setup_token = ? AND token_expiry > CURRENT_TIMESTAMP
    """, (token,)).fetchone()

    if not user:
        flash("Nieprawidłowy lub przeterminowany link aktywacyjny", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form["password"]
        confirmation = request.form["confirmation"]

        if password != confirmation:
            flash("Hasła nie są identyczne", "error")
            return redirect(url_for("setup_password", token=token))

        # Update user with password and clear token
        hash_pw = generate_password_hash(password)
        try:
            db.execute("""
                UPDATE users 
                SET hash = ?, password_setup_token = NULL, token_expiry = NULL
                WHERE id = ?
            """, (hash_pw, user["id"]))
            db.commit()

            flash("Hasło zostało ustawione! Możesz się teraz zalogować", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"Błąd podczas ustawiania hasła: {str(e)}", "error")
            return redirect(url_for("setup_password", token=token))

    return render_template("setup_password.html", token=token, username=user["username"])


@app.route("/add", methods=["GET", "POST"])
def add():
    if "user_id" not in session:
        flash("Musisz być zalogowany, aby dodać pinezkę", "error")
        return redirect(url_for("login"))

    role = session.get("user_role", "user")
    if role not in ["teacher", "regional_teacher", "admin"]:
        flash("Nie masz uprawnień do dodawania pinów", "error")
        return redirect(url_for("index"))

    user_id = session["user_id"]
    db = get_db()

    existing_pin = None
    if role in ["teacher", "regional_teacher"]:
        existing_pin = db.execute("SELECT * FROM pins WHERE created_by = ?", (user_id,)).fetchone()

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        region = request.form["region"]
        city = request.form["city"]
        address = request.form["address"]
        lat = request.form["lat"]
        lng = request.form["lng"]

        if not all([title, region, city, address, lat, lng]):
            flash("Wypełnij wszystkie wymagane pola", "error")
            return redirect(url_for("add"))

        # For regional teachers, validate that pin is in their region
        if role == "regional_teacher":
            user_voivodeship = session.get("user_voivodeship")
            if user_voivodeship and region.lower() != user_voivodeship.lower():
                flash("Nauczyciel regionalny może dodawać pinezki tylko w swoim województwo", "error")
                return redirect(url_for("add"))

        if role in ["teacher", "regional_teacher"] and existing_pin:
            db.execute("""
                UPDATE pins SET 
                    title = ?, description = ?, region = ?, city = ?, 
                    address = ?, lat = ?, lng = ?
                WHERE created_by = ?
            """, (title, description, region, city, address, lat, lng, user_id))
            flash("Pinezka została zaktualizowana", "success")
        else:
            db.execute("""
                INSERT INTO pins (title, description, region, city, address, lat, lng, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (title, description, region, city, address, lat, lng, user_id))
            flash("Pinezka została dodana", "success")

        db.commit()

        if role in ["teacher", "regional_teacher"]:
            pin = db.execute("SELECT id FROM pins WHERE created_by = ?", (user_id,)).fetchone()
            if pin:
                session["assigned_pin_id"] = pin["id"]

        return redirect(url_for("index"))

    pin_data = row_to_dict(existing_pin) if existing_pin else None
    return render_template("add.html", existing_pin=pin_data, is_teacher=(role in ["teacher", "regional_teacher"]),
                           voivodeships=VOIVODESHIPS.keys(), user_role=role,
                           user_voivodeship=session.get("user_voivodeship"))


@app.route("/edit_pin/<int:pin_id>", methods=["GET", "POST"])
def edit_pin(pin_id):
    if "user_id" not in session:
        flash("Musisz być zalogowany, aby edytować pinezkę", "error")
        return redirect(url_for("login"))

    db = get_db()
    pin_row = db.execute("SELECT * FROM pins WHERE id = ?", (pin_id,)).fetchone()
    if not pin_row:
        flash("Pinezka nie istnieje", "error")
        return redirect(url_for("index"))

    pin = row_to_dict(pin_row)
    user_id = session["user_id"]
    role = session.get("user_role", "user")

    can_edit = False
    if role == "admin":
        can_edit = True
    elif role in ["teacher", "regional_teacher"] and pin["created_by"] == user_id:
        can_edit = True
    elif role == "regional_teacher":
        user_voivodeship = session.get("user_voivodeship")
        if user_voivodeship and pin["region"].lower() == user_voivodeship.lower():
            can_edit = True

    if not can_edit:
        flash("Nie masz uprawnień do edycji tej pinezki", "error")
        return redirect(url_for("index"))

    show_calendar = False
    if pin["created_by"] == user_id and role in ["teacher", "regional_teacher"]:
        show_calendar = True

    availability = {}
    if show_calendar:
        availability_rows = db.execute("""
            SELECT day_of_week, start_time, end_time, teaching_mode
            FROM teacher_availability
            WHERE teacher_id = ?
        """, (user_id,)).fetchall()

        for row in availability_rows:
            day = row['day_of_week']
            time_slot = f"{row['start_time']} - {row['end_time']}"
            if day not in availability:
                availability[day] = {}
            availability[day][time_slot] = {
                'mode': row['teaching_mode']
            }

    if request.method == "POST":
        if 'update_pin' in request.form:
            title = request.form["title"]
            description = request.form["description"]
            region = request.form["region"]
            city = request.form["city"]
            address = request.form["address"]
            lat = request.form["lat"]
            lng = request.form["lng"]

            if not all([title, region, city, address, lat, lng]):
                flash("Wypełnij wszystkie wymagane pola", "error")
                return redirect(url_for("edit_pin", pin_id=pin_id))

            if role == "regional_teacher":
                user_voivodeship = session.get("user_voivodeship")
                if user_voivodeship and region.lower() != user_voivodeship.lower():
                    flash("Nauczyciel regionalny może edytować pinezki tylko w swoim województwo", "error")
                    return redirect(url_for("edit_pin", pin_id=pin_id))

            db.execute("""
                UPDATE pins SET 
                    title = ?, description = ?, region = ?, city = ?, 
                    address = ?, lat = ?, lng = ?
                WHERE id = ?
            """, (title, description, region, city, address, lat, lng, pin_id))
            db.commit()
            flash("Pinezka została zaktualizowana", "success")

        elif 'update_calendar' in request.form and show_calendar:
            db.execute("DELETE FROM teacher_availability WHERE teacher_id = ?", (user_id,))

            for day in range(7):
                start_times = request.form.getlist(f"start_time_{day}")
                end_times = request.form.getlist(f"end_time_{day}")
                modes = request.form.getlist(f"mode_{day}")

                for i in range(len(start_times)):
                    start_time = start_times[i]
                    end_time = end_times[i]
                    teaching_mode = modes[i]

                    if start_time and end_time and teaching_mode:
                        db.execute("""
                            INSERT INTO teacher_availability 
                            (teacher_id, day_of_week, start_time, end_time, teaching_mode, is_available)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (user_id, day, start_time, end_time, teaching_mode, 1))

            db.commit()
            flash("Kalendarz dostępności został zaktualizowany", "success")

        return redirect(url_for("edit_pin", pin_id=pin_id))

    return render_template("edit_pin.html", pin=pin, voivodeships=VOIVODESHIPS.keys(),
                           user_role=role, user_voivodeship=session.get("user_voivodeship"),
                           show_calendar=show_calendar, availability=availability,
                           time_slots=generate_time_slots(), teaching_modes=TEACHING_MODES)


@app.route("/delete_pin/<int:pin_id>", methods=["POST"])
def delete_pin(pin_id):
    if "user_id" not in session:
        flash("Musisz być zalogowany, aby usunąć pinezkę", "error")
        return redirect(url_for("login"))

    db = get_db()
    pin_row = db.execute("SELECT * FROM pins WHERE id = ?", (pin_id,)).fetchone()
    if not pin_row:
        flash("Pinezka nie istnieje", "error")
        return redirect(url_for("index"))

    pin = row_to_dict(pin_row)
    user_id = session["user_id"]
    role = session.get("user_role", "user")

    # Permission check
    can_delete = False
    if role == "admin":
        can_delete = True
    elif role in ["teacher", "regional_teacher"] and pin["created_by"] == user_id:
        can_delete = True
    elif role == "regional_teacher":
        # Regional teacher can delete pins in their region
        user_voivodeship = session.get("user_voivodeship")
        if user_voivodeship and pin["region"].lower() == user_voivodeship.lower():
            can_delete = True

    if not can_delete:
        flash("Nie masz uprawnień do usunięcia tej pinezki", "error")
        return redirect(url_for("index"))

    # Delete related availability data
    db.execute("DELETE FROM teacher_availability WHERE teacher_id = ?", (pin["created_by"],))
    db.execute("DELETE FROM pins WHERE id = ?", (pin_id,))
    db.commit()

    if role in ["teacher", "regional_teacher"] and pin["created_by"] == user_id:
        session.pop("assigned_pin_id", None)

    flash("Pinezka została usunięta", "success")
    return redirect(url_for("index"))


@app.route("/api/pins", methods=["GET"])
def get_pins():
    db = get_db()
    pins_rows = db.execute("""
        SELECT p.*, u.username as creator, u.email as creator_email
        FROM pins p
        JOIN users u ON p.created_by = u.id
    """).fetchall()

    pins = rows_to_dict_list(pins_rows)
    return jsonify(pins)


@app.route("/api/managed_teachers", methods=["GET"])
def get_managed_teachers():
    if "user_id" not in session or session.get("user_role") != "regional_teacher":
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session["user_id"]
    db = get_db()

    teachers_rows = db.execute("""
        SELECT u.id, u.username, u.email, u.voivodeship, 
               CASE WHEN p.id IS NOT NULL THEN 1 ELSE 0 END as has_pin,
               p.title as pin_title
        FROM users u
        LEFT JOIN pins p ON u.id = p.created_by
        WHERE u.regional_teacher_id = ? AND u.role = ?
        ORDER BY u.username
    """, (user_id, ROLE_TEACHER)).fetchall()

    teachers = rows_to_dict_list(teachers_rows)
    return jsonify(teachers)


@app.route("/api/teacher_availability/<int:teacher_id>", methods=["GET"])
def get_teacher_availability_by_id(teacher_id):
    db = get_db()
    teacher = db.execute("SELECT * FROM users WHERE id = ? AND role IN (?, ?)",
                         (teacher_id, ROLE_TEACHER, ROLE_REGIONAL_TEACHER)).fetchone()
    if not teacher:
        return jsonify({"error": "Teacher not found"}), 404

    availability_rows = db.execute("""
        SELECT day_of_week, start_time, end_time, is_available, teaching_mode
        FROM teacher_availability
        WHERE teacher_id = ?
    """, (teacher_id,)).fetchall()

    availability = {}
    for row in availability_rows:
        day = row['day_of_week']
        time_slot = f"{row['start_time']} - {row['end_time']}"
        if day not in availability:
            availability[day] = {}
        availability[day][time_slot] = {
            'available': row['is_available'],
            'mode': row['teaching_mode']
        }

    return jsonify({
        "teacher_id": teacher_id,
        "teacher_name": teacher['username'],
        "availability": availability,
        "time_slots": generate_time_slots()
    })


@app.route("/api/book_appointment", methods=["POST"])
def book_appointment():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    teacher_id = data.get('teacher_id')
    day_of_week = data.get('day_of_week')
    time_slot = data.get('time_slot')
    booking_date = data.get('booking_date')
    lesson_mode = data.get('lesson_mode')
    notes = data.get('notes', '')

    if not all([teacher_id, day_of_week is not None, time_slot, booking_date, lesson_mode]):
        return jsonify({"error": "Missing required fields"}), 400

    student_id = session["user_id"]
    db = get_db()

    # Extract start and end time from time slot
    start_time, end_time = time_slot.split(" - ")

    # Check if teacher exists and has availability in this time slot
    availability = db.execute("""
        SELECT is_available, teaching_mode FROM teacher_availability 
        WHERE teacher_id = ? 
          AND day_of_week = ? 
          AND start_time = ? 
          AND end_time = ?
    """, (teacher_id, day_of_week, start_time, end_time)).fetchone()

    if not availability or not availability['is_available']:
        return jsonify({"error": "Time slot not available"}), 400

    # Check mode compatibility
    slot_mode = availability['teaching_mode']
    if lesson_mode not in slot_mode and slot_mode != 'both':
        return jsonify({"error": "Selected teaching mode not available for this slot"}), 400

    # Check if time slot is already booked
    existing_booking = db.execute("""
        SELECT id FROM bookings 
        WHERE teacher_id = ? 
          AND day_of_week = ? 
          AND time_slot = ? 
          AND booking_date = ? 
          AND status = 'active'
    """, (teacher_id, day_of_week, time_slot, booking_date)).fetchone()

    if existing_booking:
        return jsonify({"error": "Time slot already booked"}), 400

    # Check if student already has a booking at the same time
    student_conflict = db.execute("""
        SELECT id FROM bookings 
        WHERE student_id = ? 
          AND day_of_week = ? 
          AND time_slot = ? 
          AND booking_date = ? 
          AND status = 'active'
    """, (student_id, day_of_week, time_slot, booking_date)).fetchone()

    if student_conflict:
        return jsonify({"error": "You already have a booking at this time"}), 400

    # Get teacher's pricing
    pricing = db.execute("""
        SELECT price_online, price_in_person 
        FROM teacher_pricing 
        WHERE teacher_id = ?
    """, (teacher_id,)).fetchone()

    if not pricing:
        # Default pricing if not set
        pricing = {"price_online": 80.0, "price_in_person": 100.0}

    # Create booking
    try:
        db.execute("""
            INSERT INTO bookings (teacher_id, student_id, day_of_week, time_slot, 
                                 booking_date, lesson_mode, notes,
                                 price_online, price_in_person)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (teacher_id, student_id, day_of_week, time_slot, booking_date,
              lesson_mode, notes, pricing['price_online'], pricing['price_in_person']))

        # Create notification for the teacher
        student_username = session["username"]
        notification_msg = f"Nowa rezerwacja od {student_username} na {booking_date} o {time_slot} (tryb: {'Online' if lesson_mode == 'online' else 'Stacjonarnie'})"
        db.execute("""
            INSERT INTO notifications (user_id, sender_id, message)
            VALUES (?, ?, ?)
        """, (teacher_id, student_id, notification_msg))

        db.commit()

        return jsonify({"success": True, "message": "Appointment booked successfully"})
    except Exception as e:
        return jsonify({"error": "Failed to book appointment"}), 500


@app.route("/api/cancel_booking", methods=["POST"])
def cancel_booking():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    booking_id = data.get('booking_id')

    if not booking_id:
        return jsonify({"error": "Booking ID required"}), 400

    user_id = session["user_id"]
    user_role = session.get("user_role", "user")
    db = get_db()

    # Check if user has permission to cancel
    booking = db.execute("""
        SELECT * FROM bookings WHERE id = ? AND status = 'active'
    """, (booking_id,)).fetchone()

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    # Student can cancel their booking, teacher can cancel bookings for themselves
    if booking['student_id'] != user_id and booking['teacher_id'] != user_id and user_role != 'admin':
        return jsonify({"error": "Not authorized"}), 403

    # Cancel booking
    try:
        db.execute("""
            UPDATE bookings SET status = 'cancelled' WHERE id = ?
        """, (booking_id,))

        # Create notification
        if booking['teacher_id'] != user_id:
            # If student cancels, notify teacher
            student_username = session["username"]
            notification_msg = f"Rezerwacja {booking_id} została anulowana przez {student_username}"
            db.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (booking['teacher_id'], notification_msg))
        elif booking['student_id'] != user_id:
            # If teacher cancels, notify student
            teacher_username = session["username"]
            notification_msg = f"Rezerwacja {booking_id} została anulowana przez nauczyciela {teacher_username}"
            db.execute("""
                INSERT INTO notifications (user_id, message)
                VALUES (?, ?)
            """, (booking['student_id'], notification_msg))

        db.commit()

        return jsonify({"success": True, "message": "Booking cancelled successfully"})
    except Exception as e:
        return jsonify({"error": "Failed to cancel booking"}), 500


@app.route("/api/teacher_bookings/<int:teacher_id>", methods=["GET"])
def get_teacher_bookings(teacher_id):
    db = get_db()

    # Get all active bookings
    bookings_rows = db.execute("""
        SELECT b.*, u.username as student_name, u.email as student_email
        FROM bookings b
        JOIN users u ON b.student_id = u.id
        WHERE b.teacher_id = ? AND b.status = 'active'
        ORDER BY b.booking_date, b.day_of_week, b.time_slot
    """, (teacher_id,)).fetchall()

    bookings = rows_to_dict_list(bookings_rows)
    return jsonify(bookings)


@app.route("/api/my_bookings", methods=["GET"])
def get_my_bookings():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    user_role = session.get("user_role", "user")
    db = get_db()

    if user_role in ["teacher", "regional_teacher"]:
        # Show bookings for this teacher
        bookings_rows = db.execute("""
            SELECT b.*, u.username as student_name, u.email as student_email,
                   t.username as teacher_name
            FROM bookings b
            JOIN users u ON b.student_id = u.id
            JOIN users t ON b.teacher_id = t.id
            WHERE b.teacher_id = ? AND b.status = 'active'
            ORDER BY b.booking_date, b.day_of_week, b.time_slot
        """, (user_id,)).fetchall()
    else:
        # Show student bookings
        bookings_rows = db.execute("""
            SELECT b.*, u.username as teacher_name, u.email as teacher_email,
                   p.title as pin_title
            FROM bookings b
            JOIN users u ON b.teacher_id = u.id
            LEFT JOIN pins p ON b.teacher_id = p.created_by
            WHERE b.student_id = ? AND b.status = 'active'
            ORDER by b.booking_date, b.day_of_week, b.time_slot
        """, (user_id,)).fetchall()

    bookings = rows_to_dict_list(bookings_rows)
    return jsonify(bookings)


@app.route("/bookings")
def bookings():
    if "user_id" not in session:
        flash("Musisz być zalogowany", "error")
        return redirect(url_for("login"))

    return render_template("bookings.html")


@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    db = get_db()

    # Get last 10 notifications
    notifications = db.execute("""
        SELECT n.id, n.message, n.created_at, n.is_read, 
               u.username as sender_name
        FROM notifications n
        LEFT JOIN users u ON n.sender_id = u.id
        WHERE n.user_id = ?
        ORDER BY n.created_at DESC
        LIMIT 10
    """, (user_id,)).fetchall()

    return jsonify(rows_to_dict_list(notifications))


@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    """Admin endpoint to edit user information"""
    if "user_id" not in session or session.get("user_role") != "admin":
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    db = get_db()

    # Get user data
    user_row = db.execute("""
        SELECT u.*, rt.username as regional_teacher_name
        FROM users u
        LEFT JOIN users rt ON u.regional_teacher_id = rt.id
        WHERE u.id = ?
    """, (user_id,)).fetchone()

    if not user_row:
        flash("Użytkownik nie istnieje", "error")
        return redirect(url_for("users"))

    user = row_to_dict(user_row)

    # Get regional teachers for dropdown
    regional_teachers = db.execute("""
        SELECT id, username, email, voivodeship 
        FROM users 
        WHERE role = ? 
        ORDER BY voivodeship, username
    """, (ROLE_REGIONAL_TEACHER,)).fetchall()

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        role_str = request.form.get("role", "user")
        voivodeship = request.form.get("voivodeship", "").strip()
        regional_teacher_id = request.form.get("regional_teacher_id", "").strip()
        subjects = request.form.getlist("subjects")
        parental_email = request.form.get("parental_email", "").strip()

        role_mapping = {
            "user": ROLE_USER,
            "teacher": ROLE_TEACHER,
            "regional_teacher": ROLE_REGIONAL_TEACHER,
            "admin": ROLE_ADMIN
        }
        role = role_mapping.get(role_str.lower(), ROLE_USER)

        # Validation
        if not username or not email:
            flash("Nazwa użytkownika i email są wymagane", "error")
            return redirect(url_for("edit_user", user_id=user_id))

        if not is_valid_email(email):
            flash("Podaj prawidłowy adres email", "error")
            return redirect(url_for("edit_user", user_id=user_id))

        # Check if username exists (exclude current user)
        existing_user = db.execute("SELECT * FROM users WHERE username = ? AND id != ?", (username, user_id)).fetchone()
        if existing_user:
            flash("Użytkownik o tej nazwie już istnieje", "error")
            return redirect(url_for("edit_user", user_id=user_id))

        # Check if email exists (exclude current user)
        existing_email = db.execute("SELECT * FROM users WHERE email = ? AND id != ?", (email, user_id)).fetchone()
        if existing_email:
            flash("Użytkownik z tym adresem email już istnieje", "error")
            return redirect(url_for("edit_user", user_id=user_id))

        # Role-specific validation
        if role == ROLE_USER:
            if not voivodeship or voivodeship not in VOIVODESHIPS:
                flash("Użytkownik musi mieć przypisane prawidłowe województwo", "error")
                return redirect(url_for("edit_user", user_id=user_id))
            # Validate parental email
            if parental_email and not is_valid_email(parental_email):
                flash("Podaj prawidłowy adres email opiekuna", "error")
                return redirect(url_for("edit_user", user_id=user_id))
        elif role == ROLE_TEACHER:
            if not regional_teacher_id:
                flash("Nauczyciel musi mieć przypisanego nauczyciela regionalnego", "error")
                return redirect(url_for("edit_user", user_id=user_id))
            # Verify the regional teacher exists
            regional_teacher = db.execute("SELECT * FROM users WHERE id = ? AND role = ?",
                                          (regional_teacher_id, ROLE_REGIONAL_TEACHER)).fetchone()
            if not regional_teacher:
                flash("Wybrany nauczyciel regionalny nie istnieje", "error")
                return redirect(url_for("edit_user", user_id=user_id))
            parental_email = None  # Clear for non-student users
        elif role == ROLE_REGIONAL_TEACHER:
            if not voivodeship or voivodeship not in VOIVODESHIPS:
                flash("Nauczyciel regionalny musi mieć przypisane województwo", "error")
                return redirect(url_for("edit_user", user_id=user_id))
            parental_email = None  # Clear for non-student users
        else:  # Admin
            parental_email = None  # Clear for non-student users

        # Set values based on role
        final_voivodeship = voivodeship if voivodeship in VOIVODESHIPS else None
        final_rt_id = regional_teacher_id if role == ROLE_TEACHER and regional_teacher_id else None

        # Convert list of subjects to comma-separated string
        subjects_str = ", ".join(subjects) if subjects else ""

        # Update user
        try:
            db.execute("""
                UPDATE users 
                SET username = ?, email = ?, role = ?, voivodeship = ?, 
                    regional_teacher_id = ?, subjects = ?, parental_email = ?
                WHERE id = ?
            """, (username, email, role, final_voivodeship, final_rt_id, subjects_str, parental_email, user_id))
            db.commit()

            flash("Dane użytkownika zostały zaktualizowane", "success")
            return redirect(url_for("users"))
        except Exception as e:
            flash("Błąd podczas aktualizacji danych użytkownika", "error")
            return redirect(url_for("edit_user", user_id=user_id))

    return render_template("edit_user.html",
                           user=user,
                           voivodeships=VOIVODESHIPS.keys(),
                           regional_teachers=regional_teachers,
                           school_subjects=SCHOOL_SUBJECTS)


@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    """Admin endpoint to delete a user"""
    if "user_id" not in session or session.get("user_role") != "admin":
        flash("Nie masz uprawnień do tej akcji", "error")
        return redirect(url_for("index"))

    # Prevent admin from deleting themselves
    if user_id == session["user_id"]:
        flash("Nie możesz usunąć samego siebie", "error")
        return redirect(url_for("users"))

    db = get_db()

    # Check if user exists
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        flash("Użytkownik nie istnieje", "error")
        return redirect(url_for("users"))

    try:
        # Delete related data first (foreign key constraints)
        db.execute("DELETE FROM teacher_availability WHERE teacher_id = ?", (user_id,))
        db.execute("DELETE FROM bookings WHERE teacher_id = ? OR student_id = ?", (user_id, user_id))
        db.execute("DELETE FROM notifications WHERE user_id = ? OR sender_id = ?", (user_id, user_id))
        db.execute("DELETE FROM pins WHERE created_by = ?", (user_id,))
        db.execute("DELETE FROM teacher_pricing WHERE teacher_id = ?", (user_id,))

        # Update users who have this user as regional teacher
        db.execute("UPDATE users SET regional_teacher_id = NULL WHERE regional_teacher_id = ?", (user_id,))

        # Finally delete the user
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()

        flash(f"Użytkownik {user['username']} został usunięty", "success")
    except Exception as e:
        flash("Błąd podczas usuwania użytkownika", "error")

    return redirect(url_for("users"))


@app.route("/messages", methods=["GET", "POST"])
def messages():
    if "user_id" not in session or session.get("user_role") != "admin":
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    db = get_db()

    if request.method == "POST":
        user_id = request.form.get("user_id")
        message = request.form.get("message")

        if not message:
            flash("Wiadomość nie może być pusta", "error")
            return redirect(url_for("messages"))

        # Send to all users or specific user?
        if user_id == "all":
            # Send to all users
            users = db.execute("SELECT id FROM users").fetchall()
            for user in users:
                db.execute("""
                    INSERT INTO notifications (user_id, sender_id, message)
                    VALUES (?, ?, ?)
                """, (user["id"], session["user_id"], message))
        else:
            # Send to specific user
            user = db.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                flash("Użytkownik nie istnieje", "error")
                return redirect(url_for("messages"))

            db.execute("""
                INSERT INTO notifications (user_id, sender_id, message)
                VALUES (?, ?, ?)
            """, (user_id, session["user_id"], message))

        db.commit()
        flash("Wiadomość została wysłana", "success")
        return redirect(url_for("messages"))

    # Get all users for the dropdown
    users = db.execute("""
        SELECT id, username, role 
        FROM users
        ORDER BY role DESC, username
    """).fetchall()

    return render_template("messages.html", users=users)


@app.route("/online_teachers", methods=["GET"])
def online_teachers():
    """Strona z listą wszystkich nauczycieli (online i offline)"""
    if "user_id" not in session:
        flash("Musisz być zalogowany, aby przeglądać nauczycieli", "error")
        return redirect(url_for("login"))

    db = get_db()

    # Pobierz parametry filtrowania
    subject = request.args.get("subject", "")
    region = request.args.get("region", "")
    mode = request.args.get("mode", "")

    # Zbuduj zapytanie
    query = """
        SELECT u.id, u.first_name, u.last_name, u.subjects, u.voivodeship, 
               u.teaching_modes, u.availability_hours, u.is_online, u.last_online,
               p.city, p.address
        FROM users u
        LEFT JOIN pins p ON u.id = p.created_by
        WHERE u.role IN (?, ?)
    """
    params = [ROLE_TEACHER, ROLE_REGIONAL_TEACHER]

    if subject:
        query += " AND u.subjects LIKE ?"
        params.append(f"%{subject}%")

    if region and region != "all":
        query += " AND u.voivodeship = ?"
        params.append(region)

    if mode and mode != "all":
        query += " AND u.teaching_modes LIKE ?"
        params.append(f"%{mode}%")

    query += " ORDER BY u.is_online DESC, u.last_online DESC"

    teachers = db.execute(query, params).fetchall()
    teachers = rows_to_dict_list(teachers)

    return render_template("online_teachers.html",
                           teachers=teachers,
                           subjects=SCHOOL_SUBJECTS,
                           voivodeships=VOIVODESHIPS.keys(),
                           teaching_modes=TEACHING_MODES)


@app.route("/teacher_profile/<int:teacher_id>")
def teacher_profile(teacher_id):
    """Profil nauczyciela"""
    if "user_id" not in session:
        flash("Musisz być zalogowany, aby przeglądać profile nauczycieli", "error")
        return redirect(url_for("login"))

    db = get_db()
    teacher = db.execute("""
        SELECT u.*, p.city, p.address, p.lat, p.lng, 
               rt.username as regional_teacher_name
        FROM users u
        LEFT JOIN pins p ON u.id = p.created_by
        LEFT JOIN users rt ON u.regional_teacher_id = rt.id
        WHERE u.id = ? AND u.role IN (?, ?)
    """, (teacher_id, ROLE_TEACHER, ROLE_REGIONAL_TEACHER)).fetchone()

    if not teacher:
        flash("Nauczyciel nie istnieje", "error")
        return redirect(url_for("index"))

    teacher = row_to_dict(teacher)

    # Pobierz dostępność
    availability = {}
    availability_rows = db.execute("""
        SELECT day_of_week, start_time, end_time, is_available, teaching_mode
        FROM teacher_availability
        WHERE teacher_id = ?
    """, (teacher_id,)).fetchall()

    for row in availability_rows:
        day = row['day_of_week']
        time_slot = f"{row['start_time']} - {row['end_time']}"
        if day not in availability:
            availability[day] = {}
        availability[day][time_slot] = {
            'available': row['is_available'],
            'mode': row['teaching_mode']
        }

    # Pobierz opinie
    reviews = []
    if db:
        reviews = db.execute("""
            SELECT r.*, u.username as student_name
            FROM reviews r
            JOIN users u ON r.student_id = u.id
            WHERE r.teacher_id = ?
            ORDER BY r.created_at DESC
        """, (teacher_id,)).fetchall()
        reviews = rows_to_dict_list(reviews)

    pricing = db.execute("""
        SELECT price_online, price_in_person 
        FROM teacher_pricing 
        WHERE teacher_id = ?
    """, (teacher_id,)).fetchone()

    if not pricing:
        pricing = {"price_online": "brak danych", "price_in_person": "brak danych"}

    unread_notifications = 0
    if 'user_id' in session:
        user_id = session['user_id']
        unread_notifications = db.execute("""
                SELECT COUNT(*) as count
                FROM notifications
                WHERE user_id = ? AND is_read = 0
            """, (user_id,)).fetchone()["count"]

    return render_template("teacher_profile.html",
                           teacher=teacher,
                           availability=availability,
                           reviews=reviews,
                           time_slots=generate_time_slots(),
                           datetime=datetime,
                           pricing=pricing,
                           logged_in='user_id' in session,
                           session=session,
                           unread_notifications=unread_notifications)


@app.route("/book_teacher/<int:teacher_id>", methods=["GET", "POST"])
def book_teacher(teacher_id):
    if "user_id" not in session:
        flash("Musisz być zalogowany, aby umawiać lekcje", "error")
        return redirect(url_for("login"))

    student_id = session["user_id"]
    db = get_db()
    week_offset = request.args.get('week_offset', 0, type=int)
    week_offset = max(0, min(1, week_offset))
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_dates = [start_of_week + timedelta(days=i) for i in range(14)]

    teacher = db.execute("""
        SELECT id, first_name, last_name, teaching_modes
        FROM users 
        WHERE id = ? AND role IN (?, ?)
    """, (teacher_id, ROLE_TEACHER, ROLE_REGIONAL_TEACHER)).fetchone()

    if not teacher:
        flash("Nauczyciel nie istnieje", "error")
        return redirect(url_for("index"))

    teacher = row_to_dict(teacher)
    pricing = db.execute("""
        SELECT price_online, price_in_person 
        FROM teacher_pricing 
        WHERE teacher_id = ?
    """, (teacher_id,)).fetchone()

    if not pricing:
        pricing = {"price_online": 80.0, "price_in_person": 100.0}

    availability_rows = db.execute("""
        SELECT day_of_week, start_time, end_time, is_available, teaching_mode
        FROM teacher_availability
        WHERE teacher_id = ? AND is_available = 1
    """, (teacher_id,)).fetchall()

    availability_blocks = {}
    for row in availability_rows:
        day = row['day_of_week']
        if day not in availability_blocks:
            availability_blocks[day] = []

        # Normalize times
        start_time = normalize_time(row['start_time'])
        end_time = normalize_time(row['end_time'])
        time_slot = f"{start_time} - {end_time}"

        availability_blocks[day].append({
            "start": start_time,
            "end": end_time,
            "mode": row['teaching_mode'],
            "time_slot": time_slot
        })

    # Get all booked time slots for the two-week period
    booked_slots = {}
    if week_dates:
        start_date = week_dates[0].strftime("%Y-%m-%d")
        end_date = week_dates[-1].strftime("%Y-%m-%d")

        booking_rows = db.execute("""
            SELECT booking_date, time_slot 
            FROM bookings 
            WHERE teacher_id = ? 
              AND status NOT IN ('cancelled', 'odwolana')
              AND booking_date BETWEEN ? AND ?
        """, (teacher_id, start_date, end_date)).fetchall()

        for row in booking_rows:
            date_str = row['booking_date']
            if date_str not in booked_slots:
                booked_slots[date_str] = set()

            # Normalize time slot
            normalized_slot = normalize_time_slot(row['time_slot'])
            booked_slots[date_str].add(normalized_slot)

    if request.method == "POST":
        day_of_week = request.form.get("day_of_week")
        time_slot = request.form.get("time_slot")
        booking_date = request.form.get("selected_booking_date")
        lesson_mode = request.form.get("lesson_mode")
        notes = request.form.get("notes", "")

        if not all([day_of_week, time_slot, booking_date, lesson_mode]):
            flash("Wypełnij wszystkie wymagane pola", "error")
            return redirect(url_for("book_teacher", teacher_id=teacher_id, week_offset=week_offset))

        try:
            day_of_week = int(day_of_week)
        except ValueError:
            flash("Nieprawidłowy dzień tygodnia", "error")
            return redirect(url_for("book_teacher", teacher_id=teacher_id, week_offset=week_offset))

        # Normalize time slot consistently
        normalized_time_slot = normalize_time_slot(time_slot)

        # Check for existing booking with normalized time slot
        if booking_date in booked_slots and normalized_time_slot in booked_slots[booking_date]:
            flash("Wybrany termin jest już zajęty", "error")
            return redirect(url_for("book_teacher", teacher_id=teacher_id, week_offset=week_offset))

        # Find the availability block to validate mode
        valid_mode = False
        block_mode = "online"
        if day_of_week in availability_blocks:
            for block in availability_blocks[day_of_week]:
                if normalize_time_slot(block["time_slot"]) == normalized_time_slot:
                    block_mode = block["mode"]
                    if block_mode in ['both', 'hybrid']:
                        valid_mode = lesson_mode in ['online', 'in_person']
                    else:
                        valid_mode = lesson_mode == block_mode
                    break

        if not valid_mode:
            flash(f"Wybrany tryb lekcji nie jest dostępny w tym terminie. Dostępny tryb: {block_mode}", "error")
            return redirect(url_for("book_teacher", teacher_id=teacher_id, week_offset=week_offset))

        try:
            # Create booking with normalized time slot
            db.execute("""
                INSERT INTO bookings (teacher_id, student_id, day_of_week, time_slot, booking_date, lesson_mode, notes,
                                     price_online, price_in_person)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (teacher_id, student_id, day_of_week, normalized_time_slot, booking_date, lesson_mode, notes,
                  pricing['price_online'], pricing['price_in_person']))

            # Create notification for the teacher
            student_username = session["username"]
            start_time, end_time = normalized_time_slot.split(" - ")
            notification_msg = f"Nowa rezerwacja od {student_username} na {booking_date} o {start_time}-{end_time} (tryb: {'Online' if lesson_mode == 'online' else 'Stacjonarnie'})"
            db.execute("""
                INSERT INTO notifications (user_id, sender_id, message)
                VALUES (?, ?, ?)
            """, (teacher_id, student_id, notification_msg))

            db.commit()
            flash("Rezerwacja została potwierdzona", "success")
            return redirect(url_for("bookings"))
        except sqlite3.IntegrityError as e:
            flash("Ten termin został już zarezerwowany przez kogoś innego", "error")
            return redirect(url_for("book_teacher", teacher_id=teacher_id, week_offset=week_offset))
        except Exception as e:
            flash(f"Błąd podczas rezerwacji terminu: {str(e)}", "error")
            return redirect(url_for("book_teacher", teacher_id=teacher_id, week_offset=week_offset))

    return render_template("book_teacher.html",
                           teacher=teacher,
                           availability_blocks=availability_blocks,
                           booked_slots=booked_slots,
                           teaching_modes=TEACHING_MODES,
                           pricing=pricing,
                           timedelta=timedelta,
                           week_dates=week_dates,
                           week_offset=week_offset)


@app.route("/crm", methods=["GET", "POST"])
def crm():
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    teacher_id = session["user_id"]
    db = get_db()
    today = datetime.now().date()
    current_weekday = today.weekday()
    selected_date_str = request.args.get('date', today.strftime('%Y-%m-%d'))

    try:
        selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    except ValueError:
        selected_date = today

    start_of_week = selected_date - timedelta(days=selected_date.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    week_dates = [(start_of_week + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    week_days = [(start_of_week + timedelta(days=i)).strftime('%d.%m') for i in range(7)]
    prev_week = (selected_date - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (selected_date + timedelta(days=7)).strftime('%Y-%m-%d')

    overrides = {}
    override_rows = db.execute("""
        SELECT date, is_free 
        FROM availability_overrides 
        WHERE teacher_id = ? AND date BETWEEN ? AND ?
    """, (teacher_id, start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d'))).fetchall()

    for row in override_rows:
        overrides[row['date']] = row['is_free']

    availability_rows = db.execute("""
        SELECT day_of_week, start_time, end_time, is_available, teaching_mode
        FROM teacher_availability
        WHERE teacher_id = ?
        ORDER BY day_of_week, start_time
    """, (teacher_id,)).fetchall()

    availability = {}
    for row in availability_rows:
        day = row['day_of_week']
        time_slot = f"{row['start_time']} - {row['end_time']}"
        if day not in availability:
            availability[day] = {}
        availability[day][time_slot] = {
            'available': bool(row['is_available']),
            'mode': row['teaching_mode']
        }

    bookings_for_week = db.execute("""
        SELECT b.id, b.day_of_week, b.time_slot, b.booking_date, 
               u.username as student_name, u.email as student_email
        FROM bookings b
        JOIN users u ON b.student_id = u.id
        WHERE b.teacher_id = ? 
          AND b.status = 'active'
          AND b.booking_date BETWEEN ? AND ?
    """, (teacher_id, start_of_week.strftime('%Y-%m-%d'), end_of_week.strftime('%Y-%m-%d'))).fetchall()

    bookings_info = {}
    for booking in bookings_for_week:
        day = booking['day_of_week']
        slot = booking['time_slot']
        date_str = booking['booking_date']

        if day not in bookings_info:
            bookings_info[day] = {}
        if slot not in bookings_info[day]:
            bookings_info[day][slot] = []

        bookings_info[day][slot].append({
            'student_name': booking['student_name'],
            'student_email': booking['student_email'],
            'date': date_str
        })

    managed_teachers = []
    if session.get("user_role") == "regional_teacher":
        managed_teachers_rows = db.execute("""
            SELECT id, username, email, voivodeship 
            FROM users 
            WHERE regional_teacher_id = ? AND role = ?
            ORDER BY username
        """, (teacher_id, ROLE_TEACHER)).fetchall()
        managed_teachers = rows_to_dict_list(managed_teachers_rows)

    pricing_row = db.execute("SELECT * FROM teacher_pricing WHERE teacher_id = ?", (teacher_id,)).fetchone()
    if pricing_row:
        pricing = dict(pricing_row)
    else:
        pricing = {"price_online": 80.0, "price_in_person": 100.0}

    # Pobierz saldo użytkownika
    balance = get_balance(teacher_id)

    return render_template("crm.html",
                           availability=availability,
                           time_slots=generate_time_slots(),
                           week_dates=week_dates,
                           week_days=week_days,
                           selected_date=selected_date_str,
                           current_weekday=current_weekday,
                           overrides=overrides,
                           today=today.strftime('%Y-%m-%d'),
                           prev_week=prev_week,
                           next_week=next_week,
                           bookings_info=bookings_info,
                           managed_teachers=managed_teachers,
                           pricing=pricing,
                           balance=balance)


@app.route("/crm/set_day_free", methods=["POST"])
def set_day_free():
    """Set entire day as free for teacher"""
    # Authentication and authorization
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    teacher_id = session["user_id"]
    date = request.form.get("date")
    is_free = request.form.get("is_free", "1") == "1"  # Default to True if not specified

    # Validate input
    if not date:
        return jsonify({"error": "Brakująca data"}), 400

    try:
        # Validate date format
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Nieprawidłowy format daty. Użyj YYYY-MM-DD"}), 400

    db = get_db()

    try:
        # Check if override already exists
        existing_override = db.execute("""
            SELECT id, is_free 
            FROM availability_overrides 
            WHERE teacher_id = ? AND date = ?
        """, (teacher_id, date)).fetchone()

        if existing_override:
            # Update existing override if status changed
            if existing_override['is_free'] != is_free:
                db.execute("""
                    UPDATE availability_overrides 
                    SET is_free = ?
                    WHERE id = ?
                """, (is_free, existing_override['id']))
                action = "zaktualizowany"
            else:
                # No change needed
                return jsonify({
                    "success": True,
                    "message": "Status dni pozostaje bez zmian",
                    "is_free": is_free
                })
        else:
            # Create new override
            db.execute("""
                INSERT INTO availability_overrides (teacher_id, date, is_free)
                VALUES (?, ?, ?)
            """, (teacher_id, date, is_free))
            action = "ustawiony"

        db.commit()

        return jsonify({
            "success": True,
            "message": f"Dzień {date} został {'wolny' if is_free else 'dostępny'}",
            "is_free": is_free
        })

    except Exception as e:
        return jsonify({
            "error": f"Błąd bazy danych: {str(e)}"
        }), 500


@app.route("/crm/pricing", methods=["GET", "POST"])
def crm_pricing():
    """Manage teacher pricing"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    teacher_id = session["user_id"]
    db = get_db()

    # Get current pricing
    pricing = db.execute("SELECT * FROM teacher_pricing WHERE teacher_id = ?", (teacher_id,)).fetchone()

    if request.method == "POST":
        price_online = float(request.form.get("price_online", 80.0))
        price_in_person = float(request.form.get("price_in_person", 100.0))

        if pricing:
            db.execute("""
                UPDATE teacher_pricing 
                SET price_online = ?, price_in_person = ?, updated_at = CURRENT_TIMESTAMP
                WHERE teacher_id = ?
            """, (price_online, price_in_person, teacher_id))
        else:
            db.execute("""
                INSERT INTO teacher_pricing (teacher_id, price_online, price_in_person)
                VALUES (?, ?, ?)
            """, (teacher_id, price_online, price_in_person))

        db.commit()
        flash("Cennik został zaktualizowany", "success")
        return redirect(url_for("crm_pricing"))

    return render_template("crm_pricing.html", pricing=pricing)


@app.route("/api/crm/availability", methods=["GET"])
def get_crm_availability():
    """Get teacher's availability blocks for CRM"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    teacher_id = session["user_id"]
    db = get_db()

    blocks = db.execute("""
        SELECT id, day_of_week, start_time, end_time, teaching_mode
        FROM teacher_availability
        WHERE teacher_id = ?
        ORDER BY day_of_week, start_time
    """, (teacher_id,)).fetchall()

    return jsonify(rows_to_dict_list(blocks))


@app.route("/api/crm/availability/<int:block_id>", methods=["DELETE"])
def delete_availability_block(block_id):
    """Delete a specific availability block"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    teacher_id = session["user_id"]
    db = get_db()

    # Verify the block belongs to the teacher
    block = db.execute("""
        SELECT * FROM teacher_availability 
        WHERE id = ? AND teacher_id = ?
    """, (block_id, teacher_id)).fetchone()

    if not block:
        return jsonify({"error": "Block not found"}), 404

    db.execute("DELETE FROM teacher_availability WHERE id = ?", (block_id,))
    db.commit()

    return jsonify({"success": True})


@app.route("/api/crm/availability", methods=["POST"])
def save_teacher_availability():
    """Save teacher's availability blocks"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    teacher_id = session["user_id"]
    data = request.get_json()
    blocks = data.get("blocks", [])
    db = get_db()

    try:
        # Delete all existing blocks
        db.execute("DELETE FROM teacher_availability WHERE teacher_id = ?", (teacher_id,))

        # Insert new blocks with is_available=1
        new_ids = []
        for block in blocks:
            cur = db.execute("""
                INSERT INTO teacher_availability 
                (teacher_id, day_of_week, start_time, end_time, teaching_mode, is_available)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                teacher_id,
                block["day_of_week"],
                block["start_time"],
                block["end_time"],
                block["teaching_mode"],
                1  # Set is_available to True (1)
            ))
            new_ids.append(cur.lastrowid)

        db.commit()
        return jsonify({
            "success": True,
            "message": "Availability saved",
            "new_ids": new_ids
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/crm/bookings", methods=["GET"])
def get_crm_bookings():
    """Get teacher's bookings for CRM"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    teacher_id = session["user_id"]
    db = get_db()

    # Get upcoming bookings (next 30 days)
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

    # Query now uses time_slot instead of non-existent start_time/end_time
    bookings_rows = db.execute("""
        SELECT b.id, b.teacher_id, b.student_id, b.day_of_week, b.booking_date, 
               b.lesson_mode, b.status, b.notes, b.time_slot,
               u.username as student_name, u.email as student_email
        FROM bookings b
        JOIN users u ON b.student_id = u.id
        WHERE b.teacher_id = ? 
          AND b.status = 'active'
          AND b.booking_date BETWEEN ? AND ?
        ORDER BY b.booking_date, b.time_slot
    """, (teacher_id, start_date, end_date)).fetchall()

    # Process results to split time_slot into start_time and end_time
    bookings = []
    for row in bookings_rows:
        row_dict = dict(row)

        # Extract start_time and end_time from time_slot
        if 'time_slot' in row_dict and row_dict['time_slot']:
            parts = row_dict['time_slot'].split(' - ')
            if len(parts) == 2:
                row_dict['start_time'] = parts[0].strip()
                row_dict['end_time'] = parts[1].strip()

        bookings.append(row_dict)

    return jsonify(bookings)


@app.route("/api/crm/update_booking/<int:booking_id>", methods=["PUT"])
def update_crm_booking(booking_id):
    """Update booking status (cancel/confirm)"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    teacher_id = session["user_id"]
    db = get_db()
    data = request.get_json()

    # Validate booking exists and belongs to teacher
    booking = db.execute("""
        SELECT * FROM bookings 
        WHERE id = ? AND teacher_id = ?
    """, (booking_id, teacher_id)).fetchone()

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    new_status = data.get("status")
    if new_status not in ["confirmed", "cancelled", "completed"]:
        return jsonify({"error": "Invalid status"}), 400

    try:
        db.execute("""
            UPDATE bookings SET status = ? 
            WHERE id = ?
        """, (new_status, booking_id))

        # Create notification for student
        teacher_name = session.get("username", "Nauczyciel")
        notification_msg = f"Status rezerwacji {booking_id} został zmieniony na {new_status} przez {teacher_name}"
        db.execute("""
            INSERT INTO notifications (user_id, sender_id, message)
            VALUES (?, ?, ?)
        """, (booking["student_id"], teacher_id, notification_msg))

        db.commit()
        return jsonify({"success": True, "message": "Booking status updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/crm/student_info/<int:student_id>", methods=["GET"])
def get_crm_student_info(student_id):
    """Get student information for CRM"""
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 401

    db = get_db()

    student = db.execute("""
        SELECT id, username, email, first_name, last_name, phone, school
        FROM users
        WHERE id = ? AND role = ?
    """, (student_id, ROLE_USER)).fetchone()

    if not student:
        return jsonify({"error": "Student not found"}), 404

    # Get student's bookings with this teacher
    bookings = db.execute("""
        SELECT id, booking_date, day_of_week, time_slot, lesson_mode, status
        FROM bookings
        WHERE student_id = ? AND teacher_id = ?
        ORDER BY booking_date DESC
        LIMIT 10
    """, (student_id, session["user_id"])).fetchall()

    return jsonify({
        "student": row_to_dict(student),
        "bookings": rows_to_dict_list(bookings)
    })


def get_role_name(role_id):
    """Convert role ID to role name"""
    role_names = {
        ROLE_USER: "user",
        ROLE_TEACHER: "teacher",
        ROLE_REGIONAL_TEACHER: "regional_teacher",
        ROLE_ADMIN: "admin"
    }
    return role_names.get(role_id, "user")


def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def generate_time_slots():
    """Generate time slots from 08:00 to 20:00 with 30-minute intervals"""
    slots = []
    start_hour = 8
    end_hour = 20

    for hour in range(start_hour, end_hour):
        for minute in [0, 30]:
            start_time = f"{hour:02d}:{minute:02d}"
            end_minute = minute + 30
            end_hour_calc = hour
            if end_minute >= 60:
                end_minute = 0
                end_hour_calc += 1
            end_time = f"{end_hour_calc:02d}:{end_minute:02d}"
            slots.append({
                'start': start_time,
                'end': end_time,
                'label': f"{start_time} - {end_time}"
            })
    return [slot['label'] for slot in slots]


def init_db():
    with app.app_context():
        db = get_db()

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                hash TEXT NOT NULL,
                role INTEGER DEFAULT 0,
                voivodeship TEXT,
                regional_teacher_id INTEGER,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                school TEXT,
                subjects TEXT,
                experience_years INTEGER,
                bio TEXT,
                profile_picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_online INTEGER DEFAULT 0,
                last_online TIMESTAMP,
                teaching_modes TEXT DEFAULT 'online',
                availability_hours INTEGER DEFAULT 8,
                parental_email TEXT,
                password_setup_token TEXT,
                token_expiry TIMESTAMP,
                password_reset_token TEXT,
                password_reset_expiry TIMESTAMP,
                tmethod TEXT DEFAULT 'default_method'
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS pins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                region TEXT NOT NULL,
                city TEXT NOT NULL,
                address TEXT NOT NULL,
                lat REAL NOT NULL,
                lng REAL NOT NULL,
                created_by INTEGER NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS teacher_availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                teaching_mode TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES users (id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                time_slot TEXT NOT NULL,
                booking_date TEXT NOT NULL,
                lesson_mode TEXT NOT NULL DEFAULT 'online',
                status TEXT DEFAULT 'active',
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                price_online REAL DEFAULT 80.0,
                price_in_person REAL DEFAULT 100.0,
                cancellation_reason TEXT,
                FOREIGN KEY (teacher_id) REFERENCES users (id),
                FOREIGN KEY (student_id) REFERENCES users (id),
                UNIQUE(teacher_id, day_of_week, time_slot, booking_date)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                sender_id INTEGER,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (sender_id) REFERENCES users(id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS teacher_pricing (
                teacher_id INTEGER PRIMARY KEY,
                price_online REAL NOT NULL DEFAULT 80.0,
                price_in_person REAL NOT NULL DEFAULT 100.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES users (id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS availability_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                is_free INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (teacher_id) REFERENCES users (id),
                UNIQUE(teacher_id, date)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS ref_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                link TEXT UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL,
                recipient_id INTEGER,
                lesson1_completed INTEGER DEFAULT 0,
                lesson2_completed INTEGER DEFAULT 0,
                lesson3_completed INTEGER DEFAULT 0,
                lesson4_completed INTEGER DEFAULT 0,
                lesson5_completed INTEGER DEFAULT 0,
                all_completed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users (id),
                FOREIGN KEY (recipient_id) REFERENCES users (id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                FOREIGN KEY (teacher_id) REFERENCES users(id),
                FOREIGN KEY (student_id) REFERENCES users(id)
                )
            """)

        # Dodaj w init_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_balances (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


        # Create admin user if not exists
        admin = db.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
        if not admin:
            hash_pw = generate_password_hash("admin")
            db.execute(
                "INSERT INTO users (username, email, hash, role) VALUES (?, ?, ?, ?)",
                ("admin", "admin@system.local", hash_pw, ROLE_ADMIN)
            )

        db.commit()


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            token = secrets.token_urlsafe(32)
            token_expiry = datetime.now() + timedelta(hours=1)

            db.execute("""
                UPDATE users 
                SET password_reset_token = ?, password_reset_expiry = ?
                WHERE id = ?
            """, (token, token_expiry, user["id"]))
            db.commit()

            reset_link = url_for('reset_password', token=token, _external=True)
            flash(f"Jeśli adres email jest zarejestrowany, wysłaliśmy link resetujący hasło. Link: {reset_link}",
                  "info")
        else:
            flash("Jeśli adres email jest zarejestrowany, wysłaliśmy link resetujący hasło.", "info")

        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    db = get_db()
    user = db.execute("""
        SELECT * FROM users 
        WHERE password_reset_token = ? AND password_reset_expiry > CURRENT_TIMESTAMP
    """, (token,)).fetchone()

    if not user:
        flash("Nieprawidłowy lub przeterminowany token resetujący", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if password != confirmation:
            flash("Hasła nie są identyczne", "error")
            return redirect(url_for('reset_password', token=token))

        hash_pw = generate_password_hash(password)
        db.execute("""
            UPDATE users 
            SET hash = ?, password_reset_token = NULL, password_reset_expiry = NULL
            WHERE id = ?
        """, (hash_pw, user["id"]))
        db.commit()

        flash("Hasło zostało zresetowane. Możesz się teraz zalogować", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html", token=token)


@app.template_filter('format_date')
def format_date(value):
    if value is None:
        return "Nieznana"
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except:
        return value


@app.template_filter('string_to_date')
def string_to_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except:
        return datetime.now()


@app.route("/crm/referrals", methods=["GET", "POST"])
def crm_referrals():
    # Zezwól regional_teacher, admin i teacher
    if "user_id" not in session or session.get("user_role") not in ["regional_teacher", "admin", "teacher"]:
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    user_id = session["user_id"]
    db = get_db()

    if request.method == "POST":
        token = secrets.token_urlsafe(16)
        link = url_for('register_teacher_ref', token=token, _external=True)

        db.execute("""
            INSERT INTO ref_links (link, owner_id)
            VALUES (?, ?)
        """, (link, user_id))
        db.commit()
        flash("Nowy link polecający został wygenerowany", "success")
        return redirect(url_for("crm_referrals"))

    links = db.execute("""
        SELECT r.*, u.username as recipient_name
        FROM ref_links r
        LEFT JOIN users u ON r.recipient_id = u.id
        WHERE r.owner_id = ?
        ORDER BY r.created_at DESC
    """, (user_id,)).fetchall()

    return render_template("crm_referrals.html", links=links)

@app.route("/register/teacher/<token>", methods=["GET", "POST"])
def register_teacher_ref(token):
    db = get_db()
    ref_link = db.execute("""
        SELECT * FROM ref_links 
        WHERE link LIKE ? AND recipient_id IS NULL
    """, (f"%{token}%",)).fetchone()

    if not ref_link:
        flash("Nieprawidłowy lub wykorzystany link", "error")
        return redirect(url_for("register"))

    owner_id = ref_link["owner_id"]
    # Pobierz właściciela linku (może być regional_teacher lub teacher)
    owner = db.execute("""
        SELECT * FROM users 
        WHERE id = ? AND role IN (?, ?)
    """, (owner_id, ROLE_REGIONAL_TEACHER, ROLE_TEACHER)).fetchone()

    if not owner:
        flash("Błędny link polecający", "error")
        return redirect(url_for("register"))

    # Dla nauczyciela (teacher) używamy jego regional_teacher_id
    regional_teacher_id = owner["regional_teacher_id"] if owner["role"] == ROLE_TEACHER else owner["id"]

    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        voivodeship = owner["voivodeship"]  # Użyj województwa właściciela linku

        if not all([username, email, password]):
            flash("Wypełnij wszystkie wymagane pola", "error")
            return redirect(url_for("register_teacher_ref", token=token))

        if not is_valid_email(email):
            flash("Podaj prawidłowy adres email", "error")
            return redirect(url_for("register_teacher_ref", token=token))

        existing_user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if existing_user:
            flash("Użytkownik o tej nazwie już istnieje", "error")
            return redirect(url_for("register_teacher_ref", token=token))

        existing_email = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if existing_email:
            flash("Użytkownik z tym adresem email już istnieje", "error")
            return redirect(url_for("register_teacher_ref", token=token))

        try:
            hash_pw = generate_password_hash(password)
            db.execute("""
                INSERT INTO users (
                    username, email, hash, role, voivodeship, regional_teacher_id
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (username, email, hash_pw, ROLE_TEACHER, voivodeship, regional_teacher_id))
            db.commit()

            new_teacher = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()

            db.execute("""
                UPDATE ref_links 
                SET recipient_id = ?
                WHERE id = ?
            """, (new_teacher["id"], ref_link["id"]))
            db.commit()

            flash("Rejestracja zakończona sukcesem! Możesz się teraz zalogować", "success")
            return redirect(url_for("login"))

        except Exception as e:
            flash(f"Błąd podczas rejestracji: {str(e)}", "error")
            return redirect(url_for("register_teacher_ref", token=token))

    return render_template("register_teacher_ref.html",
                           owner=owner,
                           token=token)


@app.route("/crm/referrals/manage/<int:link_id>", methods=["GET", "POST"])
def manage_referral(link_id):
    # Zezwól regional_teacher, admin i teacher
    if "user_id" not in session or session.get("user_role") not in ["regional_teacher", "admin", "teacher"]:
        flash("Nie masz uprawnień do tej strony", "error")
        return redirect(url_for("index"))

    user_id = session["user_id"]
    db = get_db()

    # Verify the link belongs to current user
    ref_link = db.execute("""
        SELECT r.*, u.username as recipient_name
        FROM ref_links r
        LEFT JOIN users u ON r.recipient_id = u.id
        WHERE r.id = ? AND r.owner_id = ?
    """, (link_id, user_id)).fetchone()

    if not ref_link:
        flash("Nieprawidłowy link", "error")
        return redirect(url_for("crm_referrals"))

    # Calculate completed referral lessons
    completed_referral_lessons = sum([
        ref_link['lesson1_completed'],
        ref_link['lesson2_completed'],
        ref_link['lesson3_completed'],
        ref_link['lesson4_completed'],
        ref_link['lesson5_completed']
    ])

    # In a real app, you might have a different way to get client lessons count
    # For now, we'll use the same as completed_referral_lessons for demonstration
    client_lessons_count = completed_referral_lessons

    if request.method == "POST":
        # Update lesson status
        updates = {}
        for i in range(1, 6):
            completed = request.form.get(f"lesson{i}", "0") == "1"
            updates[f"lesson{i}_completed"] = 1 if completed else 0

        # Check if all lessons are completed
        all_completed = all(updates.values())
        updates["all_completed"] = 1 if all_completed else 0

        # Build update query
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [link_id]

        db.execute(f"""
            UPDATE ref_links 
            SET {set_clause}
            WHERE id = ?
        """, values)
        db.commit()

        flash("Status lekcji został zaktualizowany", "success")
        return redirect(url_for("manage_referral", link_id=link_id))

    return render_template(
        "manage_referral.html",
        link=ref_link,
        completed_referral_lessons=completed_referral_lessons,
        client_lessons_count=client_lessons_count
    )


# Add these routes to app.py

@app.route("/api/crm/generate_referral", methods=["POST"])
def generate_referral():
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher", "admin"]:
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session["user_id"]
    db = get_db()

    try:
        token = secrets.token_urlsafe(16)
        link = url_for('register_teacher_ref', token=token, _external=True)

        db.execute("""
            INSERT INTO ref_links (link, owner_id)
            VALUES (?, ?)
        """, (link, user_id))
        db.commit()

        return jsonify({
            "success": True,
            "message": "Link generated successfully",
            "link": link
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/crm/referral_links", methods=["GET"])
def get_referral_links():
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher", "admin"]:
        return jsonify({"error": "Unauthorized"}), 403

    user_id = session["user_id"]
    db = get_db()

    try:
        links = db.execute("""
            SELECT r.*, u.username as recipient_name
            FROM ref_links r
            LEFT JOIN users u ON r.recipient_id = u.id
            WHERE r.owner_id = ?
            ORDER BY r.created_at DESC
        """, (user_id,)).fetchall()

        links_data = []
        for link in links:
            link_data = dict(link)
            link_data["manage_url"] = url_for('manage_referral', link_id=link["id"])
            links_data.append(link_data)

        return jsonify(links_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/add_review", methods=["POST"])
def add_review():
    if "user_id" not in session:
        return jsonify({"error": "Musisz być zalogowany"}), 401

    data = request.get_json()
    teacher_id = data.get("teacher_id")
    content = data.get("content")
    rating = data.get("rating")

    if not all([teacher_id, content, rating]):
        return jsonify({"error": "Wypełnij wszystkie pola"}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            return jsonify({"error": "Ocena musi być od 1 do 5"}), 400
    except ValueError:
        return jsonify({"error": "Nieprawidłowa ocena"}), 400

    student_id = session["user_id"]
    db = get_db()

    # Sprawdzamy tylko czy użytkownik już nie dodał opinii
    existing_review = db.execute("""
        SELECT id FROM reviews 
        WHERE teacher_id = ? AND student_id = ?
    """, (teacher_id, student_id)).fetchone()

    if existing_review:
        return jsonify({"error": "Możesz dodać tylko jedną opinię na nauczyciela"}), 403

    try:
        db.execute("""
            INSERT INTO reviews (teacher_id, student_id, content, rating)
            VALUES (?, ?, ?, ?)
        """, (teacher_id, student_id, content, rating))
        db.commit()
        return jsonify({"success": True, "message": "Dziękujemy za opinię!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/get_reviews/<int:teacher_id>", methods=["GET"])
def get_reviews(teacher_id):
    db = get_db()
    reviews = db.execute("""
        SELECT r.*, u.username as student_name
        FROM reviews r
        JOIN users u ON r.student_id = u.id
        WHERE r.teacher_id = ?
        ORDER BY r.created_at DESC
    """, (teacher_id,)).fetchall()
    return jsonify(rows_to_dict_list(reviews))


@app.route("/api/can_review", methods=["GET"])
def can_review():
    if "user_id" not in session:
        return jsonify({"can_review": False})

    student_id = session["user_id"]
    teacher_id = request.args.get("teacher_id")

    if not teacher_id:
        return jsonify({"can_review": False})

    try:
        teacher_id = int(teacher_id)
    except ValueError:
        return jsonify({"can_review": False})

    db = get_db()

    # Sprawdzamy tylko czy użytkownik już nie dodał opinii
    has_review = db.execute("""
        SELECT id FROM reviews 
        WHERE teacher_id = ? AND student_id = ?
        LIMIT 1
    """, (teacher_id, student_id)).fetchone()

    can_review = has_review is None
    return jsonify({"can_review": can_review})


@app.template_filter('format_date')
def format_date(value):
    if value is None:
        return "Nieznana"
    try:
        dt = datetime.strptime(value, '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except:
        return value


@app.route("/api/balance", methods=["GET"])
def get_user_balance():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    user_id = session["user_id"]
    return jsonify({"balance": get_balance(user_id)})


@app.route("/api/deposit", methods=["POST"])
def deposit():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    amount = data.get('amount')

    if not amount or amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    user_id = session["user_id"]
    db = get_db()

    try:
        db.execute("""
            UPDATE user_balances 
            SET balance = balance + ? 
            WHERE user_id = ?
        """, (amount, user_id))
        db.commit()
        return jsonify({"success": True, "new_balance": get_balance(user_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/withdraw", methods=["POST"])
def withdraw():
    if "user_id" not in session or session.get("user_role") not in ["teacher", "regional_teacher"]:
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json()
    amount = data.get('amount')
    user_id = session["user_id"]

    if not amount or amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400

    db = get_db()
    current_balance = get_balance(user_id)

    if current_balance < amount:
        return jsonify({"error": "Insufficient funds"}), 400

    try:
        db.execute("""
            UPDATE user_balances 
            SET balance = balance - ? 
            WHERE user_id = ?
        """, (amount, user_id))
        db.commit()
        return jsonify({"success": True, "new_balance": get_balance(user_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def process_booking_payment(booking_id, student_id, teacher_id, amount, lesson_mode):
    db = get_db()

    try:
        # Sprawdź saldo ucznia
        student_balance = get_balance(student_id)
        if student_balance < amount:
            return False, "Insufficient funds"

        # Pobierz cenę lekcji
        pricing = db.execute("""
            SELECT price_online, price_in_person 
            FROM teacher_pricing 
            WHERE teacher_id = ?
        """, (teacher_id,)).fetchone()

        if not pricing:
            pricing = {"price_online": 80.0, "price_in_person": 100.0}

        price = pricing['price_online'] if lesson_mode == 'online' else pricing['price_in_person']

        # Potrąć środki z konta ucznia
        db.execute("""
            UPDATE user_balances 
            SET balance = balance - ? 
            WHERE user_id = ?
        """, (price, student_id))

        # Zapisz kwotę w rezerwacji
        db.execute("""
            UPDATE bookings 
            SET amount = ?
            WHERE id = ?
        """, (price, booking_id))

        return True, ""
    except Exception as e:
        return False, str(e)


@app.route("/api/update_lesson_payment", methods=["POST"])
def update_lesson_payment():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    booking_id = data.get("booking_id")
    status = data.get("status")

    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()

    if not booking:
        return jsonify({"error": "Booking not found"}), 404

    if booking["amount"] is None or booking["amount"] <= 0:
        return jsonify({"success": True, "message": "No payment to process"})

    try:
        # Jeśli lekcja została odwołana, zwróć środki
        if status in ["cancelled", "odwolana"]:
            db.execute("""
                UPDATE user_balances 
                SET balance = balance + ? 
                WHERE user_id = ?
            """, (booking["amount"], booking["student_id"]))

        # Jeśli lekcja została zakończona, przelicz prowizję
        elif status in ["completed", "przeprowadzona"]:
            # 85% dla nauczyciela, 15% prowizji systemowej
            teacher_share = booking["amount"] * 0.85
            db.execute("""
                UPDATE user_balances 
                SET balance = balance + ? 
                WHERE user_id = ?
            """, (teacher_share, booking["teacher_id"]))

        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_balance(user_id):
    db = get_db()
    balance_row = db.execute("SELECT balance FROM user_balances WHERE user_id = ?", (user_id,)).fetchone()
    return balance_row["balance"] if balance_row else 0.0


@app.route("/add_balance", methods=["GET", "POST"])
def add_balance():
    if "user_id" not in session:
        flash("Musisz być zalogowany", "error")
        return redirect(url_for("login"))

    user_id = session["user_id"]
    balance = get_balance(user_id)

    if request.method == "POST":
        amount = request.form.get("amount")
        try:
            amount = float(amount)
            if amount <= 0:
                flash("Kwota musi być dodatnia", "error")
                return redirect(url_for("add_balance"))

            db = get_db()
            db.execute("""
                UPDATE user_balances 
                SET balance = balance + ? 
                WHERE user_id = ?
            """, (amount, user_id))
            db.commit()
            flash(f"Doładowano konto o {amount:.2f} zł", "success")
            return redirect(url_for("add_balance"))
        except ValueError:
            flash("Nieprawidłowa kwota", "error")
            return redirect(url_for("add_balance"))

    return render_template("add_balance.html", balance=balance)

if __name__ == "__main__":
    init_db()
    # migrate_db()
    app.run(debug=True)

# Michał Jaksan autor aplikacji. Wszelkie prawa zastrzeżone :).