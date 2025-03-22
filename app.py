from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session
from transformers import pipeline
import pdfplumber
import os
import logging
import json
import mysql.connector
import pyautogui
from PIL import Image
from reportlab.pdfgen import canvas
import spacy

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_secret_key")
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['SUMMARY_FOLDER'] = os.path.join(os.getcwd(), 'summaries')
app.config['SCREENSHOT_FOLDER'] = os.path.join(os.getcwd(), 'screenshots')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SUMMARY_FOLDER'], exist_ok=True)
os.makedirs(app.config['SCREENSHOT_FOLDER'], exist_ok=True)

# Database Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # Replace with your MySQL password if set
    'database': 'hospital_db'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        logging.info("Database connection successful")
        return conn
    except Exception as e:
        logging.error(f"Database connection failed: {e}")
        return None

# Initialize summarization pipeline
try:
    summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    logging.info("Summarization model loaded successfully")
except Exception as e:
    logging.error(f"Error loading summarization model: {e}")
    summarizer = None

# Load SciSpaCy model for medical term extraction
try:
    nlp = spacy.load("en_ner_bc5cdr_md")
    logging.info("SciSpaCy model loaded successfully")
except Exception as e:
    logging.error(f"Error loading SciSpaCy model: {e}")
    nlp = None

# Simple dictionary for medical term explanations
MEDICAL_TERMS = {
    "hypertension": "High blood pressure, a condition where the force of blood against artery walls is too high, which can lead to heart problems.",
    "diabetes": "A condition where the body can't properly manage blood sugar levels, often requiring diet changes or medication.",
    "myocardial infarction": "A heart attack, which happens when blood flow to the heart is blocked, causing damage to the heart muscle.",
    "pneumonia": "An infection in the lungs that can cause cough, fever, and difficulty breathing, often treated with antibiotics.",
    "anemia": "A condition where you have fewer red blood cells than normal, which can make you feel tired or weak."
}

def explain_medical_term(term):
    """Explain a medical term in natural language."""
    term = term.lower()
    if term in MEDICAL_TERMS:
        return MEDICAL_TERMS[term]
    else:
        # Fallback: Generate a simple explanation (or use a generative model in the future)
        return f"{term} is a medical term that may relate to a specific condition, treatment, or symptom. Please consult a healthcare professional for a detailed explanation."

