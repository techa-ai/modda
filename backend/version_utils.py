
import os
import re
import dateutil.parser
import imagehash
from pdf2image import convert_from_path
from PIL import Image
import tempfile
from datetime import datetime

def extract_date_from_text(text):
    """
    Attempt to find the most likely document date in the text.
    Looks for date patterns. Returns the latest found date or None.
    """
    if not text:
        return None
        
    # Common date formats: MM/DD/YYYY, YYYY-MM-DD, Month DD, YYYY
    date_patterns = [
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b'
    ]
    
    found_dates = []
    
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                dt = dateutil.parser.parse(match, fuzzy=False)
                # Filter out unlikely dates (e.g. future or too old)
                if 1990 <= dt.year <= datetime.now().year + 1:
                    found_dates.append(dt.date())
            except:
                pass
                
    if not found_dates:
        # Fallback: Look for standalone years (e.g. "2024") often found in tax forms header/footer
        # We look for 2010-2030 range to catch recent documents
        from datetime import date
        year_matches = re.findall(r'\b(20[1-2][0-9])\b', text)
        valid_years = []
        for y in year_matches:
            try:
                val = int(y)
                if 1990 <= val <= datetime.now().year + 2:
                    # Treat standalone year as Jan 1st of that year for sorting purposes
                    valid_years.append(date(val, 1, 1))
            except:
                pass
        
        if valid_years:
            return max(valid_years)

        return None
        
    # Return the LATEST date found (often document date is recent)
    return max(found_dates)

def compute_visual_hashes(pdf_path):
    """
    Convert first page of PDF to image and compute perceptual hashes.
    Returns dictionary with phash, dhash, ahash.
    """
    temp_dir = tempfile.mkdtemp()
    try:
        # Convert first page only
        images = convert_from_path(
            pdf_path,
            first_page=1,
            last_page=1,
            dpi=150,
            fmt='png',
            output_folder=temp_dir
        )
        
        if not images:
            return None
            
        img = images[0]
        
        hashes = {
            'phash': str(imagehash.phash(img, hash_size=16)),
            'dhash': str(imagehash.dhash(img, hash_size=16)),
            'ahash': str(imagehash.average_hash(img, hash_size=16))
        }
        
        return hashes
        
    except Exception as e:
        print(f"Error computing visual hashes for {pdf_path}: {e}")
        return None
    finally:
        # Cleanup temp dir
        try:
            import shutil
            shutil.rmtree(temp_dir)
        except:
            pass

def hamming_distance(hash1, hash2):
    """Calculate Hamming distance between two hex hash strings"""
    if not hash1 or not hash2 or len(hash1) != len(hash2):
        return float('inf')
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

def are_visually_similar(hashes1, hashes2, threshold=5):
    """
    Check if two documents are visually similar based on their hashes.
    matches if at least 2 out of 3 hashes are within threshold.
    """
    if not hashes1 or not hashes2:
        return False
        
    matches = 0
    if hamming_distance(hashes1['phash'], hashes2['phash']) <= threshold:
        matches += 1
    if hamming_distance(hashes1['dhash'], hashes2['dhash']) <= threshold:
        matches += 1
    if hamming_distance(hashes1['ahash'], hashes2['ahash']) <= threshold:
        matches += 1
        
    return matches >= 2
