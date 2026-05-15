cat > actualizar_mathmentor.py <<'PY'
from pathlib import Path
import textwrap

ROOT = Path.cwd()

def wf(path, content):
    file_path = ROOT / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")

# ============================================================
# REQUIREMENTS
# ============================================================

wf("requirements.txt", r'''
fastapi
uvicorn
pydantic
python-multipart
python-dotenv
openai
PyPDF2
python-docx
''')

wf(".env.example", r'''
OPENAI_API_KEY=tu_api_key_aqui
DATABASE_URL=tutormath.db
''')

for path in [
    "backend/__init__.py",
    "backend/database/__init__.py",
    "backend/routes/__init__.py",
    "backend/services/__init__.py",
    "backend/model/__init__.py",
]:
    wf(path, "")

# ============================================================
# DATABASE
# ============================================================

wf("backend/database/db.py", r'''
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "tutormath.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]


def add_column_if_missing(cursor, table, column, definition):
    if not column_exists(cursor, table, column):
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diagnostics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        academic_level TEXT,
        area TEXT,
        topic TEXT,
        score REAL,
        total REAL,
        mastery REAL,
        risk_level TEXT,
        detected_errors TEXT,
        weak_subtopics TEXT,
        weekly_hours REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kpis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        topic TEXT,
        area TEXT,
        initial_mastery REAL,
        current_mastery REAL,
        target_mastery REAL,
        weekly_hours REAL,
        estimated_weeks INTEGER,
        risk_level TEXT,
        status TEXT,
        pending_topics TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        mode TEXT,
        topic TEXT,
        question TEXT,
        answer TEXT,
        affects_kpi INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teacher_materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        filename TEXT,
        content_type TEXT,
        extracted_text TEXT,
        summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Compatibilidad si ya existían tablas antiguas
    add_column_if_missing(cursor, "diagnostics", "total", "REAL")
    add_column_if_missing(cursor, "diagnostics", "weak_subtopics", "TEXT")
    add_column_if_missing(cursor, "kpis", "area", "TEXT")
    add_column_if_missing(cursor, "kpis", "risk_level", "TEXT")
    add_column_if_missing(cursor, "kpis", "pending_topics", "TEXT")

    conn.commit()
    conn.close()
''')

# ============================================================
# AI SERVICE
# ============================================================

wf("backend/services/ai_service.py", r'''
import os
import json

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


def generate_ai_response(system_prompt: str, user_prompt: str):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key or OpenAI is None:
        return None

    try:
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
        )

        return response.choices[0].message.content

    except Exception:
        return None


def generate_ai_json(system_prompt: str, user_prompt: str):
    raw = generate_ai_response(system_prompt, user_prompt)

    if not raw:
        return None

    try:
        clean = raw.strip()

        if clean.startswith("```json"):
            clean = clean.replace("```json", "").replace("```", "").strip()
        elif clean.startswith("```"):
            clean = clean.replace("```", "").strip()

        return json.loads(clean)

    except Exception:
        return None
''')

# ============================================================
# AUTH
# ============================================================

wf("backend/services/auth_service.py", r'''
from database.db import get_connection


def register_user(name: str, email: str, password: str):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, password),
        )
        conn.commit()
        user_id = cursor.lastrowid

        return {
            "success": True,
            "message": "Usuario registrado correctamente.",
            "user": {"id": user_id, "name": name, "email": email},
        }

    except Exception:
        return {
            "success": False,
            "message": "El correo ya está registrado.",
        }

    finally:
        conn.close()


def login_user(email: str, password: str):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, email, password FROM users WHERE email = ?",
        (email,),
    )

    user = cursor.fetchone()
    conn.close()

    if not user:
        return {"success": False, "message": "Usuario no encontrado."}

    if user["password"] != password:
        return {"success": False, "message": "Contraseña incorrecta."}

    return {
        "success": True,
        "message": "Inicio de sesión exitoso.",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
        },
    }
''')

wf("backend/routes/auth_routes.py", r'''
from fastapi import APIRouter
from pydantic import BaseModel
from services.auth_service import register_user, login_user

router = APIRouter()


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
def register(data: RegisterRequest):
    return register_user(data.name, data.email, data.password)


@router.post("/login")
def login(data: LoginRequest):
    return login_user(data.email, data.password)
''')

# ============================================================
# DIAGNOSTIC
# ============================================================

