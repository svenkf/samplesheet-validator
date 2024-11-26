# app.py

from flask import Flask, render_template, request, redirect, url_for, flash
import os
from werkzeug.utils import secure_filename
from validation.validator import validate_samplesheet
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='app.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

app = Flask(__name__)

app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')

UPLOAD_FOLDER = 'uploads/'
ALLOWED_EXTENSIONS = {'csv'}
VALIDATION_RULES_PATH = 'validation_rules.yaml'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'samplesheet' not in request.files:
            flash('No file part in the request.')
            return redirect(request.url)
        file = request.files['samplesheet']
        if file.filename == '':
            flash('No file selected for uploading.')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            flash('File successfully uploaded and is being validated.')

            try:
                issues = validate_samplesheet(filepath, VALIDATION_RULES_PATH)
                if any(issues.values()):
                    return render_template('results.html', issues=issues)
                else:
                    flash('Samplesheet validation passed! No issues found.')
                    return render_template('results.html', issues=None)
            except Exception as e:
                logging.error(f"An error occurred during validation: {e}")
                flash(f'An error occurred during validation: {e}')
                return redirect(request.url)
        else:
            flash('Allowed file types are CSV.')
            return redirect(request.url)
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
