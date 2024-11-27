Overview:

Given the issues in demuxer and other pipelines that occur because of problems in the SampleSheet.csv, this application aims to validate samplesheets before starting the sequencing machines. This web application was designed to validate Illumina samplesheets. It ensures that a given samplesheets is in accordance to different standards for the correct functioning of our pipelines. It prints all found issues to be corrected before starting the sequencing runs.

Features

	File Upload: expects a CSV samplesheets for validation.
	Validation: Checks for required sections, fields, allowed characters, and pipeline-specific rules.
	SLIMS Integration: Verifies if samples already exist in the SLIMS system to prevent duplicates.
	Logging: Detailed information on what needs to be corrected.

Validation:
	sample-sheet Module:
		- Ensure the format and structure is in accordance to Illumina's samplesheet model.
		- Parses and ensures that essential sections and fields are present in the samplesheet:
			[Header], [Reads], [Settings], and [Data].
		- Will exit as soon as it finds a parsing error (it expects the different sections and ONE line between them.
		- Checks for the different sections, the presence of Sample_ID, indexes are not the same.

	validator.py:
		- Checks that the necessary fields for the sections are present and non-empty.
    			Required Fields:
        			Header:
            				Investigator Name
            				Experiment Name
            				Date
            				Workflow
            				Application
            				Chemistry
        			Data:
            				Sample_ID
            				Sample_Name
            				index
            				index2
            				Description
		- Confirms that Sample_ID matches Sample_Name, because Demuxer needs it to be like this.
		- Character Validation and reports any invalid characters found.
			Fields Checked:
        		Sample_ID
        		Sample_Name
        		index
        		index2
		- SLIMS connection: It connects to SLIMS using demuxer credentials to check if a given Sample_ID already has a fastq object in SLIMS.
		- Pipeline-Specific Validation
			Since some pipelines rely on the 'Description' field to be properly written to extract the samples to be run by them, we have to ensure that the description has the keyword 'npm1' and not 'nmp1', for example.
    			Pipelines Handled and their keywords:
        			NPM1: npm1
        			FLT3-ITD: flt3-itd or flt3_itd
        			Archer: fp_pst
        			GMS-Myeloid: gms-myeloid
        			COVID: covid, covid19 or covid-19
			Keyword Checks:
            			Searches the Description field for pipeline-specific keywords.
            			Detects possible typos using difflib to suggest correct pipeline names. If written 'f3tl-idt' it is still able to identify the typo and suggest coorection to 'flt3-itd'
        		Regex Validation (Specific to COVID Pipeline):
            			Ensures that Sample_ID and Sample_Name match the required regex pattern: D[A-Z]2[0-4]\d{6}
		- Filename
			Ensures the file contains 'samplesheet' (case insensitive) and does not allow '_original' (because demuxer will not perform some editings if there is already a *_original.csv in the /raw_runs directory.
				Allowed (example): sampleSheet123_blabla.csv
				Disallowed: samplesheet_original.csv	
		- Filename and Settings Validation (Specific to GMS-Myeloid Pipeline)
			- if the samplesheet contains the keyword 'gms-myeloid' in the 'Description' field, then it will check the name of that file and the fields in the [Settings] section.
			- GMS-Myeloid is picky and needs the samplesheet file to be named exactly 'SampleSheet.csv'.
    			- Settings Validation:
        			Verifies the presence of required settings fields:
            				Adapter
            				AdapterRead2
            				Read1UMILength
            				Read2UMILength
            				Read1StartFromCycle
            				Read2StartFromCycle
Installation:

Configuration:
	The validation_rules.yaml file sets the rules for samplesheet validation, including required sections, fields, allowed characters, and pipeline-specific criteria.

Environment Variables:

    SLIMS Credentials:
        SLIMS_URL: URL of the SLIMS REST API.
        SLIMS_USER: Username for SLIMS API access.
        SLIMS_PASSWORD: Password for SLIMS API access.

    Flask Secret Key:
        FLASK_SECRET_KEY: A secret key for securely signing the session and other security-related needs.
