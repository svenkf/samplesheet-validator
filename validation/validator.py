# validator.py

import yaml
import re
import os
import sys
import json
import traceback
import logging
import difflib
from collections import defaultdict  # For grouping errors
from sample_sheet import SampleSheet, Sample
from slims.slims import Slims
from slims.criteria import equals, conjunction
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='validation.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def load_validation_rules(rules_path):
    """Load validation rules from a YAML configuration file."""
    try:
        with open(rules_path, 'r') as file:
            rules = yaml.safe_load(file)
        return rules
    except FileNotFoundError:
        logging.error(f"Validation rules file not found: '{rules_path}'.")
        raise
    except yaml.YAMLError as e:
        logging.error(f"Failed to parse YAML file '{rules_path}': {e}")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading validation rules: {e}")
        traceback.print_exc()
        raise

def validate_samplesheet_structure(ss, required_sections, issues):
    """Validate the presence of required sections in the samplesheet."""
    section_issues = issues['[Header]']
    for section in required_sections:
        if section == 'Header' and not ss.Header:
            section_issues.append("[Header] section is missing or empty.")
        elif section == 'Reads' and not ss.Reads:
            section_issues.append("[Reads] section is missing or empty.")
        elif section == 'Settings' and not ss.Settings:
            section_issues.append("[Settings] section is missing or empty.")
        elif section == 'Data' and not ss.samples:
            section_issues.append("[Data] section is missing or empty.")

def validate_required_fields(ss, required_fields, issues):
    """Validate presence of required fields within each section."""
    header_issues = issues['[Header]']
    data_issues = issues['[Data]']
    missing_fields_samples = defaultdict(list)
    missing_header_fields = []

    # Validate [Header] fields
    header_fields = ss.Header or {}
    for field in required_fields.get('Header', []):
        if field not in header_fields or not str(header_fields[field]).strip():
            missing_header_fields.append(f"'{field}' is missing or empty.")

    if missing_header_fields:
        message = f"Missing Fields:\n\t" + "\n\t".join(missing_header_fields)
        header_issues.append(message)

    # Validate [Data] fields
    for idx, sample in enumerate(ss.samples, start=1):
        for field in required_fields.get('Data', []):
            value = getattr(sample, field, None)
            if value is None or not str(value).strip():
                sample_id = sample.Sample_ID or f"Sample {idx}"
                missing_fields_samples[field].append(sample_id)

    for field, sample_ids in missing_fields_samples.items():
        data_issues.append(f"Missing or empty required field '{field}':\n\t" + "\n\t".join(sample_ids))

    # Ensure Sample_ID equals Sample_Name
    mismatch_samples = []
    for idx, sample in enumerate(ss.samples, start=1):
        if sample.Sample_ID != sample.Sample_Name:
            mismatch_samples.append(f"Sample_ID: {sample.Sample_ID}, Sample_Name: {sample.Sample_Name}")
    if mismatch_samples:
        data_issues.append(f"Sample_ID does not match Sample_Name. Both should be identical:\n\t" + "\n\t".join(mismatch_samples))

def validate_allowed_characters(ss, allowed_characters, issues):
    """Validate that fields contain only allowed characters."""
    data_issues = issues['[Data]']
    field_errors = defaultdict(list)
    for idx, sample in enumerate(ss.samples, start=1):
        for field, rules in allowed_characters.items():
            pattern = rules.get('pattern', '')
            description = rules.get('description', 'allowed characters')
            value = getattr(sample, field, '') or ''
            value = value.strip()
            if value:
                invalid_chars = re.findall(f'[^{pattern}]', value)
                if invalid_chars:
                    unique_invalid_chars = set(invalid_chars)
                    formatted_invalid_chars = ', '.join(f"'{char}'" for char in unique_invalid_chars)
                    error_message = f"{field} contains invalid characters: {formatted_invalid_chars}. Allowed characters: {description}."
                    field_errors[error_message].append(f"{field}: {value}")
    for error_message, samples in field_errors.items():
        data_issues.append(f"{error_message}:\n\t" + "\n\t".join(samples))