wf("backend/services/diagnostic_service.py", r'''
from database.db import get_connection
from services.ai_service import generate_ai_json


SUBTOPICS_BY_AREA = {
    "Bases matemáticas": [
        "Todos",
        "Álgebra",
        "Factorización",
        "Sistemas de ecuaciones",
        "Funciones",
        "Trigonometría",
    ],
    "Cálculo diferencial": [
        "Todos",
        "Límites",
        "Continuidad",
        "Derivadas",
        "Regla de la cadena",
        "Optimización",
    ],
    "Cálculo integral": [
        "Todos",
        "Integrales directas",
        "Sustitución",
        "Integración por partes",
        "Fracciones parciales",
        "Volúmenes de revolución",
    ],
    "Cálculo multivariable": [
        "Todos",
        "Funciones de varias variables",
        "Derivadas parciales",
        "Gradiente",
        "Plano tangente",
        "Integrales dobles",
        "Integrales triples",
    ],
    "Cálculo vectorial": [
        "Todos",
        "Campos vectoriales",
        "Integrales de línea",
        "Integrales de superficie",
        "Teorema de Green",
        "Teorema de Gauss",
        "Teorema de Stokes",
    ],
    "Ecuaciones diferenciales": [
        "Todos",
        "EDO separables",
        "EDO lineales de primer orden",
        "Factor integrante",
        "EDO de segundo orden",
        "Modelos aplicados",
    ],
}


def normalize_hours(weekly_hours: float):
    if weekly_hours < 1:
        return 1
    if weekly_hours > 40:
        return 40
    return weekly_hours


def difficulty_profile(academic_level: str):
    if "Nivelación" in academic_level:
        return "básica y media"
    if "Segundo" in academic_level:
        return "media y avanzada"
    return "básica, media y algunas avanzadas"


def calculate_time_minutes(academic_level: str, questions: list):
    advanced_count = sum(
        1
        for q in questions
        if q.get("difficulty") == "avanzada" or q.get("requires_upload")
    )

    if "Nivelación" in academic_level:
        base = 10 if len(questions) <= 5 else 15
    elif "Segundo" in academic_level:
        base = 20 if len(questions) <= 5 else 30
    else:
        base = 15 if len(questions) <= 5 else 20

    if advanced_count > 0:
        base += 5

    return base


def fallback_questions(area: str, topic: str, academic_level: str):
    selected_topic = topic if topic != "Todos" else area

    questions = [
        {
            "id": 1,
            "question": f"Identifique el concepto principal asociado a {selected_topic}.",
            "options": [
                "Concepto correcto",
                "Concepto no relacionado",
                "Procedimiento inverso",
                "Ninguna de las anteriores",
            ],
            "correct": "Concepto correcto",
            "difficulty": "basica",
            "skill": "Concepto base",
            "weight": 1,
            "requires_upload": False,
        },
        {
            "id": 2,
            "question": f"Seleccione el método más adecuado para resolver un ejercicio típico de {selected_topic}.",
            "options": [
                "Método adecuado",
                "Método no aplicable",
                "Ensayo aleatorio",
                "No se puede resolver",
            ],
            "correct": "Método adecuado",
            "difficulty": "media",
            "skill": "Selección de método",
            "weight": 2,
            "requires_upload": False,
        },
        {
            "id": 3,
            "question": f"Determine cuál afirmación sobre {selected_topic} es correcta.",
            "options": [
                "Afirmación correcta",
                "Afirmación incompleta",
                "Afirmación falsa",
                "Afirmación contradictoria",
            ],
            "correct": "Afirmación correcta",
            "difficulty": "media",
            "skill": "Interpretación conceptual",
            "weight": 2,
            "requires_upload": False,
        },
        {
            "id": 4,
            "question": f"Resuelva un ejercicio aplicado de {selected_topic} y seleccione la alternativa correcta.",
            "options": [
                "Resultado correcto",
                "Resultado con error de signo",
                "Resultado incompleto",
                "Resultado fuera de contexto",
            ],
            "correct": "Resultado correcto",
            "difficulty": "media",
            "skill": "Aplicación",
            "weight": 2,
            "requires_upload": False,
        },
        {
            "id": 5,
            "question": f"Desarrolle un procedimiento de mayor dificultad relacionado con {selected_topic}.",
            "options": [
                "Procedimiento correcto",
                "Error de método",
                "Error algebraico",
                "No corresponde",
            ],
            "correct": "Procedimiento correcto",
            "difficulty": "avanzada",
            "skill": "Desarrollo avanzado",
            "weight": 3,
            "requires_upload": True,
        },
    ]

    return questions


def generate_ai_test(data):
    weekly_hours = normalize_hours(data.weekly_hours)

    system_prompt = (
        "Eres un generador experto de diagnósticos matemáticos para estudiantes "
        "de ingeniería hasta segundo año. Devuelve solo JSON válido."
    )

    user_prompt = f"""
Crea un test diagnóstico de mínimo 5 preguntas.

Nivel académico: {data.academic_level}
Área matemática: {data.area}
Tema o subtema: {data.topic}
Perfil de dificultad: {difficulty_profile(data.academic_level)}

Reglas:
- Mínimo 5 preguntas.
- Alternativas A, B, C y D.
- Debe incluir preguntas según la dificultad del nivel.
- Una pregunta avanzada puede requerir desarrollo.
- Cada pregunta debe tener:
  id, question, options, correct, difficulty, skill, weight, requires_upload.
- correct debe ser exactamente una de las opciones.
- difficulty debe ser: basica, media o avanzada.
- weight: 1 básica, 2 media, 3 avanzada.

Devuelve:
{{
  "topic": "{data.topic}",
  "questions": []
}}
"""

    ai_result = generate_ai_json(system_prompt, user_prompt)

    if ai_result and isinstance(ai_result.get("questions"), list) and len(ai_result["questions"]) >= 5:
        questions = ai_result["questions"]

        for index, question in enumerate(questions, start=1):
            question["id"] = index
            question.setdefault("weight", 1)
            question.setdefault("requires_upload", False)
            question.setdefault("skill", "Habilidad matemática")
            question.setdefault("difficulty", "media")

        return {
            "topic": data.topic,
            "area": data.area,
            "academic_level": data.academic_level,
            "weekly_hours": weekly_hours,
            "time_minutes": calculate_time_minutes(data.academic_level, questions),
            "questions": questions,
        }

    questions = fallback_questions(data.area, data.topic, data.academic_level)

    return {
        "topic": data.topic,
        "area": data.area,
        "academic_level": data.academic_level,
        "weekly_hours": weekly_hours,
        "time_minutes": calculate_time_minutes(data.academic_level, questions),
        "questions": questions,
    }


def calculate_risk(mastery: float):
    if mastery < 40:
        return "Alto riesgo"
    if mastery < 70:
        return "Riesgo medio"
    if mastery < 90:
        return "Buen avance"
    return "Meta avanzada"


def recommend_goal(mastery: float):
    if mastery < 40:
        return 65
    if mastery < 60:
        return 75
    if mastery < 75:
        return 85
    return 92


def estimate_weeks(current_mastery: float, target_mastery: float, weekly_hours: float, area: str):
    weekly_hours = normalize_hours(weekly_hours)

    difficulty_factor = {
        "Bases matemáticas": 1.0,
        "Cálculo diferencial": 1.2,
        "Cálculo integral": 1.4,
        "Cálculo multivariable": 1.7,
        "Cálculo vectorial": 1.8,
        "Ecuaciones diferenciales": 1.9,
    }.get(area, 1.3)

    gap = max(target_mastery - current_mastery, 1)
    weekly_progress = max(weekly_hours * 2.2 / difficulty_factor, 1)
    weeks = round(gap / weekly_progress)

    return max(1, weeks)


def evaluate_diagnostic(data):
    total = 0
    score = 0
    wrong_skills = []
    weak_subtopics = []

    for question in data.questions:
        qid = str(question.get("id"))
        correct = question.get("correct")
        user_answer = data.answers.get(qid)
        weight = float(question.get("weight", 1))
        skill = question.get("skill", "Habilidad matemática")

        total += weight

        if user_answer == correct:
            score += weight
        else:
            wrong_skills.append(skill)
            weak_subtopics.append(skill)

    mastery = round((score / total) * 100, 1) if total else 0
    risk = calculate_risk(mastery)
    target = recommend_goal(mastery)
    weekly_hours = normalize_hours(data.weekly_hours)
    weeks = estimate_weeks(mastery, target, weekly_hours, data.area)

    detected_errors = list(dict.fromkeys(wrong_skills)) or ["Sin errores relevantes detectados"]
    weak_subtopics = list(dict.fromkeys(weak_subtopics)) or ["Sin subtemas débiles detectados"]

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO diagnostics
        (user_id, academic_level, area, topic, score, total, mastery, risk_level,
         detected_errors, weak_subtopics, weekly_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.user_id,
            data.academic_level,
            data.area,
            data.topic,
            score,
            total,
            mastery,
            risk,
            ", ".join(detected_errors),
            ", ".join(weak_subtopics),
            weekly_hours,
        ),
    )

    conn.commit()
    diagnostic_id = cursor.lastrowid
    conn.close()

    return {
        "diagnostic_id": diagnostic_id,
        "score": score,
        "total": total,
        "mastery": mastery,
        "risk_level": risk,
        "detected_errors": detected_errors,
        "weak_subtopics": weak_subtopics,
        "recommended_goal": target,
        "estimated_weeks": weeks,
        "weekly_hours": weekly_hours,
        "recommendation": (
            f"Tu dominio actual es {mastery}%. "
            f"Se recomienda una meta de {target}% en aproximadamente {weeks} semanas, "
            f"estudiando {weekly_hours} horas semanales."
        ),
    }


def create_kpi(data):
    current = max(0, min(data.initial_mastery, 100))
    target = max(0, min(data.target_mastery, 100))
    weekly = normalize_hours(data.weekly_hours)
    risk = calculate_risk(current)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO kpis
        (user_id, topic, area, initial_mastery, current_mastery, target_mastery,
         weekly_hours, estimated_weeks, risk_level, status, pending_topics)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.user_id,
            data.topic,
            data.area,
            current,
            current,
            target,
            weekly,
            data.estimated_weeks,
            risk,
            "En progreso",
            "",
        ),
    )

    conn.commit()
    kpi_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "message": "KPI creado correctamente.",
        "kpi_id": kpi_id,
    }
''')

wf("backend/routes/diagnostic_routes.py", r'''
from fastapi import APIRouter
from pydantic import BaseModel
from services.diagnostic_service import (
    SUBTOPICS_BY_AREA,
    generate_ai_test,
    evaluate_diagnostic,
    create_kpi,
)

router = APIRouter()


class GenerateAITestRequest(BaseModel):
    user_id: int
    academic_level: str
    area: str
    topic: str
    weekly_hours: float


class SubmitDiagnosticRequest(BaseModel):
    user_id: int
    academic_level: str
    area: str
    topic: str
    weekly_hours: float
    questions: list
    answers: dict


class CreateKPIRequest(BaseModel):
    user_id: int
    area: str
    topic: str
    initial_mastery: float
    target_mastery: float
    weekly_hours: float
    estimated_weeks: int


@router.get("/subtopics")
def subtopics():
    return SUBTOPICS_BY_AREA


@router.post("/generate-ai-test")
def generate_test(data: GenerateAITestRequest):
    return generate_ai_test(data)


@router.post("/submit")
def submit(data: SubmitDiagnosticRequest):
    return evaluate_diagnostic(data)


@router.post("/create-kpi")
def create(data: CreateKPIRequest):
    return create_kpi(data)
''')

# ============================================================
# CHATBOT
# ============================================================

wf("backend/services/chatbot_service.py", r'''
from database.db import get_connection
from services.ai_service import generate_ai_response


def fallback_math_response(message: str):
    return f"""
Vamos a trabajarlo como tutor matemático.

1. Primero identificamos el tipo de problema.
Qué se hace: se revisa el enunciado y se determina el tema matemático involucrado.
Por qué se hace: si no identificamos el tipo de problema, podemos elegir un método incorrecto.

2. Luego seleccionamos el método.
Qué se hace: se elige una regla, fórmula o procedimiento adecuado.
Por qué se hace: en matemática, cada procedimiento depende de las condiciones del ejercicio.

3. Después desarrollamos paso a paso.
Qué se hace: se aplican operaciones ordenadas, cuidando signos y simplificaciones.
Por qué se hace: el orden evita errores y permite comprobar el resultado.

4. Finalmente verificamos.
Qué se hace: revisamos si el resultado tiene sentido y si cumple el enunciado.
Por qué se hace: muchos errores se detectan al comprobar.

Tu consulta fue:
{message}

Puedo ayudarte mejor si me escribes el ejercicio completo o subes tu desarrollo.
"""


def generate_chatbot_response(user_id: int, message: str, topic: str = "", mode: str = "libre"):
    system_prompt = """
Eres Mathmentor IA, un tutor experto en matemáticas universitarias para estudiantes de ingeniería hasta segundo año.
No entregues solo tips.
Debes resolver, explicar y enseñar paso a paso.
Siempre que corresponda, indica:
- qué se está haciendo;
- por qué se hace;
- fórmula usada;
- ejemplo cotidiano si ayuda;
- ejercicio similar para practicar.
Puedes corregir procedimientos y generar ejercicios.
El aprendizaje libre no debe afectar KPIs.
"""

    ai_answer = generate_ai_response(system_prompt, message)
    answer = ai_answer if ai_answer else fallback_math_response(message)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO learning_history (user_id, mode, topic, question, answer, affects_kpi)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, mode, topic, message, answer, 0),
    )

    conn.commit()
    conn.close()

    return {
        "message": message,
        "response": answer,
        "affects_kpi": False,
    }
''')

