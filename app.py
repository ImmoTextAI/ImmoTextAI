import streamlit as st
import sqlite3
import hashlib
import os
from datetime import datetime
from groq import Groq
from fpdf import FPDF
import base64
from PIL import Image
import io

STRIPE_PAYMENT_URL = "https://buy.stripe.com/test_6oU9AS8mC7H68AN7iO0Ny00"
UPLOAD_DIR = "profile_pics"
PROPERTY_IMAGE_DIR = "property_images"
LOGO_PATH = "logo.jpg"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
if not os.path.exists(PROPERTY_IMAGE_DIR):
    os.makedirs(PROPERTY_IMAGE_DIR)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password TEXT,
            name TEXT,
            telefon TEXT,
            buero TEXT,
            profilbild TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE users ADD COLUMN password TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN profilbild TEXT")
    except sqlite3.OperationalError:
        pass
    c.execute("""
        CREATE TABLE IF NOT EXISTS exposes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            titel TEXT,
            inhalt TEXT,
            datum TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            titel TEXT,
            inhalt TEXT,
            datum TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_user(email):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute("SELECT password, name, telefon, buero, profilbild FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "password": row[0], 
            "name": row[1] or "", 
            "telefon": row[2] or "", 
            "buero": row[3] or "",
            "profilbild": row[4]
        }
    return None

def register_user(email, password, name="", telefon="", buero=""):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    hashed_pw = hash_password(password)
    c.execute("""
        INSERT OR REPLACE INTO users (email, password, name, telefon, buero, profilbild) 
        VALUES (?, ?, ?, ?, ?, NULL)
    """, (email, hashed_pw, name, telefon, buero))
    conn.commit()
    conn.close()

def update_user_profile(email, name, telefon, buero, profilbild=None):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    if profilbild:
        c.execute('UPDATE users SET name=?, telefon=?, buero=?, profilbild=? WHERE email=?', (name, telefon, buero, profilbild, email))
    else:
        c.execute('UPDATE users SET name=?, telefon=?, buero=? WHERE email=?', (name, telefon, buero, email))
    conn.commit()
    conn.close()

def update_user_email(old_email, new_email):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute('UPDATE users SET email=? WHERE email=?', (new_email, old_email))
    c.execute('UPDATE exposes SET email=? WHERE email=?', (new_email, old_email))
    c.execute('UPDATE notes SET email=? WHERE email=?', (new_email, old_email))
    conn.commit()
    conn.close()

def update_user_password(email, new_password):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    hashed_pw = hash_password(new_password)
    c.execute('UPDATE users SET password=? WHERE email=?', (hashed_pw, email))
    conn.commit()
    conn.close()

def save_expose_to_db(email, titel, inhalt):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute("INSERT INTO exposes (email, titel, inhalt) VALUES (?, ?, ?)", (email, titel, inhalt))
    conn.commit()
    conn.close()

def get_user_exposes(email):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute("SELECT id, titel, inhalt, datum FROM exposes WHERE email = ? ORDER BY datum DESC", (email,))
    rows = c.fetchall()
    conn.close()
    return rows

def save_note_to_db(email, titel, inhalt):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute("INSERT INTO notes (email, titel, inhalt) VALUES (?, ?, ?)", (email, titel, inhalt))
    conn.commit()
    conn.close()

def get_user_notes(email):
    conn = sqlite3.connect("immo_users.db")
    c = conn.cursor()
    c.execute("SELECT id, titel, inhalt, datum FROM notes WHERE email = ? ORDER BY datum DESC", (email,))
    rows = c.fetchall()
    conn.close()
    return rows

def create_pdf(text, makler_name, makler_telefon, makler_email, makler_buero):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Immobilien-Exposé", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 11)
    clean_text = text.encode("latin-1", "replace").decode("latin-1")
    pdf.multi_cell(0, 8, clean_text)
    if makler_name or makler_telefon or makler_buero or makler_email:
        pdf.ln(10)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Ihr persönlicher Ansprechpartner:", ln=True)
        pdf.set_font("Helvetica", "", 10)
        contact_lines = []
        if makler_name: contact_lines.append(f"Name: {makler_name}")
        if makler_telefon: contact_lines.append(f"Telefon: {makler_telefon}")
        if makler_email: contact_lines.append(f"E-Mail: {makler_email}")
        if makler_buero: contact_lines.append(f"Büro: {makler_buero}")
        contact_info = "\n".join(contact_lines)
        clean_contact = contact_info.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 6, clean_contact)
    return bytes(pdf.output(dest='S'))

def encode_image_to_base64(uploaded_file):
    image = Image.open(uploaded_file)
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        image = image.convert("RGB")
    image.thumbnail((800, 800))
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=85)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def get_epoch_prompt_instructions(stimmung, lang="Deutsch"):
    if lang == "English":
        instructions = {
            "🚀 Junge Erwachsene / Urban Start-up (Modern, dynamisch, frisch)": "CRITICAL: Output ONLY the final property exposé. No thinking process, no <think> tags. Tone: Modern, dynamic, fresh, and trendy. Ideal for young professionals, singles, and first-time buyers looking for an urban lifestyle, openness, and smart aesthetics.",
            "🏡 Familienphase / Nestbauer (Warm, sicher, kinderfreundlich)": "CRITICAL: Output ONLY the final property exposé. No thinking process, no <think> tags. Tone: Warm, emotional, safe, and family-oriented. Focus on a harmonious home, child safety, garden spaces, and a welcoming community.",
            "🏛️ Etablierte Lebensmitte / Karriere (Elegant, prestigeträchtig, exklusiv)": "CRITICAL: Output ONLY the final property exposé. No thinking process, no <think> tags. Tone: Elegant, prestigious, exclusive, and sophisticated. Focus on top architecture, premium finishes, status, and long-term value.",
            "🧓 Ruhestand / Senioren (Ruhig, naturnah, barrierearm, entspannt)": "CRITICAL: Output ONLY the final property exposé. No thinking process, no <think> tags. Tone: Peaceful, natural, accessible, and relaxed. Focus on tranquility, relaxation, comfort, nature, and stress-free living."
        }
    else:
        instructions = {
            "🚀 Junge Erwachsene / Urban Start-up (Modern, dynamisch, frisch)": "WICHTIG: Gib AUSSCHLIESSLICH das fertige Exposé aus. Keine Denkprozesse, keine <think>-Tags. Schreibstil: Modern, dynamisch, frisch und am Puls der Zeit. Zielgruppe sind junge Berufstätige, Singles oder Erstkäufer, die einen urbanen Lifestyle, Offenheit und smarte Ästhetik suchen.",
            "🏡 Familienphase / Nestbauer (Warm, sicher, kinderfreundlich)": "WICHTIG: Gib AUSSCHLIESSLICH das fertige Exposé aus. Keine Denkprozesse, keine <think>-Tags. Schreibstil: Herzlich, emotional, sicher und familiär. Der Fokus liegt auf einem behaglichen Zuhause, Garten, Sicherheit für Kinder, Spielmöglichkeiten und einer harmonischen Nachbarschaft.",
            "🏛️ Etablierte Lebensmitte / Karriere (Elegant, prestigeträchtig, exklusiv)": "WICHTIG: Gib AUSSCHLIESSLICH das fertige Exposé aus. Keine Denkprozesse, keine <think>-Tags. Schreibstil: Elegant, gehoben, prestigeträchtig und souverän. Der Fokus liegt auf architektonischer Qualität, exklusiven Materialien, Status und langfristigem Werterhalt.",
            "🧓 Ruhestand / Senioren (Ruhig, naturnah, barrierearm, entspannt)": "WICHTIG: Gib AUSSCHLIESSLICH das fertige Exposé aus. Keine Denkprozesse, keine <think>-Tags. Schreibstil: Ruhig, einladend, entspannt und naturnah. Der Fokus liegt auf Erholung, Komfort, Barrierefreiheit, friedlicher Umgebung und barrierearmem Wohnen."
        }
    return instructions.get(stimmung, instructions.get(list(instructions.keys())[0]))

def main():
    init_db()
    st.set_page_config(page_title="ImmoText AI", page_icon="🏡", layout="centered")
    
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user_email" not in st.session_state:
        st.session_state.user_email = ""

    if st.session_state.user_email and not st.session_state.authenticated:
        st.session_state.authenticated = True

    st.sidebar.title("🎨 Design-Modus")
    theme = st.sidebar.selectbox("Wähle das Design", ["Light Mode ☀️", "Dark Mode 🌙"], index=1)
    
    radio_box_css = """
    div[data-testid="stRadio"] > div { gap: 8px; }
    div[data-testid="stRadio"] label {
        border-radius: 8px;
        padding: 8px 12px;
        transition: all 0.2s ease;
        width: 100%;
    }
    """

    if theme == "Dark Mode 🌙":
        st.markdown(f"""
            <style>
            .stApp {{ background-color: #0b0f19; color: #f8fafc; }}
            section[data-testid="stSidebar"] {{ background-color: #111827; color: #f8fafc; }}
            section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {{ color: #f8fafc !important; }}
            div[data-testid="stRadio"] label {{
                background-color: rgba(59, 130, 246, 0.05);
                border: 1px solid rgba(59, 130, 246, 0.2);
            }}
            div[data-testid="stRadio"] label:hover {{
                background-color: rgba(59, 130, 246, 0.15);
                border-color: rgba(59, 130, 246, 0.5);
            }}
            .stButton button {{
                width: 100%; background-color: #3b82f6; color: white;
                border-radius: 8px; font-weight: 600; padding: 0.6rem; border: none;
            }}
            .stButton button:hover {{ background-color: #2563eb; color: white; }}
            {radio_box_css}
            </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <style>
            .stApp {{ background-color: #f8fafc; color: #0f172a; }}
            section[data-testid="stSidebar"] {{ background-color: #ffffff; color: #0f172a; border-right: 1px solid #e2e8f0; }}
            section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {{ color: #0f172a !important; }}
            
            .stApp p, .stApp span, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6, .stApp li {{ color: #0f172a !important; }}
            
            div[data-testid="stRadio"] label {{
                background-color: #ffffff;
                border: 1px solid #cbd5e1;
            }}
            div[data-testid="stRadio"] label:hover {{
                background-color: #f1f5f9;
                border-color: #94a3b8;
            }}
            
            div[data-baseweb="select"] > div {{
                background-color: #ffffff !important;
                color: #0f172a !important;
                border-color: #cbd5e1 !important;
            }}
            div[data-baseweb="select"] span {{
                color: #0f172a !important;
            }}
            div[data-baseweb="popover"] div, div[data-baseweb="menu"] div, div[data-baseweb="option"] {{
                background-color: #ffffff !important;
                color: #0f172a !important;
            }}
            div[data-baseweb="option"]:hover {{
                background-color: #f1f5f9 !important;
                color: #0f172a !important;
            }}

            input, textarea {{ 
                color: #0f172a !important; 
                background-color: #ffffff !important; 
                border: 1px solid #cbd5e1 !important;
            }}
            .stButton button {{
                width: 100%; background-color: #2563eb; color: white;
                border-radius: 8px; font-weight: 600; padding: 0.6rem; border: none;
            }}
            .stButton button:hover {{ background-color: #1d4ed8; color: white; }}
            {radio_box_css}
            </style>
        """, unsafe_allow_html=True)

    if not st.session_state.authenticated:
        col_space, col_logo = st.columns([3, 1])
        with col_logo:
            if os.path.exists(LOGO_PATH):
                st.image(LOGO_PATH, width=150)

        st.title("ImmoText AI 🏡")
        
        if st.query_params.get("pro", "false") == "true" or "session_id" in st.query_params:
            if not st.session_state.user_email:
                st.session_state.user_email = "kunde@stripe-payment.de"
            st.session_state.authenticated = True

        st.markdown("---")
        tab_login, tab_register, tab_datenschutz = st.tabs(["🔐 Anmelden", "📝 Registrieren", "🔒 Datenschutzerklärung"])
        
        with tab_login:
            st.subheader("Willkommen zurück!")
            st.write("Bitte melde dich mit deinen Zugangsdaten an.")
            login_email = st.text_input("E-Mail-Adresse", placeholder="z.B. name@gmail.com", key="login_email")
            login_password = st.text_input("Passwort", type="password", placeholder="Dein Passwort", key="login_pw")
            
            if st.button("Anmelden", key="btn_login"):
                clean_email = login_email.strip().lower()
                whitelist_raw = st.secrets.get("WHITELIST_EMAIL", "")
                whitelist = [email.strip().lower() for email in whitelist_raw.split(",")] if whitelist_raw else []
                
                if not clean_email or not login_password:
                    st.error("⚠️ Bitte fülle alle Felder aus.")
                elif "@" not in clean_email or "." not in clean_email:
                    st.error("⚠️ Bitte gib eine gültige E-Mail-Adresse ein (mit '@' und Domain).")
                else:
                    user_record = get_user(clean_email)
                    if not user_record or not user_record["password"]:
                        st.error(f"❌ Unter der E-Mail {clean_email} existiert kein Account. Bitte registriere dich zuerst.")
                    else:
                       if user_record["password"] == hash_password(login_password): st.session_state.authenticated = True; st.session_state.user_email = clean_email; st.rerun()
                           
        with tab_register:
            st.subheader("Neues Konto erstellen")
            st.write("Erstelle deinen Account, um fehlerfreie Exposés zu generieren.")
            reg_email = st.text_input("E-Mail-Adresse", placeholder="z.B. name@gmail.com", key="reg_email")
            reg_password = st.text_input("Passwort wählen", type="password", placeholder="Sicheres Passwort", key="reg_pw")
            
            st.markdown("##### Makler-Standarddaten für den Exposé-Footer (optional & jederzeit in den Einstellungen änderbar)")
            reg_name = st.text_input("Dein vollständiger Name (optional)", value="", placeholder="z.B. Max Mustermann", key="reg_name")
            reg_telefon = st.text_input("Deine Telefonnummer (optional)", value="", placeholder="z.B. +49 (0) 551 1234567", key="reg_tel")
            reg_buero = st.text_area("Büro-Adresse / Firmenname (optional)", value="", placeholder="z.B. Musterstraße 12, 37073 Göttingen", key="reg_buero")
            
            if st.button("Jetzt registrieren", key="btn_register"):
                clean_reg_email = reg_email.strip().lower()
                whitelist_raw = st.secrets.get("WHITELIST_EMAIL", "")
                whitelist = [email.strip().lower() for email in whitelist_raw.split(",")] if whitelist_raw else []
                
                if not clean_reg_email or not reg_password:
                    st.error("⚠️ Bitte E-Mail und Passwort eingeben.")
                elif "@" not in clean_reg_email or "." not in clean_reg_email:
                    st.error("⚠️ Bitte gib eine gültige E-Mail-Adresse ein (mit '@' und Domain).")
                else:
                    existing_user = get_user(clean_reg_email)
                    if existing_user and existing_user["password"]:
                        st.error("⚠️ Es existiert bereits ein Konto mit dieser E-Mail. Bitte melde dich stattdessen an.")
                    else:
                        register_user(clean_reg_email, reg_password, reg_name, reg_telefon, reg_buero)
                        if clean_reg_email in whitelist:
                            st.success("Registrierung erfolgreich! Du wirst angemeldet...")
                            st.session_state.authenticated = True
                            st.session_state.user_email = clean_reg_email
                            st.rerun()
                        else:
                            st.success("Registrierung erfolgreich! Bitte schalte nun deinen Pro-Zugang frei:")
                            st.markdown(f"""
                                <a href="{STRIPE_PAYMENT_URL}" target="_self">
                                    <button style="width:100%; background-color:#635BFF; color:white; padding:14px; border:none; border-radius:8px; font-size:16px; font-weight:600; cursor:pointer;">
                                        Jetzt für 29 € / Monat freischalten (Stripe Checkout)
                                    </button>
                                </a>
                            """, unsafe_allow_html=True)

        with tab_datenschutz:
            st.subheader("🔒 Datenschutzerklärung")
            st.write("""
            **1. Datenschutz auf einen Blick**
            Die folgenden Hinweise geben einen einfachen Überblick darüber, was mit Ihren personenbezogenen Daten passiert, wenn Sie unsere Website besuchen.
            
            **2. KI-Verarbeitung (Groq API)**
            Zur Generierung von Texten und Bildanalysen nutzen wir Schnittstellen des Anbieters Groq, Inc.
            
            **3. Hosting und Zahlungsabwicklung (Stripe)**
            For the processing of paid services, we use Stripe.
            """)
        st.stop()
    
    if os.path.exists(LOGO_PATH):
        col_sb1, col_sb2 = st.columns([2, 1])
        with col_sb2:
            st.sidebar.image(LOGO_PATH, width=80)

    user_data = get_user(st.session_state.user_email)
    current_name = user_data["name"] if user_data else ""
    current_telefon = user_data["telefon"] if user_data else ""
    current_buero = user_data["buero"] if user_data else ""
    current_profilbild = user_data["profilbild"] if user_data else None

    st.sidebar.markdown("---")
    if current_profilbild and os.path.exists(current_profilbild):
        st.sidebar.image(current_profilbild, width=100, caption=current_name if current_name else st.session_state.user_email)
    
    st.sidebar.write(f"Eingeloggt als:\n`{st.session_state.user_email}`")
    
    if st.sidebar.button("🚪 Abmelden / Ausloggen", key="btn_logout"):
        st.session_state.authenticated = False
        st.session_state.user_email = ""
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.title("Navigation")
    menu = st.sidebar.radio(
        "Menü", 
        [
            "🏠 Startseite",
            "Exposé Generator", 
            "📸 KI-Bilderkennung", 
            "📝 Digitaler Notizblock",
            "📂 Meine Exposés (Archiv)", 
            "⚙️ Einstellungen (My Account)",
            "🔒 Datenschutzerklärung"
        ]
    )

    # Haupttitel mit integriertem Logo oben auf der Seite
    col_titel, col_logo_main = st.columns([4, 1])
    with col_titel:
        st.title("ImmoText AI 🏡")
    with col_logo_main:
        if os.path.exists(LOGO_PATH):
            st.image(LOGO_PATH, width=90)

    if menu == "🏠 Startseite":
        st.subheader(f"👋 Hallo{', ' + current_name if current_name else ''}!")
        st.write(f"Schön, dass du da bist. Du bist eingeloggt als `{st.session_state.user_email}`.")
        st.markdown("---")
        st.markdown("### Übersicht deiner Tools:")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info("**Exposé Generator**\n\nErstelle rechtssichere, faktenbasierte Immobilien-Texte in Sekundenschnelle inklusive Lebensphasen-Stimmungen.")
            st.info("**📸 KI-Bilderkennung**\n\nLade Fotos hoch, wähle deine Lebensphase und lass direkt ein maßgeschneidertes Exposé erstellen.")
        with col2:
            st.info("**📝 Digitaler Notizblock**\n\nHalte wichtige Eindrücke und Notizen direkt bei Besichtigungen fest.")
            st.info("**📂 Exposé-Archiv**\n\nGreife jederzeit auf deine bisherigen Texte und PDFs zu.")

    elif menu == "Exposé Generator":
        st.subheader("🏡 Professioneller Immobilien-Exposé-Generator")
        st.write("Gib die Objektdetails ein und wähle die passende Stimmung je nach Lebensphase der Zielgruppe.")

        with st.form("expose_form"):
            expose_lang = st.selectbox("Exposé-Sprache / Language", ["Deutsch", "English"])
            
            st.markdown("##### 🎭 Stimmung & Lebensphase der Zielgruppe")
            stimmung_auswahl = st.selectbox(
                "Wähle die passende Zeitepoche / Lebensphase für den Tonfall:",
                [
                    "🚀 Junge Erwachsene / Urban Start-up (Modern, dynamisch, frisch)",
                    "🏡 Familienphase / Nestbauer (Warm, sicher, kinderfreundlich)",
                    "🏛️ Etablierte Lebensmitte / Karriere (Elegant, prestigeträchtig, exklusiv)",
                    "☕ Ruhestand / Senioren (Ruhig, naturnah, barrierearm, entspannt)"
                ]
            )
            
            col1, col2 = st.columns(2)
            with col1:
                immobilien_typ = st.selectbox(
                    "Art der Immobilie", 
                    [
                        "Einfamilienhaus", 
                        "Wohnung / Etagenwohnung", 
                        "Penthouse", 
                        "Doppelhaushälfte", 
                        "Reihenhaus", 
                        "Gewerbeobjekt", 
                        "Grundstück", 
                        "Villa"
                    ]
                )
                objekt_titel = st.text_input("Objekttitel / Überschrift", placeholder="z.B. Exklusive Immobilie in Bestlage")
                ort = st.text_input("Ort / Lage", placeholder="z.B. Musterstadt")
                preis = st.text_input("Kaufpreis / Miete (in EUR)", placeholder="z.B. 450.000 €")
            with col2:
                flaeche = st.text_input("Wohnfläche / Grundstücksfläche", placeholder="z.B. 120 m² Wohnfläche")
                zimmer = st.text_input("Anzahl Zimmer", placeholder="z.B. 4 Zimmer")
                baujahr = st.text_input("Baujahr", placeholder="z.B. 2018")
                energieeffizienz = st.selectbox(
                    "Energieeffizienzklasse (optional)", 
                    ["Nicht angegeben / Optional", "A+", "A", "B", "C", "D", "E", "F", "G", "H"]
                )

            st.markdown("##### Ausstattungs-Highlights (Checkboxen)")
            cb_col1, cb_col2, cb_col3 = st.columns(3)
            with cb_col1:
                highlight_theressa = st.checkbox("Theressa-Ausstattung")
                highlight_balkon = st.checkbox("Balkon / Terrasse")
            with cb_col2:
                highlight_kueche = st.checkbox("Einbauküche")
                highlight_boden = st.checkbox("Fußbodenheizung")
            with cb_col3:
                highlight_parkplatz = st.checkbox("Tiefgaragenstellplatz")
                highlight_garten = st.checkbox("Eigener Garten")

            ausstattung_highlights = st.text_area("Weitere Ausstattungs-Highlights (Stichpunkte)", placeholder="z.B. Smart-Home System, bodentiefe Fenster...")
            sonstiges = st.text_area("Zusätzliche Angaben / Besonderheiten", placeholder="z.B. Sofort frei, provisionsfrei...")
            
            submit_button = st.form_submit_button("🚀 Exposé generieren")

        if submit_button:
            groq_key = st.secrets.get("GROQ_API_KEY", "")
            if not groq_key:
                st.error("❌ Kein Groq API Key in den Streamlit Secrets hinterlegt!")
            else:
                with st.spinner("Die KI generiert dein Exposé mit der gewählten Lebensphasen-Stimmung..."):
                    try:
                        client = Groq(api_key=groq_key)
                        
                        active_highlights = []
                        if highlight_theressa: active_highlights.append("Theressa-Ausstattung")
                        if highlight_balkon: active_highlights.append("Balkon / Terrasse")
                        if highlight_kueche: active_highlights.append("Einbauküche")
                        if highlight_boden: active_highlights.append("Fußbodenheizung")
                        if highlight_parkplatz: active_highlights.append("Tiefgaragenstellplatz")
                        if highlight_garten: active_highlights.append("Eigener Garten")
                        
                        combined_highlights = ", ".join(active_highlights)
                        if ausstattung_highlights:
                            combined_highlights += f", {ausstattung_highlights}"

                        energienutzung = energieeffizienz if energieeffizienz != "Nicht angegeben / Optional" else "Nicht angegeben"
                        epoch_instruction = get_epoch_prompt_instructions(stimmung_auswahl, expose_lang)

                        if expose_lang == "English":
                            prompt = f"""
                            You are an experienced, highly creative, and reputable real estate agent. 
                            {epoch_instruction}
                            Create a professional, appealing, and structured real estate exposé in English based on the following data. 
                            Use sections such as: 'Property Description', 'Features / Amenities', 'Location', and 'Miscellaneous'. Avoid repetition.

                            - Property Type: {immobilien_typ}
                            - Title: {objekt_titel}
                            - Location: {ort}
                            - Price: {preis}
                            - Area: {flaeche}
                            - Rooms: {zimmer}
                            - Year Built: {baujahr}
                            - Energy Efficiency Class: {energienutzung}
                            - Features & Highlights: {combined_highlights}
                            - Special Details: {sonstiges}
                            """
                        else:
                            prompt = f"""
                            Du bist ein erfahrener, hochkreativer und seriöser deutscher Immobilienmakler. 
                            {epoch_instruction}
                            Erstelle ein professionelles, ansprechendes und strukturiertes Immobilien-Exposé auf Basis der folgenden Daten. 
                            Verwende Abschnitte wie: 'Objektbeschreibung', 'Ausstattung', 'Lage' und 'Sonstiges'. Vermeide Wortwiederholungen oder Endlosschleifen.

                            - Objekttyp: {immobilien_typ}
                            - Titel: {objekt_titel}
                            - Ort / Lage: {ort}
                            - Preis: {preis}
                            - Fläche: {flaeche}
                            - Zimmer: {zimmer}
                            - Baujahr: {baujahr}
                            - Energieeffizienzklasse: {energienutzung}
                            - Ausstattung & Highlights: {combined_highlights}
                            - Besonderheiten: {sonstiges}
                            """

                        completion = client.chat.completions.create(
                            messages=[{"role": "user", "content": prompt}],
                            model="qwen/qwen3.6-27b",
                            max_completion_tokens=1000,
                            temperature=0.7
                        )

                        expose_ergebnis = completion.choices[0].message.content
                        st.markdown("---")
                        st.subheader("📄 Generiertes Exposé:")
                        st.markdown(expose_ergebnis)

                        save_expose_to_db(st.session_state.user_email, objekt_titel if objekt_titel else "Immobilien-Exposé", expose_ergebnis)
                        
                        pdf_bytes = create_pdf(expose_ergebnis, current_name, current_telefon, st.session_state.user_email, current_buero)
                        st.download_button(
                            label="📥 Als PDF herunterladen",
                            data=pdf_bytes,
                            file_name=f"expose_{objekt_titel.replace(' ', '_') if objekt_titel else 'immobilie'}.pdf",
                            mime="application/pdf"
                        )
                    except Exception as e:
                        st.error(f"Fehler bei der Generierung: {e}")

    elif menu == "⚙️ Einstellungen (My Account)":
        st.subheader("⚙️ Makler-Profil & Konto-Einstellungen")
        st.write("Verwalte hier deine optionalen Kontaktdaten für den Exposé-Footer, dein Profilbild sowie deine Zugangsdaten.")
        
        if current_profilbild and os.path.exists(current_profilbild):
            st.image(current_profilbild, width=150, caption="Dein aktuelles Profilbild")
            
        new_name = st.text_input("Dein vollständiger Name", value=current_name, placeholder="z.B. Max Mustermann")
        new_telefon = st.text_input("Deine Telefonnummer", value=current_telefon, placeholder="z.B. +49 (0) 551 1234567")
        new_buero = st.text_area("Büro-Adresse / Firmenname", value=current_buero, placeholder="z.B. Musterstraße 12, 37073 Göttingen")
        uploaded_file = st.file_uploader("Profilbild hochladen (PNG, JPG)", type=["png", "jpg", "jpeg"])
        
        if st.button("💾 Profildaten & Bild speichern"):
            image_path = current_profilbild
            if uploaded_file is not None:
                safe_email_name = st.session_state.user_email.replace("@", "_at_").replace(".", "_")
                file_extension = uploaded_file.name.split(".")[-1]
                image_path = os.path.join(UPLOAD_DIR, f"{safe_email_name}.{file_extension}")
                with open(image_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
            update_user_profile(st.session_state.user_email, new_name, new_telefon, new_buero, image_path)
            st.success("Profil erfolgreich gespeichert!")
            st.rerun()

        st.markdown("---")
        st.subheader("📧 E-Mail-Adresse ändern")
        new_email_input = st.text_input("Neue E-Mail-Adresse", placeholder="z.B. neue-email@gmail.com", key="settings_new_email")
        if st.button("🔄 E-Mail-Adresse aktualisieren", key="btn_update_email"):
            clean_new_email = new_email_input.strip().lower()
            if not clean_new_email or "@" not in clean_new_email or "." not in clean_new_email:
                st.error("⚠️ Bitte gib eine gültige E-Mail-Adresse ein.")
            else:
                existing = get_user(clean_new_email)
                if existing:
                    st.error("⚠️ Diese E-Mail-Adresse ist bereits von einem anderen Account belegt.")
                else:
                    update_user_email(st.session_state.user_email, clean_new_email)
                    st.session_state.user_email = clean_new_email
                    st.success("E-Mail-Adresse erfolgreich geändert!")
                    st.rerun()

        st.markdown("---")
        st.subheader("🔒 Passwort zurücksetzen / ändern")
        old_password_input = st.text_input("Aktuelles Passwort", type="password", placeholder="Altes Passwort", key="settings_old_pw")
        new_password_input = st.text_input("Neues Passwort", type="password", placeholder="Sicheres neues Passwort", key="settings_new_pw")
        
        if st.button("🔑 Passwort ändern", key="btn_update_pw"):
            if not old_password_input or not new_password_input:
                st.error("⚠️ Bitte altes und neues Passwort ausfüllen.")
            else:
                if user_data["password"] == hash_password(old_password_input):
                    update_user_password(st.session_state.user_email, new_password_input)
                    st.success("Passwort erfolgreich geändert!")
                else:
                    st.error("❌ Das eingegebene aktuelle Passwort ist falsch.")

    elif menu == "🔒 Datenschutzerklärung":
        st.subheader("🔒 Datenschutzerklärung")
        st.write("""
        **1. Datenschutz auf einen Blick**
        Die folgenden Hinweise geben einen einfachen Überblick darüber, was mit Ihren personenbezogenen Daten passiert, wenn Sie unsere Website besuchen.
        """)

    elif menu == "📝 Digitaler Notizblock":
        st.subheader("📝 Digitaler Notizblock für Besichtigungen")
        st.write("Schreibe hier während der Hausbesichtigung deine Notizen, Mängel oder Besonderheiten auf.")
        
        with st.form("note_form"):
            note_titel = st.text_input("Titel / Objekt", placeholder="z.B. Besichtigung Villa Müller")
            note_text = st.text_area("Notizen & Eindrücke", placeholder="z.B. Dachboden gut gedämmt...")
            note_submit = st.form_submit_button("💾 Notiz speichern")
            
            if note_submit:
                if not note_titel.strip() or not note_text.strip():
                    st.error("⚠️ Bitte Titel und Notiztext ausfüllen.")
                else:
                    save_note_to_db(st.session_state.user_email, note_titel, note_text)
                    st.success("Notiz erfolgreich gespeichert!")
                    st.rerun()
                    
        st.markdown("---")
        st.subheader("📂 Deine gespeicherten Notizen")
        notes = get_user_notes(st.session_state.user_email)
        if not notes:
            st.info("Du hast noch keine Notizen gespeichert.")
        else:
            for note_id, n_titel, n_inhalt, n_datum in notes:
                with st.expander(f"📌 {n_titel} ({n_datum})"):
                    st.write(n_inhalt)

    elif menu == "📂 Meine Exposés (Archiv)":
        st.subheader("📂 Bisher generierte Exposés")
        st.write("Hier findest du alle Immobilien-Texte, die du jemals erstellt hast.")
        exposes = get_user_exposes(st.session_state.user_email)
        if not exposes:
            st.info("Du hast noch keine Exposés generiert.")
        else:
            for exp_id, titel, inhalt, datum in exposes:
                with st.expander(f"🏡 {titel} ({datum})"):
                    st.markdown(inhalt)
                    pdf_data = create_pdf(inhalt, current_name, current_telefon, st.session_state.user_email, current_buero)
                    st.download_button(
                        label=f"📥 PDF erneut herunterladen (ID: {exp_id})",
                        data=pdf_data,
                        file_name=f"expose_{exp_id}.pdf",
                        mime="application/pdf",
                        key=f"dl_{exp_id}"
                    )

    elif menu == "📸 KI-Bilderkennung":
        st.subheader("📸 KI-gestützte Immobilien-Bilderkennung & Exposé-Generierung")
        st.info("Lade maximal **2 bis 3 Bilder** hoch. Wähle die gewünschte Lebensphasen-Stimmung und lass ein vollständiges Exposé daraus erstellen.")
        
        photo_lang = st.selectbox("Ausgabesprache / Language", ["Deutsch", "English"], key="photo_lang_select")
        
        st.markdown("##### 🎭 Stimmung & Lebensphase der Zielgruppe")
        stimmung_auswahl_photo = st.selectbox(
            "Wähle den Tonfall basierend auf der Lebensphase:",
            [
                "🚀 Junge Erwachsene / Urban Start-up (Modern, dynamisch, frisch)",
                "🏡 Familienphase / Nestbauer (Warm, sicher, kinderfreundlich)",
                "🏛️ Etablierte Lebensmitte / Karriere (Elegant, prestigeträchtig, exklusiv)",
                "☕ Ruhestand / Senioren (Ruhig, naturnah, barrierearm, entspannt)"
            ],
            key="photo_stimmung_select"
        )
        
        uploaded_images = st.file_uploader("Immobilien-Bilder hochladen (max. 3)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
        bild_hinweis = st.text_area("Zusätzliche Hinweise zu den Räumen (z.B. Preis, Lage, Zimmeranzahl)", placeholder="z.B. Kaufpreis 350.000 €, 3 Zimmer")
        
        if uploaded_images:
            if len(uploaded_images) > 3:
                st.warning("⚠️ Aus Performance- und API-Gründen werden nur die ersten 3 Bilder verarbeitet.")
                uploaded_images = uploaded_images[:3]
            
            st.markdown("### Ausgewählte Vorschau:")
            cols = st.columns(len(uploaded_images))
            for idx, img in enumerate(uploaded_images):
                with cols[idx]:
                    st.image(img, caption=f"Bild {idx+1}", use_container_width=True)
        
        if st.button("🚀 Bilder analysieren & vollständiges Exposé erstellen"):
            if not uploaded_images:
                st.error("⚠️ Bitte lade mindestens ein Bild hoch.")
            else:
                groq_key = st.secrets.get("GROQ_API_KEY", "")
                if not groq_key:
                    st.error("Kein Groq API Key hinterlegt.")
                else:
                    with st.spinner("Die KI analysiert die Bilder und erstellt das Exposé im gewählten Stil..."):
                        try:
                            client = Groq(api_key=groq_key)
                            epoch_instruction = get_epoch_prompt_instructions(stimmung_auswahl_photo, photo_lang)
                            
                            if photo_lang == "English":
                                instruction_text = (
                                    "You are a professional real estate agent. "
                                    f"{epoch_instruction} "
                                    "First, analyze the uploaded images and write a detailed room description. "
                                    "Second, based on these images and the additional notes, create a complete, professional, and structured real estate exposé "
                                    "(including Property Description, Features, Location, and Miscellaneous). Avoid repetition. "
                                    f"Additional agent notes: {bild_hinweis}"
                                )
                            else:
                                instruction_text = (
                                    "Du bist ein professioneller Immobilienmakler. "
                                    f"{epoch_instruction} "
                                    "Analysiere zuerst die hochgeladenen Bilder und verfasse eine detaillierte Raumbeschreibung. "
                                    "Erstelle im Anschluss basierend auf den Bildern und den zusätzlichen Hinweisen ein vollständiges, professionelles und strukturiertes "
                                    "Immobilien-Exposé (mit Abschnitten wie Objektbeschreibung, Ausstattung, Lage, Sonstiges). Vermeide Wortwiederholungen. "
                                    f"Zusätzliche Hinweise vom Makler: {bild_hinweis}"
                                )

                            content_payload = [
                                {
                                    "type": "text", 
                                    "text": instruction_text
                                }
                            ]
                            
                            for img_file in uploaded_images:
                                base64_data = encode_image_to_base64(img_file)
                                content_payload.append({
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_data}"
                                    }
                                })
                                
         client = Groq(api_key=groq_key)
        epoch_instruction = get_epoch_prompt_instructions(stimmung_auswahl_photo, photo_lang)
    
        system_prompt = (
            f"You are a professional real estate agent. "
            f"CRITICAL: Output ONLY the final property exposé. "
            f"No thinking process, no <think> tags, no meta-commentary whatsoever."
        )
    
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_payload}
            ],
            model="qwen/qwen3.6-27b",
            max_completion_tokens=400,
            temperature=0.7
        )
    
        expose_ergebnis = completion.choices[0].message.content
    
        st.markdown("---")
        st.subheader("📄 Generiertes Exposé & Bildanalyse:")
        st.markdown(expose_ergebnis)
    
        save_expose_to_db(st.session_state.user_email, "Exposé via KI-Bildanalyse", expose_ergebnis)
    
        pdf_bytes = create_pdf(expose_ergebnis, current_name, current_telefon, st.session_state.user_email, current_buero)
        st.download_button(
            label="📥 Als PDF herunterladen",
            data=pdf_bytes,
            file_name="expose_aus_bildern.pdf",
            mime="application/pdf"
)
    
if __name__ == "__main__":
main()