def assign_pipeline(sample, pipelines, typo_samples):
    """Assign a pipeline to the sample based on Description keywords or Sample_ID regex."""
    description = sample.Description.lower() if sample.Description else ''
    sample_id = sample.Sample_ID

    assigned_pipelines = []
    typo_detected_pipelines = []

    for pipeline_name, rules in pipelines.items():
        if rules['type'] == 'keyword':
            keywords = [kw.lower() for kw in rules['keywords']]
            exact_match = any(kw in description for kw in keywords)
            if exact_match:
                assigned_pipelines.append(pipeline_name)
                continue

            if pipeline_name in ['FLT3-ITD', 'NPM1']:
                close_matches = difflib.get_close_matches(description, keywords, cutoff=0.6)
                if close_matches:
                    typo_samples.append(f"'{sample.Description}'. Did you mean '{close_matches[0]}'?")
                    assigned_pipelines.append(pipeline_name)
                    typo_detected_pipelines.append(pipeline_name)
                    continue

                words_in_description = re.findall(r'\b[\w\-_]+\b', description)
                for word in words_in_description:
                    close_matches = difflib.get_close_matches(word, keywords, cutoff=0.6)
                    if close_matches:
                        typo_samples.append(f"'{sample.Description}'. Did you mean '{close_matches[0]}'?")
                        assigned_pipelines.append(pipeline_name)
                        typo_detected_pipelines.append(pipeline_name)
                        break

        elif rules['type'] == 'regex':
            if re.match(rules['sample_id_regex'], sample_id):
                assigned_pipelines.append(pipeline_name)

    sample.typo_detected_pipelines = typo_detected_pipelines

    if len(assigned_pipelines) > 1:
        return "Multiple Pipelines: " + ", ".join(assigned_pipelines)
    elif len(assigned_pipelines) == 1:
        return assigned_pipelines[0]
    else:
        return "Unknown Pipeline"

def validate_pipeline_rules(ss, pipelines, issues, file_path):
    """Validate pipeline-specific rules for each sample."""
    data_issues = issues['[Data]']
    filename_issues = issues['Filename']
    settings_issues = issues['[Settings]']
    filename_check_required = False
    settings_check_required = False

    typo_samples = []
    missing_keyword_samples = defaultdict(list)

    for idx, sample in enumerate(ss.samples, start=1):
        pipeline = assign_pipeline(sample, pipelines, typo_samples)
        sample.pipeline = pipeline

        if pipeline.startswith("Multiple Pipelines"):
            data_issues.append(f"Sample_ID: {sample.Sample_ID} - Assigned to multiple pipelines: {pipeline}. Please clarify the Description.")
            continue

        if pipeline == "Unknown Pipeline":
            continue

        pipeline_rules = pipelines[pipeline]

        if pipeline_rules['type'] == 'keyword' and pipeline_rules.get('description_check', False):
            if pipeline not in sample.typo_detected_pipelines:
                keywords_present = [kw for kw in pipeline_rules['keywords'] if kw.lower() in (sample.Description or '').lower()]
                if not keywords_present:
                    missing_keyword_samples[pipeline].append(f"Sample_ID: {sample.Sample_ID}, Description: {sample.Description}")

        if pipeline == 'GMS-Myeloid':
            filename_check_required = True
            settings_check_required = True

        if pipeline == 'COVID':
            pattern = pipeline_rules.get('sample_id_regex', '')
            invalid_id_samples = []
            invalid_name_samples = []
            if not re.match(pattern, sample.Sample_ID):
                invalid_id_samples.append(f"Sample_ID: {sample.Sample_ID}")
            if not re.match(pattern, sample.Sample_Name):
                invalid_name_samples.append(f"Sample_Name: {sample.Sample_Name}")
            if invalid_id_samples:
                data_issues.append(f"Sample_ID does not match the required pattern for pipeline 'COVID'. Expected format: 'D[A-Z]2[0-4]XXXXXX':\n\t" + "\n\t".join(invalid_id_samples))
            if invalid_name_samples:
                data_issues.append(f"Sample_Name does not match the required pattern for pipeline 'COVID'. Expected format: 'D[A-Z]2[0-4]XXXXXX':\n\t" + "\n\t".join(invalid_name_samples))

    for pipeline, samples in missing_keyword_samples.items():
        data_issues.append(f"Description does not contain required keyword(s) for pipeline '{pipeline}':\n\t" + "\n\t".join(samples))

    if typo_samples:
        typo_messages = ["\t" + msg for msg in typo_samples]
        data_issues.append("Possible typo in Description:\n" + "\n".join(typo_messages))

    if filename_check_required:
        actual_filename = os.path.basename(file_path)
        if actual_filename != 'SampleSheet.csv':
            filename_issues.append(f"For 'GMS-Myeloid' pipeline, the samplesheet must be named 'SampleSheet.csv', but got '{actual_filename}'.")

    if settings_check_required:
        required_settings_fields = [
            'Adapter',
            'AdapterRead2',
            'Read1UMILength',
            'Read2UMILength',
            'Read1StartFromCycle',
            'Read2StartFromCycle'
        ]
        settings_fields = ss.Settings or {}
        missing_fields = [field for field in required_settings_fields if field not in settings_fields or not str(settings_fields[field]).strip()]
        if missing_fields:
            settings_issues.append(f"Missing Fields required for the 'GMS-Myeloid' pipeline:\n\t" + "\n\t".join(missing_fields))