wf("backend/routes/chatbot_routes.py", r'''
from fastapi import APIRouter
from pydantic import BaseModel
from services.chatbot_service import generate_chatbot_response

router = APIRouter()


class ChatbotRequest(BaseModel):
    user_id: int = 1
    message: str
    topic: str | None = ""
    mode: str | None = "libre"


@router.post("/")
def chatbot(data: ChatbotRequest):
    return generate_chatbot_response(
        data.user_id,
        data.message,
        data.topic or "",
        data.mode or "libre",
    )
''')

# ============================================================
# LEARNING
# ============================================================

wf("backend/services/learning_service.py", r'''
from database.db import get_connection
from services.ai_service import generate_ai_json


def clamp_percent(value: float):
    return max(0, min(value, 100))


def fallback_plan(area: str, topic: str, mastery: float, target: float):
    modules = [
        "Conceptos base",
        "Métodos principales",
        "Ejemplo desarrollado",
        "Ejercicios de práctica",
        "Evaluación del tema",
    ]

    return {
        "area": area,
        "topic": topic,
        "current_mastery": mastery,
        "target_mastery": target,
        "modules": [
            {
                "title": module,
                "objective": f"Dominar {module.lower()} en {topic}.",
                "theory": f"Este módulo trabaja {module.lower()} relacionado con {topic}.",
                "formulas": ["Fórmulas según el tema trabajado."],
                "daily_example": "Ejemplo cotidiano aplicado al contexto del estudiante.",
                "developed_example": [
                    {
                        "step": 1,
                        "what": "Identificar el tipo de ejercicio.",
                        "why": "Permite elegir el método correcto.",
                    },
                    {
                        "step": 2,
                        "what": "Aplicar el procedimiento correspondiente.",
                        "why": "Se usa porque responde a la estructura del problema.",
                    },
                    {
                        "step": 3,
                        "what": "Comprobar el resultado.",
                        "why": "Ayuda a detectar errores de cálculo o interpretación.",
                    },
                ],
                "practice": [
                    f"Ejercicio 1 de {topic}",
                    f"Ejercicio 2 de {topic}",
                    f"Ejercicio 3 de {topic}",
                ],
                "evaluation": "Mini evaluación para avanzar.",
            }
            for module in modules
        ],
    }


def generate_guided_plan(data):
    mastery = clamp_percent(data.current_mastery)
    target = clamp_percent(data.target_mastery)

    system_prompt = (
        "Eres un tutor matemático experto para estudiantes de ingeniería hasta segundo año. "
        "Genera rutas de estudio personalizadas en JSON válido."
    )

    user_prompt = f"""
Crea una ruta guiada de aprendizaje.

Área: {data.area}
Tema: {data.topic}
Nivel académico: {data.academic_level}
Dominio actual: {mastery}
Meta: {target}

Cada módulo debe tener:
title, objective, theory, formulas, daily_example, developed_example, practice, evaluation.

developed_example debe ser una lista de pasos con:
step, what, why.

Devuelve:
{{
  "area": "{data.area}",
  "topic": "{data.topic}",
  "current_mastery": {mastery},
  "target_mastery": {target},
  "modules": []
}}
"""

    ai_plan = generate_ai_json(system_prompt, user_prompt)

    if ai_plan and isinstance(ai_plan.get("modules"), list):
        return ai_plan

    return fallback_plan(data.area, data.topic, mastery, target)


def evaluate_topic(user_id: int, topic: str, subtopic: str, score: float, kpi_id=None):
    approved = score >= 75

    conn = get_connection()
    cursor = conn.cursor()

    if kpi_id:
        if approved:
            cursor.execute(
                "UPDATE kpis SET current_mastery = MIN(current_mastery + 8, target_mastery) WHERE id = ?",
                (kpi_id,),
            )
        else:
            cursor.execute("SELECT pending_topics FROM kpis WHERE id = ?", (kpi_id,))
            row = cursor.fetchone()
            previous = row["pending_topics"] if row and row["pending_topics"] else ""
            updated = previous + f"{subtopic}; "
            cursor.execute(
                "UPDATE kpis SET pending_topics = ?, status = ? WHERE id = ?",
                (updated, "Con temas pendientes", kpi_id),
            )

    conn.commit()
    conn.close()

    return {
        "approved": approved,
        "score": score,
        "message": (
            "Tema dominado. Puedes avanzar."
            if approved
            else "Tema pendiente. Puedes repasar o avanzar, pero quedará marcado."
        ),
    }


def get_history(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT mode, topic, question, answer, affects_kpi, created_at
        FROM learning_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return rows
''')

wf("backend/routes/learning_routes.py", r'''
from fastapi import APIRouter
from pydantic import BaseModel
from services.learning_service import generate_guided_plan, evaluate_topic, get_history

router = APIRouter()


class PlanRequest(BaseModel):
    academic_level: str
    area: str
    topic: str
    current_mastery: float
    target_mastery: float


class EvaluationRequest(BaseModel):
    user_id: int
    topic: str
    subtopic: str
    score: float
    kpi_id: int | None = None


@router.post("/plan")
def plan(data: PlanRequest):
    return generate_guided_plan(data)


@router.post("/evaluate")
def evaluate(data: EvaluationRequest):
    return evaluate_topic(data.user_id, data.topic, data.subtopic, data.score, data.kpi_id)


@router.get("/history/{user_id}")
def history(user_id: int):
    return get_history(user_id)
''')

# ============================================================
# TEACHER MODE
# ============================================================

wf("backend/services/teacher_mode_service.py", r'''
from database.db import get_connection
from services.ai_service import generate_ai_json

try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import docx
except Exception:
    docx = None


async def extract_text(file):
    filename = file.filename.lower()
    content = await file.read()

    if filename.endswith(".txt") or filename.endswith(".csv"):
        return content.decode("utf-8", errors="ignore")

    if filename.endswith(".pdf") and PyPDF2:
        import io
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text

    if filename.endswith(".docx") and docx:
        import io
        document = docx.Document(io.BytesIO(content))
        return "\\n".join([p.text for p in document.paragraphs])

    return ""


def fallback_analysis(text: str):
    lower = text.lower()
    topics = []

    if "derivada" in lower:
        topics.append("Cálculo diferencial")
    if "integral" in lower:
        topics.append("Cálculo integral")
    if "gradiente" in lower or "parcial" in lower:
        topics.append("Cálculo multivariable")
    if "ecuación diferencial" in lower or "edo" in lower:
        topics.append("Ecuaciones diferenciales")

    if not topics:
        topics = ["Contenido matemático general"]

    return {
        "summary": "Material analizado localmente. Se identificaron temas y posible estilo de resolución.",
        "topics": topics,
        "subtopics": [],
        "teacher_style": "Desarrollo paso a paso con énfasis en ejercicios.",
        "difficulty": "media",
        "exercise_types": ["cálculo", "desarrollo", "aplicación"],
        "preferred_methods": ["procedimiento ordenado", "verificación del resultado"],
        "recommendations": ["Practicar ejercicios similares", "Crear simulacro de mayor dificultad"],
    }


async def upload_multiple_materials(user_id: int, files):
    combined_text = ""
    saved_files = []

    conn = get_connection()
    cursor = conn.cursor()

    for file in files:
        text = await extract_text(file)
        combined_text += "\\n\\n" + text
        saved_files.append(file.filename)

        cursor.execute(
            """
            INSERT INTO teacher_materials (user_id, filename, content_type, extracted_text, summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, file.filename, file.content_type, text[:4000], "Material subido"),
        )

    conn.commit()
    conn.close()

    system_prompt = (
        "Eres un analista de material docente de matemáticas para ingeniería. "
        "Analiza el material y devuelve JSON válido."
    )

    user_prompt = f"""
Analiza el siguiente material de clases:

{combined_text[:12000]}

Devuelve JSON:
{{
  "summary": "",
  "topics": [],
  "subtopics": [],
  "teacher_style": "",
  "difficulty": "",
  "exercise_types": [],
  "preferred_methods": [],
  "recommendations": []
}}
"""

    analysis = generate_ai_json(system_prompt, user_prompt) or fallback_analysis(combined_text)

    return {
        "success": True,
        "files": saved_files,
        "analysis": analysis,
        "combined_text_preview": combined_text[:1200],
    }


def generate_exercises_from_material(topic: str, difficulty: str, quantity: int):
    exercises = []

    for i in range(1, quantity + 1):
        exercises.append(
            {
                "number": i,
                "statement": f"Ejercicio {i} de {topic} con dificultad {difficulty}.",
                "difficulty": difficulty,
                "skill": "Aplicación del método del profesor",
                "suggested_method": "Resolver paso a paso según el material subido.",
                "solution_available": True,
            }
        )

    return {
        "topic": topic,
        "difficulty": difficulty,
        "quantity": quantity,
        "exercises": exercises,
    }


def generate_mock_test(topic: str, difficulty: str, quantity: int, duration: int):
    return {
        "topic": topic,
        "difficulty": "mayor a ejercicios similares",
        "duration_minutes": duration,
        "instructions": "Simulacro de mayor exigencia. Incluye preguntas conceptuales, cálculo y desarrollo.",
        "criteria": [
            "Desarrollo ordenado",
            "Justificación del método",
            "Resultado correcto",
            "Interpretación",
        ],
        "questions": [
            {
                "number": i,
                "statement": f"Pregunta {i} de simulacro avanzado sobre {topic}.",
                "points": 5 if i == quantity else 3,
                "type": "desarrollo" if i == quantity else "mixta",
            }
            for i in range(1, quantity + 1)
        ],
    }
''')