@app.route('/', methods=['GET', 'POST'])
def home():
    logging.debug("Entering home route")
    if request.method == 'POST':
        logging.debug("Received POST request")
        try:
            # Get form data
            patient_name = request.form.get('patient_name')
            doctor_name = request.form.get('doctor_name')
            hospital_name = request.form.get('hospital_name')
            last_visited = request.form.get('last_visited')
            date = request.form.get('date')
            text = request.form.get('text', '')

            logging.debug(f"Form data: patient_name={patient_name}, doctor_name={doctor_name}, hospital_name={hospital_name}, last_visited={last_visited}, date={date}")

            # Validate required fields
            if not all([patient_name, doctor_name, hospital_name, last_visited, date]):
                logging.error("Missing required fields")
                return render_template('input_form.html', error="All fields are required."), 400

            # Check if a PDF file is uploaded
            if 'file' not in request.files or request.files['file'].filename == '':
                logging.error("No PDF file uploaded")
                return render_template('input_form.html', error="No PDF file uploaded."), 400

            pdf_file = request.files['file']
            if not pdf_file.filename.endswith('.pdf'):
                logging.error("Uploaded file is not a PDF")
                return render_template('input_form.html', error="Please upload a valid PDF file."), 400

            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
            logging.debug(f"Saving PDF to {pdf_path}")
            pdf_file.save(pdf_path)

            # Extract text from PDF
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    text = '\n'.join([page.extract_text() for page in pdf.pages if page.extract_text()])
                logging.debug(f"Extracted text from PDF: {text[:100]}...")  # Log first 100 chars
            except Exception as e:
                logging.error(f"Error extracting text from PDF: {e}")
                return render_template('input_form.html', error=f"Error reading the PDF file: {str(e)}"), 500
            finally:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    logging.debug(f"Deleted temporary PDF file: {pdf_path}")

            # Generate summary
            if not text:
                logging.error("No text extracted from PDF")
                return render_template('input_form.html', error="No text extracted from PDF."), 400

            if not summarizer:
                logging.error("Summarizer not available")
                return render_template('input_form.html', error="Summarization model not available."), 500

            try:
                logging.debug("Generating summary")
                # Truncate text to avoid overloading the summarizer
                max_input_length = 1024  # Adjust as needed
                text = text[:max_input_length]
                summary = summarizer(text, max_length=250, min_length=70, do_sample=False)[0]['summary_text']
                logging.debug(f"Generated summary: {summary[:100]}...")
            except Exception as e:
                logging.error(f"Error generating summary: {e}")
                return render_template('input_form.html', error=f"Failed to generate summary: {str(e)}"), 500

            # Extract medical terms using SciSpaCy
            medical_terms = []
            if nlp:
                try:
                    doc = nlp(text)
                    # Extract entities (diseases and chemicals)
                    for ent in doc.ents:
                        if ent.label_ in ["DISEASE", "CHEMICAL"]:  # Focus on medical terms
                            term = ent.text
                            explanation = explain_medical_term(term)
                            medical_terms.append({"term": term, "explanation": explanation})
                    logging.debug(f"Extracted medical terms: {medical_terms}")
                except Exception as e:
                    logging.error(f"Error extracting medical terms: {e}")
                    medical_terms = []
            else:
                logging.warning("SciSpaCy model not available, skipping medical term extraction")

            # Save the summary to the database
            db = get_db_connection()
            if not db:
                return render_template('input_form.html', error="Database connection failed."), 500

            cursor = db.cursor()
            try:
                # Truncate summary to avoid exceeding max_allowed_packet
                max_summary_length = 65535  # MySQL TEXT field max length
                summary = summary[:max_summary_length]
                # Include medical terms in the database (as JSON string)
                medical_terms_json = json.dumps(medical_terms)
                sql = "INSERT INTO summaries (patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms, user_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                values = (patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms_json, session.get('user_id', None))
                cursor.execute(sql, values)
                db.commit()
                logging.debug("Summary saved to database")
            except Exception as e:
                logging.error(f"Error saving to database: {e}")
                return render_template('input_form.html', error=f"Error saving summary to database: {str(e)}"), 500
            finally:
                cursor.close()
                db.close()

            # Save the summary to a file
            try:
                summary_filename = f"{patient_name.replace(' ', '')}{doctor_name.replace(' ', '')}{hospital_name.replace(' ', '')}{last_visited.replace(' ', '')}{date}.json"
                summary_path = os.path.join(app.config['SUMMARY_FOLDER'], summary_filename)
                logging.debug(f"Attempting to save summary to: {summary_path}")
                with open(summary_path, 'w', encoding='utf-8') as file:
                    json.dump({
                        "patient_name": patient_name,
                        "doctor_name": doctor_name,
                        "hospital_name": hospital_name,
                        "last_visited": last_visited,
                        "date": date,
                        "summary": summary,
                        "medical_terms": medical_terms
                    }, file, ensure_ascii=False)
                logging.debug(f"Summary saved to file: {summary_path}")
            except Exception as e:
                logging.error(f"Error saving summary to file: {e}")
                # Not critical, continue even if file save fails

            # Redirect to downloads page instead of rendering summary.html
            flash("Summary generated successfully!", "success")
            return redirect(url_for('downloads'))

        except Exception as e:
            logging.error(f"Unexpected error in home route: {e}")
            return render_template('input_form.html', error=f"Unexpected error: {str(e)}"), 500
    
    return render_template('input_form.html')