def load_slims_credentials():
    """Load SLIMS credentials from environment variables."""
    try:
        slims_credentials = {
            'url': os.getenv('SLIMS_URL'),
            'user': os.getenv('SLIMS_USER'),
            'password': os.getenv('SLIMS_PASSWORD')
        }
        if not all(slims_credentials.values()):
            logging.error("SLIMS credentials are not fully set in environment variables.")
            raise ValueError("Incomplete SLIMS credentials.")
        return slims_credentials
    except Exception as e:
        logging.error(f"An error occurred while loading SLIMS credentials: {e}")
        traceback.print_exc()
        raise

def connect_slims(slims_credentials):
    """Connect to SLIMS with given credentials."""
    instance = 'query'
    url = slims_credentials['url']
    user = slims_credentials['user']
    password = slims_credentials['password']
    return Slims(instance, url, user, password)

def sample_has_fastq(slims, sample_id):
    """Check if a sample with the given Sample_ID already has a fastq object in SLIMS."""
    try:
        # Content type 22 corresponds to fastq objects in SLIMS
        records = slims.fetch('Content', conjunction()
                              .add(equals('cntn_id', sample_id))
                              .add(equals('cntn_fk_contentType', 22)))
        return bool(records)
    except Exception as e:
        logging.error(f"Error querying SLIMS for Sample_ID '{sample_id}': {e}")
        traceback.print_exc()
        return False

def validate_slims_samples(ss, slims, issues):
    """Check each sample in the samplesheet against SLIMS to see if a fastq object already exists."""
    slims_issues = issues['SLIMS']
    existing_samples = []
    for idx, sample in enumerate(ss.samples, start=1):
        sample_id = sample.Sample_ID
        if sample_has_fastq(slims, sample_id):
            existing_samples.append(sample_id)
    if existing_samples:
        slims_issues.append("Sample_ID already has a fastq object in SLIMS:\n\t" + "\n\t".join(existing_samples))

def validate_samplesheet(file_path, rules_path):
    """Main validation function."""
    issues = defaultdict(list)

    # Load validation rules
    rules = load_validation_rules(rules_path)

    # Parse the samplesheet
    try:
        ss = SampleSheet(file_path)
    except Exception as e:
        issues['Parsing Error'].append(str(e))
        logging.error(f"Error parsing samplesheet '{file_path}': {e}")
        traceback.print_exc()
        return issues

    # Validate the structure
    required_sections = rules.get('required_sections', [])
    validate_samplesheet_structure(ss, required_sections, issues)

    # Validate required fields
    required_fields = rules.get('required_fields', {})
    validate_required_fields(ss, required_fields, issues)

    # Validate allowed characters
    allowed_chars = rules.get('allowed_characters', {})
    validate_allowed_characters(ss, allowed_chars, issues)

    # Pipeline-specific validations
    pipelines = rules.get('pipelines', {})
    if pipelines:
        validate_pipeline_rules(ss, pipelines, issues, file_path)

    # Load SLIMS credentials and connect
    try:
        slims_credentials = load_slims_credentials()
        slims = connect_slims(slims_credentials)
    except Exception as e:
        issues['SLIMS Connection Error'].append(str(e))
        logging.error(f"Failed to connect to SLIMS: {e}")
        return issues

    # Validate samples against SLIMS
    validate_slims_samples(ss, slims, issues)

    return issues