wf("backend/routes/teacher_mode_routes.py", r'''
from fastapi import APIRouter, UploadFile, File, Form
from services.teacher_mode_service import (
    upload_multiple_materials,
    generate_exercises_from_material,
    generate_mock_test,
)

router = APIRouter()


@router.post("/upload")
async def upload(
    user_id: int = Form(1),
    files: list[UploadFile] = File(...),
):
    return await upload_multiple_materials(user_id, files)


@router.get("/exercises")
def exercises(topic: str, difficulty: str = "media", quantity: int = 5):
    return generate_exercises_from_material(topic, difficulty, quantity)


@router.get("/mock-test")
def mock_test(topic: str, difficulty: str = "avanzada", quantity: int = 6, duration: int = 45):
    return generate_mock_test(topic, difficulty, quantity, duration)
''')

# ============================================================
# ANALYTICS
# ============================================================

wf("backend/services/analytics_service.py", r'''
from database.db import get_connection


def get_dashboard(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM kpis WHERE user_id = ?", (user_id,))
    total = cursor.fetchone()["total"]

    cursor.execute("SELECT AVG(current_mastery) as avg FROM kpis WHERE user_id = ?", (user_id,))
    avg = cursor.fetchone()["avg"] or 0

    cursor.execute(
        "SELECT topic, current_mastery FROM kpis WHERE user_id = ? ORDER BY current_mastery ASC LIMIT 1",
        (user_id,),
    )
    weakest = cursor.fetchone()

    cursor.execute(
        "SELECT detected_errors FROM diagnostics WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    )
    error = cursor.fetchone()

    cursor.execute(
        """
        SELECT id, topic, area, initial_mastery, current_mastery, target_mastery,
               weekly_hours, estimated_weeks, risk_level, status, pending_topics
        FROM kpis
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    kpis = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "summary": {
            "active_objectives": total,
            "average_mastery": round(avg, 1),
            "risk": "Alto riesgo" if avg < 40 else "Riesgo medio" if avg < 70 else "Buen avance",
            "weakest_topic": weakest["topic"] if weakest else "Sin datos",
            "most_common_error": error["detected_errors"] if error else "Sin datos",
            "next_action": "Realiza un diagnóstico o continúa tu ruta guiada.",
        },
        "kpis": kpis,
    }


def get_learning_analytics(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT area, topic, mastery, risk_level, detected_errors, weak_subtopics, created_at
        FROM diagnostics
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    diagnostics = [dict(row) for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT mode, topic, question, answer, created_at
        FROM learning_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 30
        """,
        (user_id,),
    )
    history = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return {
        "diagnostics": diagnostics,
        "history": history,
        "message": (
            "Aún no hay suficiente información. Realiza un diagnóstico o crea una ruta guiada."
            if not diagnostics and not history
            else "Analítica generada correctamente."
        ),
    }
''')

wf("backend/routes/analytics_routes.py", r'''
from fastapi import APIRouter
from services.analytics_service import get_dashboard, get_learning_analytics

router = APIRouter()


@router.get("/dashboard/{user_id}")
def dashboard(user_id: int):
    return get_dashboard(user_id)


@router.get("/learning/{user_id}")
def learning(user_id: int):
    return get_learning_analytics(user_id)
''')

# ============================================================
# COACH
# ============================================================

wf("backend/services/coach_service.py", r'''
import random

MESSAGES = [
    "Vas bien. Cada ejercicio resuelto te acerca más a tu meta.",
    "Equivocarse también es parte de aprender matemática.",
    "La constancia pesa más que estudiar solo antes de una prueba.",
    "Respira, revisa el paso anterior y vuelve a intentarlo.",
    "Un error no significa que no sabes; significa que encontraste qué reforzar.",
    "Sigue paso a paso. El orden del procedimiento importa.",
    "Las matemáticas se dominan con práctica constante.",
    "“No te preocupes por tus dificultades en matemáticas. Las mías son mayores.” — Albert Einstein",
    "“Las matemáticas son el alfabeto con el cual Dios ha escrito el universo.” — Galileo Galilei",
    "“La matemática es la reina de las ciencias.” — Carl Friedrich Gauss",
]

POSITIONS = [
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
    "middle-left",
    "middle-right",
]


def get_message(context: str = "general"):
    return {
        "context": context,
        "message": random.choice(MESSAGES),
        "position": random.choice(POSITIONS),
        "avatar": "🤖",
        "name": "Coach Mathmentor",
    }
''')

wf("backend/routes/coach_routes.py", r'''
from fastapi import APIRouter
from services.coach_service import get_message

router = APIRouter()


@router.get("/message")
def message(context: str = "general"):
    return get_message(context)
''')

# ============================================================
# MAIN BACKEND
# ============================================================

wf("backend/main.py", r'''
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database.db import init_db
from routes.auth_routes import router as auth_router
from routes.diagnostic_routes import router as diagnostic_router
from routes.chatbot_routes import router as chatbot_router
from routes.learning_routes import router as learning_router
from routes.teacher_mode_routes import router as teacher_router
from routes.analytics_routes import router as analytics_router
from routes.coach_routes import router as coach_router

app = FastAPI(
    title="Mathmentor IA API",
    description="API para diagnóstico, KPIs, aprendizaje guiado, modo profesor y analítica.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(diagnostic_router, prefix="/api/diagnostic", tags=["Diagnóstico IA"])
app.include_router(chatbot_router, prefix="/api/chatbot", tags=["Aprendizaje Libre"])
app.include_router(learning_router, prefix="/api/learning", tags=["Centro de Aprendizaje"])
app.include_router(teacher_router, prefix="/api/teacher-mode", tags=["Modo Profesor"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analítica"])
app.include_router(coach_router, prefix="/api/coach", tags=["Coach"])


@app.get("/")
def home():
    return {
        "message": "Mathmentor IA API funcionando",
        "version": "2.0.0",
    }
''')

# ============================================================
# FRONTEND FILES
# ============================================================

wf("frontend/js/api.js", r'''
let API_URL = "http://127.0.0.1:8000";

if (window.location.hostname.includes("github.dev")) {
  API_URL = window.location.origin.replace("-5500", "-8000");
}

function getCurrentUserId() {
  const user = JSON.parse(localStorage.getItem("mathmentor_user") || "{}");
  return user.id || 1;
}

function getCurrentUser() {
  return JSON.parse(localStorage.getItem("mathmentor_user") || "{}");
}

console.log("API_URL:", API_URL);
''')

wf("frontend/index.html", r'''
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Mathmentor IA</title>
  <link rel="stylesheet" href="css/styles.css" />
</head>
<body class="landing-body">
  <div class="formula-rain" id="formulaRain"></div>

  <main class="landing">
    <section class="landing-info">
      <p class="eyebrow">IA educativa para matemática universitaria</p>
      <h1>Mathmentor IA</h1>
      <p class="landing-description">
        Plataforma inteligente para diagnosticar, aprender y mejorar tu rendimiento en matemática con apoyo de IA.
      </p>
      <p class="landing-sub">
        Diagnósticos por tema, KPIs personalizados, rutas de estudio, modo profesor y analítica de aprendizaje.
      </p>
    </section>

    <section class="auth-card landing-auth">
      <div class="auth-tabs">
        <button id="loginTab" class="active" onclick="showAuth('login')">Entrar</button>
        <button id="registerTab" onclick="showAuth('register')">Registrarse</button>
      </div>

      <form id="loginForm" class="auth-form">
        <h2>Iniciar sesión</h2>
        <input type="email" id="loginEmail" placeholder="Correo" required />
        <input type="password" id="loginPassword" placeholder="Contraseña" required />
        <button class="btn primary" type="submit">Entrar</button>
      </form>

      <form id="registerForm" class="auth-form hidden">
        <h2>Crear cuenta</h2>
        <input type="text" id="registerName" placeholder="Nombre" required />
        <input type="email" id="registerEmail" placeholder="Correo" required />
        <input type="password" id="registerPassword" placeholder="Contraseña" required />
        <button class="btn primary" type="submit">Registrarme</button>
      </form>

      <p id="authMessage" class="message-text"></p>
    </section>
  </main>

  <script src="js/api.js"></script>
  <script src="js/main.js"></script>
  <script src="js/auth.js"></script>
</body>
</html>
''')

