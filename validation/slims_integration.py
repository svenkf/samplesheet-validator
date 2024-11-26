import os
import json
import logging
import traceback
from slims.slims import Slims
from slims.criteria import equals, conjunction

def load_slims_credentials():
    """Load SLIMS credentials from environment variables."""
    try:
        slims_credentials = {
            'url': os.environ.get('SLIMS_URL'),
            'user': os.environ.get('SLIMS_USER'),
            'password': os.environ.get('SLIMS_PASSWORD')
        }
        if not all(slims_credentials.values()):
            raise Exception("Missing SLIMS credentials in environment variables.")
        return slims_credentials
    except Exception as e:
        logging.error(f"An error occurred while loading SLIMS credentials: {e}")
        traceback.print_exc()
        return None

def connect_slims(slims_credentials):
    """Connect to SLIMS with given credentials."""
    instance = 'query'
    url = slims_credentials['url']
    user = slims_credentials['user']
    password = slims_credentials['password']
    return Slims(instance, url, user, password)

def sample_has_fastq(slims, sample_id):
    """
    Check if a sample with the given Sample_ID already has a fastq object in SLIMS.

    :param slims: SLIMS connection object.
    :param sample_id: The Sample_ID to check.
    :return: True if a fastq object exists, False otherwise.
    """
    try:
        # Content type 22 corresponds to fastq objects in SLIMS
        records = slims.fetch('Content', conjunction()
                              .add(equals('cntn_id', sample_id))
                              .add(equals('cntn_fk_contentType', 22)))
        return bool(records)
    except Exception as e:
        logging.error(f"Error querying SLIMS for Sample_ID '{sample_id}': {e}")
        traceback.print_exc()
        return False  # Proceed as if no fastq exists in case of error

