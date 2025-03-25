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
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fallback_secret_key")

# Define folders
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
                flash("All fields are required.", "error")
                return render_template('input_form.html')

            # Check if a PDF file is uploaded
            if 'file' not in request.files or request.files['file'].filename == '':
                logging.error("No PDF file uploaded")
                flash("No PDF file uploaded.", "error")
                return render_template('input_form.html')

            pdf_file = request.files['file']
            if not pdf_file.filename.endswith('.pdf'):
                logging.error("Uploaded file is not a PDF")
                flash("Please upload a valid PDF file.", "error")
                return render_template('input_form.html')

            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
            logging.debug(f"Saving PDF to {pdf_path}")
            pdf_file.save(pdf_path)

            # Extract text from PDF
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    text = '\n'.join([page.extract_text() for page in pdf.pages if page.extract_text()])
                logging.debug(f"Extracted text from PDF: {text[:100]}...")
            except Exception as e:
                logging.error(f"Error extracting text from PDF: {e}")
                flash(f"Error reading the PDF file: {str(e)}", "error")
                return render_template('input_form.html')
            finally:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    logging.debug(f"Deleted temporary PDF file: {pdf_path}")

            # Generate summary
            if not text:
                logging.error("No text extracted from PDF")
                flash("No text extracted from PDF.", "error")
                return render_template('input_form.html')

            if not summarizer:
                logging.error("Summarizer not available")
                flash("Summarization model not available.", "error")
                return render_template('input_form.html')

            try:
                logging.debug("Generating summary")
                # Truncate text to avoid overloading the summarizer
                max_input_length = 1024  # Adjust as needed
                text = text[:max_input_length]
                summary = summarizer(text, max_length=250, min_length=70, do_sample=False)[0]['summary_text']
                logging.debug(f"Generated summary: {summary[:100]}...")
            except Exception as e:
                logging.error(f"Error generating summary: {e}")
                flash(f"Failed to generate summary: {str(e)}", "error")
                return render_template('input_form.html')

            # Extract medical terms using SciSpaCy
            medical_terms = []
            if nlp:
                try:
                    doc = nlp(text)
                    for ent in doc.ents:
                        if ent.label_ in ["DISEASE", "CHEMICAL"]:
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
                flash("Database connection failed.", "error")
                return render_template('input_form.html')

            cursor = db.cursor()
            try:
                # Truncate summary to avoid exceeding max_allowed_packet
                max_summary_length = 65535  # MySQL TEXT field max length
                summary = summary[:max_summary_length]
                medical_terms_json = json.dumps(medical_terms)
                # Removed user_id since we're not using authentication
                sql = "INSERT INTO summaries (patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                values = (patient_name, doctor_name, hospital_name, last_visited, date, summary, medical_terms_json)
                cursor.execute(sql, values)
                db.commit()
                summary_id = cursor.lastrowid  # Get the ID of the inserted summary
                logging.debug(f"Summary saved to database with ID: {summary_id}")
            except Exception as e:
                logging.error(f"Error saving to database: {e}")
                flash(f"Error saving summary to database: {str(e)}", "error")
                return render_template('input_form.html')
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

            # Store data in session for the summary page
            session['summary_id'] = summary_id
            session['summary_text'] = summary
            session['medical_terms'] = medical_terms
            session['summary_filename'] = summary_filename
            session['patient_name'] = patient_name
            session['doctor_name'] = doctor_name
            session['hospital_name'] = hospital_name
            session['last_visited'] = last_visited
            session['date'] = date

            flash("Summary generated successfully!", "success")
            return redirect(url_for('show_summary'))

        except Exception as e:
            logging.error(f"Unexpected error in home route: {e}")
            flash(f"Unexpected error: {str(e)}", "error")
            return render_template('input_form.html')

    return render_template('input_form.html')

@app.route('/summary')
def show_summary():
    # Retrieve the summary and related data from the session
    summary_id = session.get('summary_id')
    summary_text = session.get('summary_text', "No summary available.")
    medical_terms = session.get('medical_terms', [])
    filename = session.get('summary_filename')
    patient_name = session.get('patient_name')
    doctor_name = session.get('doctor_name')
    hospital_name = session.get('hospital_name')
    last_visited = session.get('last_visited')
    date = session.get('date')

    if not summary_id or not filename:
        flash("No summary found in session!", "error")
        return redirect(url_for('home'))

    return render_template('summary.html', summary=summary_text, medical_terms=medical_terms, filename=filename,
                           patient_name=patient_name, doctor_name=doctor_name, hospital_name=hospital_name,
                           last_visited=last_visited, date=date, summary_id=summary_id)

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

@app.route('/screenshot-to-pdf')
def screenshot_to_pdf():
    try:
        screenshot_path = os.path.join(app.config['SCREENSHOT_FOLDER'], "screenshot.png")
        cropped_screenshot_path = os.path.join(app.config['SCREENSHOT_FOLDER'], "cropped_screenshot.png")
        pdf_path = os.path.join(app.config['SCREENSHOT_FOLDER'], "screenshot.pdf")

        screenshot = pyautogui.screenshot()
        screen_width, screen_height = screenshot.size

        top_crop = int(screen_height * 0.17)
        left_crop = int(screen_width * 0.30)
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
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