wf("frontend/app.html", r'''
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Mathmentor IA | App</title>
  <link rel="stylesheet" href="css/styles.css" />
</head>
<body class="app-body">
  <aside class="sidebar">
    <div class="sidebar-logo">Mathmentor <span>IA</span></div>
    <p id="sidebarUser" class="sidebar-user">Estudiante</p>

    <nav class="side-nav">
      <button onclick="showSection('dashboard')">Dashboard</button>
      <button onclick="showSection('objetivos')">Mis Objetivos</button>
      <button onclick="showSection('diagnostico')">Diagnóstico IA</button>
      <button onclick="showSection('centro')">Centro de Aprendizaje</button>
      <button onclick="showSection('libre')">Aprendizaje Libre</button>
      <button onclick="showSection('profesor')">Modo Profesor</button>
      <button onclick="showSection('analitica')">Analítica</button>
      <button onclick="showSection('perfil')">Perfil</button>
    </nav>
  </aside>

  <main class="app-main">
    <section id="dashboard" class="app-section active-section">
      <h1>Dashboard</h1>
      <p class="muted">Indicadores de desempeño y KPIs personalizados.</p>
      <div class="dashboard-grid" id="dashboardSummary"></div>
      <div id="kpiList" class="kpi-list"></div>
    </section>

    <section id="objetivos" class="app-section">
      <h1>Mis Objetivos</h1>
      <p class="muted">Crea y revisa tus metas de aprendizaje matemático.</p>
      <div id="objectivesBox" class="panel"></div>
    </section>

    <section id="diagnostico" class="app-section">
      <h1>Diagnóstico IA</h1>

      <div class="panel form-panel">
        <label>Nivel académico</label>
        <select id="academicLevel">
          <option>Nivelación matemática</option>
          <option>Primer año de ingeniería</option>
          <option>Segundo año de ingeniería</option>
        </select>

        <label>Área matemática</label>
        <select id="diagnosticArea" onchange="updateDiagnosticTopics()"></select>

        <label>Tema / Subtema</label>
        <select id="diagnosticTopic"></select>

        <label>Horas de estudio semanales</label>
        <input type="number" id="weeklyHours" min="1" max="40" value="4" />

        <button class="btn primary" onclick="generateDiagnosticTest()">Generar test diagnóstico</button>
      </div>

      <div class="panel hidden" id="testPanel">
        <div class="test-header">
          <h2>Test diagnóstico</h2>
          <span id="timer">00:00</span>
        </div>
        <form id="questionForm"></form>
        <button class="btn primary" onclick="submitDiagnostic()">Enviar diagnóstico</button>
      </div>

      <div class="panel hidden" id="diagnosticResult"></div>
    </section>

    <section id="centro" class="app-section">
      <h1>Centro de Aprendizaje</h1>

      <div class="panel form-panel">
        <label>Nivel académico</label>
        <select id="planLevel">
          <option>Nivelación matemática</option>
          <option>Primer año de ingeniería</option>
          <option>Segundo año de ingeniería</option>
        </select>

        <label>Área</label>
        <select id="planArea" onchange="updatePlanTopics()"></select>

        <label>Tema</label>
        <select id="planTopic"></select>

        <label>Dominio actual (%)</label>
        <input type="number" id="planMastery" min="0" max="100" value="50" />

        <label>Meta (%)</label>
        <input type="number" id="planTarget" min="0" max="100" value="80" />

        <button class="btn primary" onclick="createStudyPlan()">Crear Ruta Guiada IA</button>
      </div>

      <div id="studyPlan" class="plan-output"></div>
    </section>

    <section id="libre" class="app-section">
      <h1>Aprendizaje Libre</h1>
      <p class="muted">Chat matemático con IA. No afecta tus KPIs.</p>

      <div class="quick-actions">
        <button onclick="quickPrompt('Explícame este ejercicio paso a paso')">Explícame paso a paso</button>
        <button onclick="quickPrompt('Dame un ejercicio similar')">Dame un ejercicio similar</button>
        <button onclick="quickPrompt('Revísame mi desarrollo')">Revísame mi desarrollo</button>
        <button onclick="quickPrompt('Explícame por qué se hace este paso')">Explícame por qué</button>
      </div>

      <div class="chat-container">
        <div id="chatMessages" class="chat-messages">
          <div class="bot-message">
            Hola, soy Mathmentor IA. Puedo resolver, explicar, generar ejercicios y revisar procedimientos.
          </div>
        </div>
        <div class="chat-input">
          <textarea id="chatInput" placeholder="Escribe tu duda o ejercicio..."></textarea>
          <button class="btn primary" onclick="sendChatMessage()">Enviar</button>
        </div>
      </div>
    </section>

    <section id="profesor" class="app-section">
      <h1>Modo Profesor</h1>

      <div class="panel form-panel">
        <label>Subir materiales del profesor</label>
        <input type="file" id="teacherFiles" multiple />

        <button class="btn primary" onclick="uploadTeacherMaterial()">Analizar materiales</button>
        <div id="teacherResult"></div>
      </div>

      <div class="panel form-panel">
        <label>Tema central</label>
        <input type="text" id="teacherTopic" placeholder="Ej: Integración por partes" />

        <label>Dificultad</label>
        <select id="teacherDifficulty">
          <option>básica</option>
          <option>media</option>
          <option>avanzada</option>
        </select>

        <label>Cantidad</label>
        <input type="number" id="exerciseQuantity" value="5" min="1" max="20" />

        <button class="btn secondary" onclick="generateTeacherExercises()">Generar ejercicios similares</button>
        <button class="btn secondary" onclick="generateMockTest()">Generar simulacro avanzado</button>

        <div id="teacherExercises"></div>
      </div>
    </section>

    <section id="analitica" class="app-section">
      <h1>Analítica de Aprendizaje</h1>
      <div id="analyticsBox" class="panel"></div>
    </section>

    <section id="perfil" class="app-section">
      <h1>Perfil</h1>
      <div class="panel">
        <p id="profileInfo"></p>
        <button class="btn danger" onclick="logout()">Cerrar sesión</button>
      </div>
    </section>
  </main>

  <div class="coach-widget hidden" id="coachWidget">
    <button onclick="closeCoach()">×</button>
    <div class="coach-avatar" id="coachAvatar">🤖</div>
    <strong id="coachName">Coach Mathmentor</strong>
    <p id="coachMessage"></p>
  </div>

  <script src="js/api.js"></script>
  <script src="js/app.js"></script>
  <script src="js/dashboard.js"></script>
  <script src="js/diagnostic.js"></script>
  <script src="js/learning.js"></script>
  <script src="js/teacher-mode.js"></script>
  <script src="js/analytics.js"></script>
  <script src="js/coach.js"></script>
</body>
</html>
''')

wf("frontend/js/main.js", r'''
const formulas = [
  "∫ f(x) dx",
  "∇f(x,y)",
  "dy/dx",
  "x² + y²",
  "a²+b²=c²",
  "lim x→0",
  "∂f/∂x",
  "Σ",
  "y' + p(x)y = q(x)"
];

function createFormulaRain() {
  const container = document.getElementById("formulaRain");
  if (!container) return;

  for (let i = 0; i < 50; i++) {
    const span = document.createElement("span");
    span.className = "formula";
    span.textContent = formulas[Math.floor(Math.random() * formulas.length)];
    span.style.left = `${Math.random() * 100}%`;
    span.style.fontSize = `${14 + Math.random() * 22}px`;
    span.style.animationDuration = `${8 + Math.random() * 10}s`;
    span.style.animationDelay = `${Math.random() * 6}s`;
    container.appendChild(span);
  }
}

function showAuth(type) {
  const login = document.getElementById("loginForm");
  const register = document.getElementById("registerForm");
  const loginTab = document.getElementById("loginTab");
  const registerTab = document.getElementById("registerTab");

  if (type === "login") {
    login.classList.remove("hidden");
    register.classList.add("hidden");
    loginTab.classList.add("active");
    registerTab.classList.remove("active");
  } else {
    register.classList.remove("hidden");
    login.classList.add("hidden");
    registerTab.classList.add("active");
    loginTab.classList.remove("active");
  }
}

document.addEventListener("DOMContentLoaded", createFormulaRain);
''')

wf("frontend/js/auth.js", r'''
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const authMessage = document.getElementById("authMessage");

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const data = {
    name: document.getElementById("registerName").value,
    email: document.getElementById("registerEmail").value,
    password: document.getElementById("registerPassword").value
  };

  try {
    const response = await fetch(`${API_URL}/api/auth/register`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    });

    const result = await response.json();
    authMessage.textContent = result.message;

    if (result.success) {
      localStorage.setItem("mathmentor_user", JSON.stringify(result.user));
      window.location.href = "app.html";
    }
  } catch {
    authMessage.textContent = "No se pudo conectar con el backend.";
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const data = {
    email: document.getElementById("loginEmail").value,
    password: document.getElementById("loginPassword").value
  };

  try {
    const response = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    });

    const result = await response.json();
    authMessage.textContent = result.message;

    if (result.success) {
      localStorage.setItem("mathmentor_user", JSON.stringify(result.user));
      window.location.href = "app.html";
    }
  } catch {
    authMessage.textContent = "No se pudo conectar con el backend.";
  }
});
''')