@app.route('/downloads')
def downloads():
    db = get_db_connection()
    if not db:
        flash("Database connection failed!", "error")
        return render_template('downloads.html', summaries=[])

    cursor = db.cursor()
    try:
        cursor.execute("SELECT id, patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms FROM summaries ORDER BY created_at DESC")
        summaries = cursor.fetchall()
        # Parse medical_terms JSON for each summary
        summaries = [(s[0], s[1], s[2], s[3], s[4], s[5], s[6], json.loads(s[7]) if s[7] else []) for s in summaries]
        logging.debug(f"Summaries fetched for downloads: {summaries}")
    except Exception as e:
        logging.error(f"Error fetching summaries: {e}")
        flash("Failed to load summaries.", "error")
        summaries = []
    finally:
        cursor.close()
        db.close()

    return render_template('downloads.html', summaries=summaries)

@app.route('/download/<int:id>')
def download_file(id):
    db = get_db_connection()
    if not db:
        flash("Database connection failed!", "error")
        return redirect(url_for('downloads'))

    cursor = db.cursor()
    try:
        cursor.execute("SELECT patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms FROM summaries WHERE id = %s", (id,))
        summary = cursor.fetchone()
        logging.debug(f"Summary fetched for download (id={id}): {summary}")
        if not summary:
            flash("Summary not found!", "error")
            return redirect(url_for('downloads'))

        patient_name, doctor_name, hospital_name, last_visited, date, summary_text, medical_terms_json = summary
        medical_terms = json.loads(medical_terms_json) if medical_terms_json else []
        summary_filename = f"{patient_name.replace(' ', '')}{doctor_name.replace(' ', '')}{hospital_name.replace(' ', '')}{last_visited.replace(' ', '')}{date}.json"
        summary_path = os.path.join(app.config['SUMMARY_FOLDER'], summary_filename)
        logging.debug(f"Looking for summary file at: {summary_path}")

        # Ensure the file exists
        if not os.path.exists(summary_path):
            logging.warning(f"Summary file not found at {summary_path}, creating it now")
            with open(summary_path, 'w', encoding='utf-8') as file:
                json.dump({
                    "patient_name": patient_name,
                    "doctor_name": doctor_name,
                    "hospital_name": hospital_name,
                    "last_visited": last_visited,
                    "date": date,
                    "summary": summary_text,
                    "medical_terms": medical_terms
                }, file, ensure_ascii=False)
            logging.debug(f"Created summary file at: {summary_path}")

        return send_file(summary_path, as_attachment=True, download_name=summary_filename)
    except Exception as e:
        logging.error(f"Error downloading file: {e}")
        flash(f"Failed to download file: {str(e)}", "error")
        return redirect(url_for('downloads'))
    finally:
        cursor.close()
        db.close()

@app.route('/delete/<int:id>')
def delete_file(id):
    db = get_db_connection()
    if not db:
        flash("Database connection failed!", "error")
        return redirect(url_for('downloads'))

    cursor = db.cursor()
    try:
        cursor.execute("SELECT patient_name, doctor_name, hospital_name, last_visited, date FROM summaries WHERE id = %s", (id,))
        summary = cursor.fetchone()
        logging.debug(f"Summary fetched for deletion (id={id}): {summary}")
        if summary:
            patient_name, doctor_name, hospital_name, last_visited, date = summary
            summary_filename = f"{patient_name.replace(' ', '')}{doctor_name.replace(' ', '')}{hospital_name.replace(' ', '')}{last_visited.replace(' ', '')}{date}.json"
            file_path = os.path.join(app.config['SUMMARY_FOLDER'], summary_filename)
            logging.debug(f"Attempting to delete file at: {file_path}")
            if os.path.exists(file_path):
                os.remove(file_path)
                logging.debug(f"Deleted file: {file_path}")
            else:
                logging.warning(f"File not found at: {file_path}")
            cursor.execute("DELETE FROM summaries WHERE id = %s", (id,))
            db.commit()
            logging.debug(f"Deleted summary from database (id={id})")
            flash("Summary deleted successfully!", "success")
        else:
            flash("Summary not found!", "error")
    except Exception as e:
        logging.error(f"Error deleting summary: {e}")
        flash(f"Failed to delete summary: {str(e)}", "error")
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('downloads'))

