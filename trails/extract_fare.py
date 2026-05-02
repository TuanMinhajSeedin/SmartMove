import pandas as pd
import json
import re
import time
from openai import OpenAI
from dotenv import load_dotenv
import os
load_dotenv()

api_key = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

df = pd.read_excel("2.xlsx")
df = df.iloc[1:].reset_index(drop=True)
# df = df.iloc[1:].reset_index(drop=True)
# print("initial df", df.head())
df = df.drop(0, axis=1, errors='ignore')
df = df.set_index(1)
location_list = df.index.dropna().astype(str).tolist()

# ----------------------------
# Safe JSON extractor
# ----------------------------
def extract_json(text):
    text = re.sub(r"```json|```", "", text).strip()

    start = text.find("[")
    end = text.rfind("]")

    if start == -1 or end == -1:
        raise ValueError(f"No JSON found:\n{text}")

    try:
        return json.loads(text[start:end+1])
    except Exception as e:
        raise ValueError(f"JSON parse error:\n{text[start:end+1]}\n\n{e}")

# ----------------------------
# Prompt (NO f-string issues)
# ----------------------------
PROMPT_TEMPLATE = """
You are a Sri Lankan Place Name Normalization System for bus routes.

SRI LANKAN PLACE REFERENCE DATABASE:
Colombo District: කොළඹ=Colombo, דילිමල=Dilimala, කිරුලපෙන=Kirulapena, මිතුරුව=Mituruwawa, මලිබේ=Malibe, පෙතාවල=Petawala, වැල්ලවත්ත=Wellawatte, කමුරිපිටිය=Kamurupitiya, දෙහිවල=Dehiwala, නිකොමහුරු=Nikomehere, බටහිර කුඩුරු=Batahira Kuduru, බොරැල්ල=Boralla, ගුණපල=Gonapola, කැස්තැලී=Kastallee

Southern Routes: වෑලිගම=Weligama, කොතුඔල්ල=Koggala, හික්කඳුවා=Hikkaduwa, ගල්ල=Galle, කලුතර=Kaluthara, පනාදුර=Panadura, මාතර=Matara, සිසිරෙස්=Sisires, ඉතිකිස=Etikisse

Central/Kandy: කැන්දි=Kandy, පෙරාදෙණිය=Peradeniya, නුවරඑළිය=Nuwara Eliya, අම්බලංගොඩ=Ambalangoda

RULES:
- OCR often confuses: ඼→ල, ි→, ෙ→, කේ→ け (look for context)
- Match partial text to known places
- Only use real Sri Lankan locations
- Return EXACT JSON format

OUTPUT FORMAT:
[
  {{
    "original": "",
    "corrected_sinhala": "",
    "english": "",
    "aliases": []
  }}
]

FEW SHOTS (Complex OCR errors):

Input: ලෆලිගම
Output:
[
  {{
    "original": "ලෆලිගම",
    "corrected_sinhala": "වෑලිගම",
    "english": "Weligama",
    "aliases": ["Weligama", "Welligama"]
  }}
]

Input: ක ොග්ග඼
Output:
[
  {{
    "original": "ක ොග්ග඼",
    "corrected_sinhala": "කොතුඔල්ල",
    "english": "Koggala",
    "aliases": ["Koggala", "Kogalla"]
  }}
]

Input: ශක් ඩුල
Output:
[
  {{
    "original": "ශක් ඩුල",
    "corrected_sinhala": "හික්කඳුවා",
    "english": "Hikkaduwa",
    "aliases": ["Hikkaduwa", "Hikaduwa"]
  }}
]

Input: ළුතර
Output:
[
  {{
    "original": "ළුතර",
    "corrected_sinhala": "කලුතර",
    "english": "Kaluthara",
    "aliases": ["Kaluthara", "Kalutara"]
  }}
]

Input: වැල්ලවත්ත
Output:
[
  {{
    "original": "වැල්ලවත්ත",
    "corrected_sinhala": "වැល්ලවත්ත",
    "english": "Wellawatte",
    "aliases": ["Wellawatte", "Wellawatta"]
  }}
]

INPUT:
"{text}"
"""

# ----------------------------
# LLM call with retry
# ----------------------------
def normalize_place(text, retries=3):
    prompt = PROMPT_TEMPLATE.replace("{text}", json.dumps(text, ensure_ascii=False))

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )

            content = response.choices[0].message.content
            normalized = extract_json(content)
            if normalized:
                return normalized[0]
            raise ValueError("No normalized output returned")
        except Exception as e:
            print(f"Retry {attempt+1} failed for {text!r}:", e)
            time.sleep(2)

    print("FAILED:", text)
    return None

# ----------------------------
# Process one location at a time
# ----------------------------
results = []

for idx, location in enumerate(location_list):
    if not location:
        continue

    try:
        result = normalize_place(location)
        if result:
            result["source_index"] = idx
            results.append(result)
    except Exception as e:
        print("Error:", location, e)

# ----------------------------
# Save output
# ----------------------------
output_df = pd.DataFrame(results)
output_df.to_excel("normalized_places2.xlsx", index=False)

print(output_df)