wf("frontend/js/app.js", r'''
let SUBTOPICS = {};

function requireSession() {
  const user = getCurrentUser();

  if (!user.id) {
    window.location.href = "index.html";
    return;
  }

  document.getElementById("sidebarUser").textContent = user.name || "Estudiante";
  document.getElementById("profileInfo").textContent = `${user.name} · ${user.email}`;
}

function showSection(id) {
  document.querySelectorAll(".app-section").forEach(section => {
    section.classList.remove("active-section");
  });

  document.getElementById(id).classList.add("active-section");

  if (id === "dashboard") loadDashboard();
  if (id === "objetivos") loadObjectives();
  if (id === "analitica") loadAnalytics();
}

function logout() {
  localStorage.removeItem("mathmentor_user");
  window.location.href = "index.html";
}

async function loadSubtopics() {
  const response = await fetch(`${API_URL}/api/diagnostic/subtopics`);
  SUBTOPICS = await response.json();

  fillAreas("diagnosticArea");
  fillAreas("planArea");

  updateDiagnosticTopics();
  updatePlanTopics();
}

function fillAreas(selectId) {
  const select = document.getElementById(selectId);
  select.innerHTML = "";

  Object.keys(SUBTOPICS).forEach(area => {
    select.innerHTML += `<option value="${area}">${area}</option>`;
  });
}

function fillTopics(areaId, topicId) {
  const area = document.getElementById(areaId).value;
  const topicSelect = document.getElementById(topicId);
  topicSelect.innerHTML = "";

  (SUBTOPICS[area] || []).forEach(topic => {
    topicSelect.innerHTML += `<option value="${topic}">${topic}</option>`;
  });
}

function updateDiagnosticTopics() {
  fillTopics("diagnosticArea", "diagnosticTopic");
}

function updatePlanTopics() {
  fillTopics("planArea", "planTopic");
}

document.addEventListener("DOMContentLoaded", async () => {
  requireSession();
  await loadSubtopics();
  loadDashboard();
  loadCoachMessage();
});
''')

wf("frontend/js/dashboard.js", r'''
function kpiBar(kpi) {
  const current = Math.max(0, Math.min(Number(kpi.current_mastery), 100));
  const target = Math.max(0, Math.min(Number(kpi.target_mastery), 100));

  let color = "danger";
  if (current >= 70) color = "success";
  else if (current >= 40) color = "warning";

  return `
    <div class="kpi-bar-wrap">
      <div class="kpi-scale">
        <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
      </div>
      <div class="kpi-bar">
        <div class="kpi-fill ${color}" style="width:${current}%"></div>
        <div class="kpi-target" style="left:${target}%"></div>
      </div>
      <div class="kpi-labels">
        <span>Actual: ${current}%</span>
        <span>Meta: ${target}%</span>
      </div>
    </div>
  `;
}

async function loadDashboard() {
  const response = await fetch(`${API_URL}/api/analytics/dashboard/${getCurrentUserId()}`);
  const result = await response.json();

  const summary = result.summary;

  document.getElementById("dashboardSummary").innerHTML = `
    <div class="dash-card"><small>Objetivos activos</small><strong>${summary.active_objectives}</strong></div>
    <div class="dash-card"><small>Dominio promedio</small><strong>${summary.average_mastery}%</strong></div>
    <div class="dash-card"><small>Riesgo</small><strong>${summary.risk}</strong></div>
    <div class="dash-card"><small>Tema más débil</small><strong>${summary.weakest_topic}</strong></div>
    <div class="dash-card"><small>Error frecuente</small><strong>${summary.most_common_error}</strong></div>
    <div class="dash-card"><small>Próxima acción</small><strong>${summary.next_action}</strong></div>
  `;

  const list = document.getElementById("kpiList");
  list.innerHTML = "";

  if (!result.kpis.length) {
    list.innerHTML = `<div class="panel">Aún no tienes KPIs. Realiza un diagnóstico para crear tu primer objetivo.</div>`;
    return;
  }

  result.kpis.forEach(kpi => {
    list.innerHTML += `
      <div class="kpi-card">
        <h3>${kpi.topic}</h3>
        <p>${kpi.area || ""}</p>
        ${kpiBar(kpi)}
        <p>Estado: ${kpi.status}</p>
        <p>Riesgo: ${kpi.risk_level}</p>
        <p>Tiempo estimado: ${kpi.estimated_weeks} semanas</p>
        <p>Temas pendientes: ${kpi.pending_topics || "Sin pendientes"}</p>
      </div>
    `;
  });
}

async function loadObjectives() {
  const response = await fetch(`${API_URL}/api/analytics/dashboard/${getCurrentUserId()}`);
  const result = await response.json();

  const box = document.getElementById("objectivesBox");

  if (!result.kpis.length) {
    box.innerHTML = `
      <h3>Aún no tienes objetivos creados</h3>
      <p>Para comenzar, realiza un diagnóstico IA y crea tu primer KPI.</p>
      <button class="btn primary" onclick="showSection('diagnostico')">Ir a Diagnóstico IA</button>
    `;
    return;
  }

  box.innerHTML = result.kpis.map(kpi => `
    <div class="kpi-card">
      <h3>${kpi.topic}</h3>
      ${kpiBar(kpi)}
    </div>
  `).join("");
}
''')

wf("frontend/js/diagnostic.js", r'''
let currentTest = null;
let lastDiagnostic = null;
let timerInterval = null;

function validateWeeklyHours() {
  const input = document.getElementById("weeklyHours");
  let value = Number(input.value);

  if (value > 40) {
    alert("El máximo recomendado para estudio semanal en la plataforma es 40 horas.");
    value = 40;
    input.value = 40;
  }

  if (value < 1) {
    value = 1;
    input.value = 1;
  }

  return value;
}

async function generateDiagnosticTest() {
  const weekly = validateWeeklyHours();

  const data = {
    user_id: getCurrentUserId(),
    academic_level: document.getElementById("academicLevel").value,
    area: document.getElementById("diagnosticArea").value,
    topic: document.getElementById("diagnosticTopic").value,
    weekly_hours: weekly
  };

  const response = await fetch(`${API_URL}/api/diagnostic/generate-ai-test`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });

  currentTest = await response.json();

  renderQuestions(currentTest.questions);
  startTimer(currentTest.time_minutes);

  document.getElementById("testPanel").classList.remove("hidden");
}

function renderQuestions(questions) {
  const form = document.getElementById("questionForm");
  form.innerHTML = "";

  questions.forEach(q => {
    let options = q.options.map(option => `
      <label class="option">
        <input type="radio" name="q_${q.id}" value="${option}">
        ${option}
      </label>
    `).join("");

    let upload = q.requires_upload ? `
      <textarea placeholder="Escribe tu desarrollo si quieres que la IA lo revise."></textarea>
      <input type="file">
    ` : "";

    form.innerHTML += `
      <div class="question-card">
        <p><strong>${q.id}.</strong> ${q.question}</p>
        ${options}
        ${upload}
      </div>
    `;
  });
}

function startTimer(minutes) {
  clearInterval(timerInterval);

  let seconds = minutes * 60;

  timerInterval = setInterval(() => {
    seconds--;

    const min = Math.floor(seconds / 60);
    const sec = seconds % 60;

    document.getElementById("timer").textContent =
      `${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;

    if (seconds <= 0) {
      clearInterval(timerInterval);
      submitDiagnostic();
    }
  }, 1000);
}

async function submitDiagnostic() {
  clearInterval(timerInterval);

  const answers = {};

  currentTest.questions.forEach(q => {
    const selected = document.querySelector(`input[name="q_${q.id}"]:checked`);
    answers[String(q.id)] = selected ? selected.value : "";
  });

  const data = {
    user_id: getCurrentUserId(),
    academic_level: currentTest.academic_level,
    area: currentTest.area,
    topic: currentTest.topic,
    weekly_hours: Number(document.getElementById("weeklyHours").value),
    questions: currentTest.questions,
    answers
  };

  const response = await fetch(`${API_URL}/api/diagnostic/submit`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });

  lastDiagnostic = await response.json();

  const box = document.getElementById("diagnosticResult");
  box.classList.remove("hidden");

  box.innerHTML = `
    <h2>Resultado del diagnóstico</h2>
    <p>Puntaje: ${lastDiagnostic.score} / ${lastDiagnostic.total}</p>
    <p>Dominio: ${lastDiagnostic.mastery}%</p>
    <p>Riesgo: ${lastDiagnostic.risk_level}</p>
    <p>Errores detectados: ${lastDiagnostic.detected_errors.join(", ")}</p>
    <p>Subtemas débiles: ${lastDiagnostic.weak_subtopics.join(", ")}</p>
    <p>Meta recomendada: ${lastDiagnostic.recommended_goal}%</p>
    <p>Tiempo estimado: ${lastDiagnostic.estimated_weeks} semanas</p>
    <p>${lastDiagnostic.recommendation}</p>
    <button class="btn primary" onclick="createKPIFromDiagnostic()">Crear KPI con esta meta</button>
  `;
}

async function createKPIFromDiagnostic() {
  const data = {
    user_id: getCurrentUserId(),
    area: currentTest.area,
    topic: currentTest.topic,
    initial_mastery: lastDiagnostic.mastery,
    target_mastery: lastDiagnostic.recommended_goal,
    weekly_hours: lastDiagnostic.weekly_hours,
    estimated_weeks: lastDiagnostic.estimated_weeks
  };

  const response = await fetch(`${API_URL}/api/diagnostic/create-kpi`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });

  const result = await response.json();
  alert(result.message);
  loadDashboard();
  showSection("dashboard");
}
''')

