import yaml
import re
import os
import traceback
import logging
import difflib
from collections import defaultdict
from sample_sheet import SampleSheet, Sample
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

logging.basicConfig(
    filename='validation.log',
    filemode='a',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def load_validation_rules(rules_path):
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
    header_issues = issues['[Header]']
    data_issues = issues['[Data]']
    missing_fields_samples = defaultdict(list)
    missing_header_fields = []

    # Validate [Header]
    header_fields = ss.Header or {}
    for field in required_fields.get('Header', []):
        if field not in header_fields or not str(header_fields[field]).strip():
            missing_header_fields.append(f"'{field}' is missing or empty.")

    if missing_header_fields:
        message = f"Missing Fields:\n\t" + "\n\t".join(missing_header_fields)
        header_issues.append(message)

    # Validate [Data]
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
    for sample in ss.samples:
        if sample.Sample_ID != sample.Sample_Name:
            mismatch_samples.append(f"Sample_ID: {sample.Sample_ID}, Sample_Name: {sample.Sample_Name}")
    if mismatch_samples:
        data_issues.append("Sample_ID does not match Sample_Name. Both should be identical:\n\t" + "\n\t".join(mismatch_samples))

def validate_allowed_characters(ss, allowed_characters, issues):
    data_issues = issues['[Data]']
    field_errors = defaultdict(list)
    for sample in ss.samples:
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

# Custom detection functions
def is_wopr_sample(description):
    parts = description.split('_')
    if len(parts) == 6:
        _, gender, pcr, trio_role, trio_id, priority = parts
        if trio_role.lower() not in ['t', 'n']:
            return True
    return False

def is_somatic_sample(description):
    parts = description.split('_')
    if len(parts) == 6:
        _, gender, pcr, tn_role, tn_id, priority = parts
        if tn_role.lower() in ['t', 'n']:
            return True
    return False

def validate_wopr_sample(sample, issues):
    data_issues = issues['[Data]']
    description = sample.Description or ''
    parts = description.split('_')
    if len(parts) != 6:
        data_issues.append(
            f"Sample '{sample.Sample_ID}': WOPR Description must have 6 parts separated by underscores."
        )
        return
    _, gender, pcr, trio_role, trio_id, priority = parts

    allowed_gender_values = ['M', 'F', 'U']
    if gender.upper() not in allowed_gender_values:
        data_issues.append(
            f"Sample '{sample.Sample_ID}': Invalid gender '{gender}' in WOPR Description. "
            f"Allowed values: {', '.join(allowed_gender_values)}."
        )

    if pcr not in ['00', '01', '']:
        data_issues.append(
            f"Sample '{sample.Sample_ID}': Invalid PCR value '{pcr}' in WOPR Description. "
            "Allowed values: '00', '01' or empty."
        )

    allowed_trio_role_values = ['far', 'mor', 'sy', 'sl', 'i']
    if trio_role not in allowed_trio_role_values:
        data_issues.append(
            f"Sample '{sample.Sample_ID}': Invalid trio role '{trio_role}' in WOPR Description. "
            f"Allowed values: {', '.join(allowed_trio_role_values)}."
        )

def validate_somatic_sample(sample, issues):
    data_issues = issues['[Data]']
    description = sample.Description or ''
    parts = description.split('_')
    if len(parts) != 6:
        data_issues.append(f"Sample '{sample.Sample_ID}': Somatic Description must have 6 parts separated by underscores.")
        return
    _, gender, pcr, tn_role, tn_id, priority = parts

    if gender.lower() not in ['m', 'f', 'u']:
        data_issues.append(f"Sample '{sample.Sample_ID}': Invalid gender '{gender}' in Somatic Description. Allowed values: M, F, U.")

    if pcr not in ['00','01', '']:
        data_issues.append(
            f"Sample '{sample.Sample_ID}': Invalid PCR value '{pcr}' in Somatic Description. "
            "Allowed values: '00', '01' or empty."
        )

    if tn_role.lower() not in ['t', 'n']:
        data_issues.append(
            f"Sample '{sample.Sample_ID}': TN role '{tn_role}' must be 't' or 'n' in Somatic Description."
        )

def validate_index_uniqueness(ss, issues):
    data_issues = issues['[Data]']
    for sample in ss.samples:
        index1 = sample.index.strip() if sample.index else ''
        index2 = sample.index2.strip() if sample.index2 else ''
        if index1 == index2 and index1 != '':
            data_issues.append(
                f"Sample '{sample.Sample_ID}': index (i7) and index2 (i5) are the same ('{index1}'). They must be different."
            )

def assign_pipeline(sample, pipelines, typo_samples):
    """Assign a pipeline to the sample based on Description keywords or custom functions."""
    description = sample.Description.lower() if sample.Description else ''
    assigned_pipelines = []
    typo_detected_pipelines = []

    for pipeline_name, rules in pipelines.items():
        if rules['type'] == 'keyword':
            keywords = [kw.lower() for kw in rules['keywords']]
            exact_match = any(kw in description for kw in keywords)
            if exact_match:
                assigned_pipelines.append(pipeline_name)
                continue

            # Check for typos in the description
            words_in_description = re.findall(r'\b[\w\-_]+\b', description)
            for word in words_in_description:
                close_matches = difflib.get_close_matches(word, keywords, cutoff=0.5)
                if close_matches:
                    typo_samples.append(f"'{sample.Description}'. Did you mean '{close_matches[0]}'?")
                    assigned_pipelines.append(pipeline_name)
                    typo_detected_pipelines.append(pipeline_name)
                    break

        elif rules['type'] == 'custom':
            function_name = rules['function']
            detection_function = globals().get(function_name)
            if detection_function and detection_function(description):
                assigned_pipelines.append(pipeline_name)

    sample.typo_detected_pipelines = typo_detected_pipelines

    if len(assigned_pipelines) > 1:
        return "Multiple Pipelines: " + ", ".join(assigned_pipelines)
    elif len(assigned_pipelines) == 1:
        return assigned_pipelines[0]
    else:
        return "Unknown Pipeline"

def validate_pipeline_rules(ss, pipelines, issues, file_path):
    data_issues = issues['[Data]']
    filename_issues = issues['Filename']
    settings_issues = issues['[Settings]']
    settings_check_required = False

    typo_samples = []
    missing_keyword_samples = defaultdict(list)
    gms_myeloid_assigned = False
    pipeline_pattern_issues = defaultdict(list)  # Changed to list of sample IDs

    header_date_str = ss.Header.get('Date', '').strip()
    if not header_date_str:
        issues['[Header]'].append("Header 'Date' field is missing or empty.")
        header_date_formatted = None
    else:
        try:
            header_date_obj = datetime.strptime(header_date_str, '%Y-%m-%d')
            header_date_formatted = header_date_obj.strftime('%y%m%d')
        except ValueError:
            issues['[Header]'].append(f"Header 'Date' '{header_date_str}' is not in 'YYYY-MM-DD' format.")
            header_date_formatted = None

    for sample in ss.samples:
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

        sample_id_patterns = pipeline_rules.get('sample_id_patterns', [])
        sample_id_display_patterns = pipeline_rules.get('sample_id_display_patterns', [])

        if sample_id_patterns:
            date_match = None
            for pattern in sample_id_patterns:
                m = re.match(pattern, sample.Sample_ID)
                if m:
                    date_match = m.group(1)
                    break
            if not date_match:
                expected = sample_id_display_patterns if sample_id_display_patterns else sample_id_patterns
                pipeline_pattern_issues[pipeline].append(sample.Sample_ID)
            else:
                if header_date_formatted and date_match != header_date_formatted:
                    data_issues.append(
                        f"Date in Sample_ID '{sample.Sample_ID}' does not match the 'Date' in [Header]. "
                        f"Sample_ID date: {date_match}, Header date: {header_date_formatted}."
                    )
                elif not header_date_formatted:
                    data_issues.append(
                        f"Cannot validate date in Sample_ID '{sample.Sample_ID}' because Header 'Date' is invalid or missing."
                    )

        if pipeline == 'WOPR':
            validate_wopr_sample(sample, issues)
        elif pipeline == 'Somatic':
            validate_somatic_sample(sample, issues)

        if pipeline == 'GMS-Myeloid':
            gms_myeloid_assigned = True
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
                data_issues.append(f"Sample_ID does not match the required pattern for pipeline 'COVID'. Expected format: '{pattern}':\n\t" + "\n\t".join(invalid_id_samples))
            if invalid_name_samples:
                data_issues.append(f"Sample_Name does not match the required pattern for pipeline 'COVID'. Expected format: '{pattern}':\n\t" + "\n\t".join(invalid_name_samples))

    # Add grouped pipeline pattern issues
    for pipeline, sample_ids in pipeline_pattern_issues.items():
        expected_patterns = pipelines[pipeline].get('sample_id_display_patterns', pipelines[pipeline].get('sample_id_patterns', []))
        message = f"Sample_ID does not match the required pattern for pipeline '{pipeline}': Expected formats: {', '.join(expected_patterns)}."
        samples_str = "\n\t".join(sample_ids)
        data_issues.append(f"{message}\n\tSample_ID(s):\n\t{samples_str}")

    for pipeline, samples_list in missing_keyword_samples.items():
        issue_message = f"Description does not contain required keyword(s) for pipeline '{pipeline}':\n\t" + "\n\t".join(samples_list)
        data_issues.append(issue_message)

    if typo_samples:
        typo_messages = ["\t" + msg for msg in typo_samples]
        data_issues.append("Possible typo in Description:\n" + "\n".join(typo_messages))

    actual_filename = os.path.basename(file_path)
    if gms_myeloid_assigned:
        if actual_filename != 'SampleSheet.csv':
            filename_issues.append(f"For 'GMS-Myeloid' pipeline, the samplesheet must be named 'SampleSheet.csv', but got '{actual_filename}'.")
    else:
        if 'samplesheet' not in actual_filename.lower():
            filename_issues.append(f"The samplesheet filename must contain 'samplesheet' (case-insensitive). Got '{actual_filename}'.")
        if '_original' in actual_filename.lower():
            filename_issues.append(f"The samplesheet filename must not contain '_original'. Got '{actual_filename}'.")

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
            issue_message = f"Missing Fields required for the 'GMS-Myeloid' pipeline:\n\t" + "\n\t".join(missing_fields)
            settings_issues.append(issue_message)

def validate_samplesheet(file_path, rules_path):
    issues = defaultdict(list)

    rules = load_validation_rules(rules_path)
    try:
        ss = SampleSheet(file_path)
    except Exception as e:
        error_message = str(e)
        issues['Parsing Error'].append(f"An error occurred while parsing the samplesheet: {error_message}")
        if 'invalid literal for int()' in error_message:
            issues['Parsing Error'].append(
                "This error often occurs due to unexpected or invisible characters. "
                "Check the file for extra characters, such as semicolons ';' or other symbols."
            )
        else:
            issues['Parsing Error'].append(
                "Please ensure that the samplesheet is correctly formatted and does not contain invalid characters."
            )
        logging.error(f"Error parsing samplesheet '{file_path}': {e}")
        traceback.print_exc()
        return issues

    required_sections = rules.get('required_sections', [])
    validate_samplesheet_structure(ss, required_sections, issues)

    required_fields = rules.get('required_fields', {})
    validate_required_fields(ss, required_fields, issues)

    allowed_chars = rules.get('allowed_characters', {})
    validate_allowed_characters(ss, allowed_chars, issues)

    validate_index_uniqueness(ss, issues)

    pipelines = rules.get('pipelines', {})
    if pipelines:
        validate_pipeline_rules(ss, pipelines, issues, file_path)

    return issues

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Validate an Illumina samplesheet.",
        epilog="Example: python validator.py SampleSheet.csv -r validation_rules.yaml"
    )
    parser.add_argument("file", help="Path to the Illumina samplesheet file.")
    parser.add_argument("-r", "--rules", default="validation_rules.yaml",
                        help="Path to the validation rules YAML file.")
    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: The file '{args.file}' does not exist.")
        sys.exit(1)
    if not os.path.isfile(args.rules):
        print(f"Error: The validation rules file '{args.rules}' does not exist.")
        sys.exit(1)

    issues = validate_samplesheet(args.file, args.rules)
    if any(issues.values()):
        print("\nValidation completed with the following issues:\n")
        for section, messages in issues.items():
            if messages:
                print(f"================================= {section} =========================================\n")
                for message in messages:
                    if isinstance(message, str):
                        print(f"- {message}\n")
                    elif isinstance(message, dict) and 'message' in message:
                        print(f"- {message['message']}")
                        for s in message.get('samples', []):
                            print(f"\tSample_ID: {s['id']}")
                            if s.get('expected_formats'):
                                print(f"\tExpected format(s): {', '.join(s['expected_formats'])}\n")
                    else:
                        print(f"- {message}\n")
        sys.exit(1)
    else:
        print("Samplesheet validation passed! No issues found.")
        sys.exit(0)

# If you want to run locally:
# if __name__ == "__main__":
#     main()