@app.route('/delete_summary/<int:id>')
def delete_summary(id):
    db = get_db_connection()
    if not db:
        flash("Database connection failed!", "error")
        return redirect(url_for('downloads'))

    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM summaries WHERE id = %s", (id,))
        db.commit()
        flash("Summary deleted successfully!", "success")
    except Exception as e:
        logging.error(f"Error deleting summary: {e}")
        flash("Failed to delete summary.", "error")
    finally:
        cursor.close()
        db.close()

    return redirect(url_for('downloads'))

@app.route('/user_reports')
def user_reports():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db_connection()
    if not db:
        flash("Database connection failed!", "error")
        return render_template('user_reports.html', reports=[])

    cursor = db.cursor()
    try:
        user_id = session['user_id']
        cursor.execute("SELECT id, patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms FROM summaries WHERE user_id = %s", (user_id,))
        reports = cursor.fetchall()
        # Parse medical_terms JSON for each report
        reports = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], json.loads(r[7]) if r[7] else []) for r in reports]
    except Exception as e:
        logging.error(f"Error fetching user reports: {e}")
        flash("Failed to load user reports.", "error")
        reports = []
    finally:
        cursor.close()
        db.close()

    return render_template('user_reports.html', reports=reports)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db_connection()
        if not db:
            flash("Database connection failed!", "error")
            return render_template('login.html')

        cursor = db.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE email = %s AND password = %s", (email, password))
            user = cursor.fetchone()
            if user:
                session['user_id'] = user[0]  # Assuming 'id' is the first column
                flash("Login successful!", "success")
                return redirect(url_for('home'))
            else:
                flash("Login failed. Invalid email or password.", "error")
                return render_template('login.html')
        except Exception as e:
            logging.error(f"Error during login: {e}")
            flash("An error occurred during login.", "error")
            return render_template('login.html')
        finally:
            cursor.close()
            db.close()
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("Logged out successfully!", "success")
    return redirect(url_for('home'))

@app.route('/screenshot-to-pdf')
def screenshot_to_pdf():
    try:
        screenshot_path = os.path.join(app.config['SCREENSHOT_FOLDER'], "screenshot.png")
        cropped_screenshot_path = os.path.join(app.config['SCREENSHOT_FOLDER'], "cropped_screenshot.png")
        pdf_path = os.path.join(app.config['SCREENSHOT_FOLDER'], "screenshot.pdf")

        screenshot = pyautogui.screenshot()
        screen_width, screen_height = screenshot.size

        top_crop = int(screen_height * 0.17)
        left_crop = int(screen_width * 0.30)  # Fixed negative value
        right_crop = int(screen_width * 0.28)
        bottom_crop = int(screen_height * 0.09)

        left = max(0, left_crop)
        top = top_crop
        right = screen_width - right_crop
        bottom = screen_height - bottom_crop

        if right <= left or bottom <= top:
            raise ValueError("Invalid cropping dimensions. Check screen resolution")

        cropped_screenshot = screenshot.crop((left, top, right, bottom))
        cropped_screenshot.save(cropped_screenshot_path)

        img = Image.open(cropped_screenshot_path)
        pdf = canvas.Canvas(pdf_path, pagesize=img.size)
        pdf.drawInlineImage(cropped_screenshot_path, 0, 0, width=img.width, height=img.height)
        pdf.showPage()
        pdf.save()

        return send_file(pdf_path, as_attachment=True)

    except Exception as e:
        logging.error(f"Error generating screenshot PDF: {str(e)}")
        return f"An error occurred: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)