wf("frontend/js/learning.js", r'''
function clampInput(id) {
  const input = document.getElementById(id);
  let value = Number(input.value);

  if (value < 0) value = 0;
  if (value > 100) value = 100;

  input.value = value;
  return value;
}

async function createStudyPlan() {
  const data = {
    academic_level: document.getElementById("planLevel").value,
    area: document.getElementById("planArea").value,
    topic: document.getElementById("planTopic").value,
    current_mastery: clampInput("planMastery"),
    target_mastery: clampInput("planTarget")
  };

  const response = await fetch(`${API_URL}/api/learning/plan`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });

  const plan = await response.json();
  const box = document.getElementById("studyPlan");

  box.innerHTML = `
    <div class="panel">
      <h2>Ruta Guiada IA: ${plan.topic}</h2>
      <p>Dominio actual: ${plan.current_mastery}% · Meta: ${plan.target_mastery}%</p>
    </div>
  `;

  plan.modules.forEach(module => {
    box.innerHTML += `
      <div class="plan-card">
        <h3>${module.title}</h3>
        <p><strong>Objetivo:</strong> ${module.objective}</p>
        <p><strong>Teoría:</strong> ${module.theory}</p>
        <p><strong>Fórmulas:</strong> ${(module.formulas || []).join(", ")}</p>
        <p><strong>Ejemplo cotidiano:</strong> ${module.daily_example}</p>

        <h4>Ejemplo desarrollado paso a paso</h4>
        ${(module.developed_example || []).map(step => `
          <div class="step-card">
            <p><strong>Paso ${step.step}:</strong> ${step.what}</p>
            <p><strong>¿Por qué?</strong> ${step.why}</p>
          </div>
        `).join("")}

        <h4>Ejercicios</h4>
        <ul>${(module.practice || []).map(ex => `<li>${ex}</li>`).join("")}</ul>

        <button class="btn secondary" onclick="simulateEvaluation('${plan.topic}', '${module.title}')">
          Evaluar tema
        </button>
      </div>
    `;
  });
}

async function simulateEvaluation(topic, subtopic) {
  const score = Number(prompt("Ingresa tu porcentaje de aprobación:"));

  const response = await fetch(`${API_URL}/api/learning/evaluate`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      user_id: getCurrentUserId(),
      topic,
      subtopic,
      score
    })
  });

  const result = await response.json();
  alert(result.message);
}

function quickPrompt(text) {
  document.getElementById("chatInput").value = text;
}

async function sendChatMessage() {
  const input = document.getElementById("chatInput");
  const message = input.value.trim();

  if (!message) return;

  const chat = document.getElementById("chatMessages");
  chat.innerHTML += `<div class="user-message">${message}</div>`;
  input.value = "";

  const response = await fetch(`${API_URL}/api/chatbot/`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      user_id: getCurrentUserId(),
      message,
      mode: "libre"
    })
  });

  const result = await response.json();
  chat.innerHTML += `<div class="bot-message">${result.response}</div>`;
  chat.scrollTop = chat.scrollHeight;
}
''')

wf("frontend/js/teacher-mode.js", r'''
async function uploadTeacherMaterial() {
  const files = document.getElementById("teacherFiles").files;

  if (!files.length) {
    alert("Sube al menos un archivo.");
    return;
  }

  const formData = new FormData();
  formData.append("user_id", getCurrentUserId());

  Array.from(files).forEach(file => {
    formData.append("files", file);
  });

  const response = await fetch(`${API_URL}/api/teacher-mode/upload`, {
    method: "POST",
    body: formData
  });

  const result = await response.json();

  document.getElementById("teacherResult").innerHTML = `
    <h3>Material analizado</h3>
    <p>${result.analysis.summary}</p>
    <p><strong>Temas:</strong> ${result.analysis.topics.join(", ")}</p>
    <p><strong>Estilo:</strong> ${result.analysis.teacher_style}</p>
    <p><strong>Dificultad:</strong> ${result.analysis.difficulty}</p>
    <p><strong>Recomendaciones:</strong> ${result.analysis.recommendations.join(", ")}</p>
  `;
}

async function generateTeacherExercises() {
  const topic = document.getElementById("teacherTopic").value || "matemática";
  const difficulty = document.getElementById("teacherDifficulty").value;
  const quantity = document.getElementById("exerciseQuantity").value;

  const response = await fetch(
    `${API_URL}/api/teacher-mode/exercises?topic=${encodeURIComponent(topic)}&difficulty=${difficulty}&quantity=${quantity}`
  );

  const result = await response.json();

  document.getElementById("teacherExercises").innerHTML = `
    <h3>Ejercicios similares</h3>
    ${result.exercises.map(ex => `
      <div class="question-card">
        <p><strong>${ex.number}.</strong> ${ex.statement}</p>
        <p>Dificultad: ${ex.difficulty}</p>
        <p>Método sugerido: ${ex.suggested_method}</p>
      </div>
    `).join("")}
  `;
}

async function generateMockTest() {
  const topic = document.getElementById("teacherTopic").value || "matemática";
  const difficulty = document.getElementById("teacherDifficulty").value;

  const response = await fetch(
    `${API_URL}/api/teacher-mode/mock-test?topic=${encodeURIComponent(topic)}&difficulty=${difficulty}&quantity=6&duration=45`
  );

  const result = await response.json();

  document.getElementById("teacherExercises").innerHTML = `
    <h3>Simulacro avanzado</h3>
    <p>Duración: ${result.duration_minutes} minutos</p>
    <p>${result.instructions}</p>
    <p>Criterios: ${result.criteria.join(", ")}</p>
    ${result.questions.map(q => `
      <div class="question-card">
        <p><strong>${q.number}.</strong> ${q.statement}</p>
        <p>Tipo: ${q.type} · Puntaje: ${q.points}</p>
      </div>
    `).join("")}
  `;
}
''')

wf("frontend/js/analytics.js", r'''
async function loadAnalytics() {
  const response = await fetch(`${API_URL}/api/analytics/learning/${getCurrentUserId()}`);
  const result = await response.json();

  const box = document.getElementById("analyticsBox");

  if (!result.diagnostics.length && !result.history.length) {
    box.innerHTML = `<p>${result.message}</p>`;
    return;
  }

  box.innerHTML = `
    <h3>Diagnósticos realizados</h3>
    ${result.diagnostics.map(d => `
      <div class="mini-card">
        <p>${d.area} · ${d.topic}</p>
        <p>Dominio: ${d.mastery}% · Riesgo: ${d.risk_level}</p>
        <p>Errores: ${d.detected_errors}</p>
      </div>
    `).join("")}

    <h3>Historial de aprendizaje libre</h3>
    ${result.history.map(h => `
      <div class="mini-card">
        <p><strong>Pregunta:</strong> ${h.question}</p>
        <p><strong>Respuesta:</strong> ${h.answer.slice(0, 240)}...</p>
      </div>
    `).join("")}
  `;
}
''')

wf("frontend/js/coach.js", r'''
const positionClasses = [
  "coach-top-left",
  "coach-top-right",
  "coach-bottom-left",
  "coach-bottom-right",
  "coach-middle-left",
  "coach-middle-right"
];

async function loadCoachMessage(context = "general") {
  const response = await fetch(`${API_URL}/api/coach/message?context=${context}`);
  const result = await response.json();

  const widget = document.getElementById("coachWidget");

  positionClasses.forEach(cls => widget.classList.remove(cls));
  widget.classList.add(`coach-${result.position}`);

  document.getElementById("coachAvatar").textContent = result.avatar;
  document.getElementById("coachName").textContent = result.name;
  document.getElementById("coachMessage").textContent = result.message;

  widget.classList.remove("hidden");
}

function closeCoach() {
  document.getElementById("coachWidget").classList.add("hidden");
}

setInterval(() => {
  loadCoachMessage();
}, 45000);
''')

