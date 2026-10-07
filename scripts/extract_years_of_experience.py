

import json
import os
import re

def extract_years_of_experience(input_file, output_file):
    # 1. Read raw file
    if not os.path.isfile(input_file):
        print(f"Input file not found: {input_file}.")
        print("Export resumes from Mongo first — see README, 'Export a collection to JSON'.")
        return
    with open(input_file, 'r', encoding='utf-8') as f:
        raw_data = f.read()

    # 2. Find the start of the JSON (the first '[')
    start_idx = raw_data.find('[')
    if start_idx == -1:
        print("No '[' found in the file.")
        return

    # 3. Parse only the first JSON value using raw_decode
    decoder = json.JSONDecoder()
    try:
        resumes, end = decoder.raw_decode(raw_data[start_idx:])
    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return

    # raw_decode returns (parsed_object, number_of_characters_consumed)
    # resumes should be a list of resumes
    if not isinstance(resumes, list):
        print("Expected a list of resumes, got", type(resumes))
        return

    # 4. Regex to find experience in years
    pattern = re.compile(r"Опыт работы:\s*(\d+)\s*(?:лет|год|года)", re.IGNORECASE)

    extracted_data = []
    for resume in resumes:
        exp_text = resume.get("experience", "")
        match = pattern.search(exp_text)
        years = int(match.group(1)) if match else None

        extracted_data.append({
            "_id": resume.get("_id"),
            "title": resume.get("title"),
            "experience_years": years
        })

    # 5. Save to output JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(extracted_data, f, ensure_ascii=False, indent=4)

    # Print summary
    total = len(extracted_data)
    found = sum(1 for r in extracted_data if r["experience_years"] is not None)
    print(f"Total resumes processed: {total}")
    print(f"Found experience years in {found} resumes.")
    print(f"Results saved to {output_file}")

if __name__ == "__main__":
    extract_years_of_experience("resumes.json", "extracted_experience.json")