wf("frontend/css/styles.css", r'''
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: "Segoe UI", Arial, sans-serif;
}

body {
  background: #090914;
  color: white;
}

.hidden {
  display: none !important;
}

.landing-body {
  min-height: 100vh;
  overflow: hidden;
}

.formula-rain {
  position: fixed;
  inset: 0;
  background:
    radial-gradient(circle at top left, rgba(139, 92, 246, 0.35), transparent 35%),
    radial-gradient(circle at bottom right, rgba(16, 185, 129, 0.18), transparent 35%),
    linear-gradient(135deg, #10051f, #1e1b4b, #090914);
  z-index: -1;
  overflow: hidden;
}

.formula {
  position: absolute;
  color: rgba(255,255,255,0.16);
  font-weight: 900;
  animation: fall linear infinite;
}

@keyframes fall {
  from { transform: translateY(-120px); opacity: 0; }
  20% { opacity: 1; }
  to { transform: translateY(110vh); opacity: 0; }
}

.landing {
  min-height: 100vh;
  padding: 7%;
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  align-items: center;
  gap: 50px;
}

.eyebrow {
  display: inline-block;
  color: #ddd6fe;
  background: rgba(124, 58, 237, 0.2);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 999px;
  padding: 9px 15px;
  font-weight: 900;
  margin-bottom: 18px;
}

.landing h1 {
  font-size: clamp(3rem, 7vw, 6rem);
  line-height: 1;
  margin-bottom: 22px;
}

.landing-description {
  font-size: 1.35rem;
  color: #ddd6fe;
  max-width: 760px;
  margin-bottom: 16px;
}

.landing-sub {
  color: #c4b5fd;
  font-size: 1.05rem;
}

.auth-card,
.panel,
.kpi-card,
.plan-card,
.question-card,
.step-card,
.dash-card,
.mini-card {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 22px;
  padding: 22px;
  backdrop-filter: blur(14px);
}

.auth-tabs {
  display: flex;
  background: rgba(0,0,0,0.25);
  padding: 5px;
  border-radius: 14px;
  margin-bottom: 18px;
}

.auth-tabs button {
  flex: 1;
  padding: 12px;
  border: 0;
  border-radius: 11px;
  background: transparent;
  color: white;
  font-weight: 900;
  cursor: pointer;
}

.auth-tabs button.active {
  background: #7c3aed;
}

.auth-form {
  display: grid;
  gap: 14px;
}

input,
select,
textarea {
  width: 100%;
  padding: 13px 14px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.16);
  background: rgba(255,255,255,0.1);
  color: white;
  outline: none;
  margin-bottom: 14px;
}

option {
  color: #111827;
}

textarea {
  min-height: 110px;
  resize: vertical;
}

label {
  display: block;
  color: #ddd6fe;
  font-weight: 800;
  margin-bottom: 8px;
}

.btn {
  border: 0;
  border-radius: 14px;
  padding: 13px 18px;
  font-weight: 900;
  cursor: pointer;
}

.btn.primary {
  background: linear-gradient(135deg, #7c3aed, #a855f7);
  color: white;
}

.btn.secondary {
  background: white;
  color: #1e1b4b;
}

.btn.danger {
  background: #dc2626;
  color: white;
}

.app-body {
  display: grid;
  grid-template-columns: 280px 1fr;
  min-height: 100vh;
  background: #0b0b16;
}

.sidebar {
  background: linear-gradient(180deg, #1e1b4b, #111122);
  padding: 24px;
  border-right: 1px solid rgba(255,255,255,0.1);
  position: fixed;
  width: 280px;
  height: 100vh;
}

.sidebar-logo {
  font-size: 1.45rem;
  font-weight: 900;
  margin-bottom: 8px;
}

.sidebar-logo span {
  color: #a78bfa;
}

.sidebar-user {
  color: #c4b5fd;
  margin-bottom: 24px;
}

.side-nav {
  display: grid;
  gap: 10px;
}

.side-nav button {
  background: rgba(255,255,255,0.06);
  color: white;
  border: 1px solid rgba(255,255,255,0.1);
  padding: 13px;
  border-radius: 14px;
  text-align: left;
  cursor: pointer;
  font-weight: 800;
}

.side-nav button.active,
.side-nav button:hover {
  background: #7c3aed;
}

.app-main {
  margin-left: 280px;
  padding: 34px;
}

.app-section {
  display: none;
}

.active-section {
  display: block;
}

.app-section h1 {
  font-size: 2.2rem;
  margin-bottom: 10px;
}

.muted {
  color: #c4b5fd;
  margin-bottom: 22px;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 18px;
  margin-bottom: 22px;
}

.dash-card small {
  color: #c4b5fd;
  display: block;
  margin-bottom: 8px;
}

.dash-card strong {
  font-size: 1.5rem;
}

.kpi-list,
.plan-output {
  display: grid;
  gap: 18px;
}

.kpi-bar-wrap {
  margin: 16px 0;
}

.kpi-scale,
.kpi-labels {
  display: flex;
  justify-content: space-between;
  font-size: 0.82rem;
  color: #c4b5fd;
}

.kpi-bar {
  position: relative;
  height: 15px;
  background: rgba(255,255,255,0.15);
  border-radius: 999px;
  margin: 8px 0;
  overflow: hidden;
}

.kpi-fill {
  height: 100%;
  border-radius: 999px;
}

.kpi-fill.danger {
  background: #ef4444;
}

.kpi-fill.warning {
  background: #f59e0b;
}

.kpi-fill.success {
  background: #10b981;
}

.kpi-target {
  position: absolute;
  top: -5px;
  width: 4px;
  height: 25px;
  background: #ffffff;
  border-radius: 999px;
}

.form-panel {
  max-width: 760px;
  margin-bottom: 22px;
}

.test-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

#timer {
  color: #34d399;
  font-weight: 900;
  font-size: 1.2rem;
}

.option {
  display: block;
  padding: 8px 0;
  color: white;
}

.quick-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.quick-actions button {
  background: rgba(255,255,255,0.1);
  border: 1px solid rgba(255,255,255,0.15);
  color: white;
  border-radius: 999px;
  padding: 9px 13px;
  cursor: pointer;
}

.chat-container {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 22px;
  overflow: hidden;
}

.chat-messages {
  height: 390px;
  overflow-y: auto;
  padding: 20px;
}

.bot-message,
.user-message {
  max-width: 82%;
  padding: 14px;
  border-radius: 16px;
  margin-bottom: 14px;
  white-space: pre-wrap;
}

.bot-message {
  background: rgba(255,255,255,0.1);
}

.user-message {
  background: #7c3aed;
  margin-left: auto;
}

.chat-input {
  display: flex;
  gap: 12px;
  padding: 16px;
}

.chat-input textarea {
  margin-bottom: 0;
}

.coach-widget {
  position: fixed;
  width: 280px;
  background: linear-gradient(135deg, #6d28d9, #4c1d95);
  border: 1px solid rgba(255,255,255,0.18);
  border-radius: 22px;
  padding: 20px;
  z-index: 99;
  box-shadow: 0 20px 50px rgba(0,0,0,0.35);
}

.coach-widget button {
  position: absolute;
  top: 10px;
  right: 12px;
  background: transparent;
  color: white;
  border: 0;
  font-size: 1.1rem;
  cursor: pointer;
}

.coach-avatar {
  font-size: 2.4rem;
  margin-bottom: 8px;
}

.coach-top-left { top: 90px; left: 310px; }
.coach-top-right { top: 90px; right: 30px; }
.coach-bottom-left { bottom: 30px; left: 310px; }
.coach-bottom-right { bottom: 30px; right: 30px; }
.coach-middle-left { top: 45%; left: 310px; }
.coach-middle-right { top: 45%; right: 30px; }

@media (max-width: 900px) {
  .landing,
  .app-body {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
    width: 100%;
    height: auto;
  }

  .app-main {
    margin-left: 0;
  }

  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}
''')

wf("README.md", r'''
# Mathmentor IA

Mathmentor IA es una plataforma educativa con inteligencia artificial para estudiantes de ingeniería hasta segundo año.

## Funcionalidades

- Landing pública con lluvia de fórmulas.
- Login y registro.
- App interna separada en `app.html`.
- Dashboard con KPIs visuales tipo barra de progreso/meta.
- Diagnóstico IA con mínimo 5 preguntas.
- Subtemas dependientes del área matemática.
- Tiempo de test ajustado por nivel y dificultad.
- Límite lógico de horas semanales: 1 a 40.
- Ruta Guiada IA con explicación teórica, fórmulas, ejemplos cotidianos y paso a paso.
- Aprendizaje Libre como tutor matemático real.
- Modo Profesor con múltiples archivos.
- Generación de ejercicios similares y simulacros más difíciles.
- Analítica de aprendizaje.
- Coach Mathmentor con personaje y aparición aleatoria.

## Ejecutar backend

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
''')
