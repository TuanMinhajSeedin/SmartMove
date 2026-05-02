#!/usr/bin/env python3
"""
Setup and run script for Gemini PDF extraction with translation
Usage: python setup_and_run_selected_pdf.py <pdf_path> [output_dir]
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add parent directory to path to import the extractor
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gemini_pdf_extractor_v2 import GeminiPDFTableExtractorV2

def translate_sinhala_to_english(text, api_key):
    """
    Translate Sinhala text to English using Gemini API
    """
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        prompt = f"""
        Translate the following Sinhala text to English. 
        If the text contains bus route numbers, times, or place names, translate them accurately.
        Return only the English translation without any additional text.
        
        Sinhala text: {text}
        """
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[prompt],
            config=genai.types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=1000,
            )
        )
        
        return response.text.strip()
        
    except Exception as e:
        print(f"Translation error: {e}")
        return text  # Return original text if translation fails

def parse_raw_response(extracted_data):
    """
    Parse raw response from Gemini API if it contains embedded JSON
    """
    if isinstance(extracted_data, dict) and "raw_response" in extracted_data:
        raw_text = extracted_data["raw_response"]
        
        # Try to extract JSON from the raw response
        if "```json" in raw_text:
            # Extract JSON content between ```json and ```
            start = raw_text.find("```json") + 7
            end = raw_text.rfind("```")
            if start > 6 and end > start:
                json_text = raw_text[start:end].strip()
                try:
                    parsed_data = json.loads(json_text)
                    print("✅ Successfully parsed raw response")
                    return parsed_data
                except json.JSONDecodeError as e:
                    print(f"⚠️ Could not parse JSON from raw response: {e}")
                    return extracted_data
        
        # Try to parse the entire raw response as JSON
        try:
            parsed_data = json.loads(raw_text)
            print("✅ Successfully parsed raw response as JSON")
            return parsed_data
        except json.JSONDecodeError:
            pass
    
    return extracted_data

def split_combined_tables(table_data):
    """
    Detect and split tables that have been combined into one
    """
    if not isinstance(table_data, dict) or "tables" not in table_data:
        return table_data
    
    new_tables = []
    
    for table in table_data["tables"]:
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        
        # Check if this looks like a combined table (has duplicate column names)
        # Look for duplicate headers first, then check column count
        duplicate_headers = []
        for i, header in enumerate(headers):
            if header in headers[i+1:]:
                duplicate_headers.append(header)
        
        if len(headers) > 6 and duplicate_headers:  # Likely combined if more than 6 columns with duplicates
            # Found duplicate headers, likely two tables
            print(f"🔍 Detected combined table with {len(headers)} columns, attempting to split...")
            print(f"   Duplicate headers found: {duplicate_headers[:3]}")  # Show first few duplicates
            
            # Try to find the split point by looking for where the first duplicate header appears again
            first_duplicate = duplicate_headers[0] if duplicate_headers else None
            split_point = len(headers) // 2  # Default to middle
            
            if first_duplicate:
                # Find the second occurrence of the first duplicate header
                first_occurrence = headers.index(first_duplicate)
                second_occurrence = headers.index(first_duplicate, first_occurrence + 1)
                if second_occurrence > first_occurrence:
                    split_point = second_occurrence
                    print(f"   Found split point at column {split_point} based on duplicate header '{first_duplicate}'")
            
            # Ensure we don't split too close to the beginning or end
            if split_point < 3:
                split_point = len(headers) // 2
            elif split_point > len(headers) - 3:
                split_point = len(headers) // 2
            
            # Create first table
            table1 = table.copy()
            table1["headers"] = headers[:split_point]
            table1["rows"] = []
            for row in rows:
                if isinstance(row, list):
                    # Take only the available elements for first table (up to split_point or row length)
                    first_part = row[:min(split_point, len(row))]
                    # Pad with empty strings if the row is shorter than split_point
                    while len(first_part) < split_point:
                        first_part.append("")
                    table1["rows"].append(first_part)
                else:
                    table1["rows"].append([""] * split_point)
            table1["table_number"] = len(new_tables) + 1
            new_tables.append(table1)
            
            # Create second table
            table2 = table.copy()
            table2["headers"] = headers[split_point:]
            expected_cols_2 = len(headers) - split_point
            table2["rows"] = []
            for row in rows:
                if isinstance(row, list) and len(row) > split_point:
                    # Take elements from split_point onwards
                    second_part = row[split_point:]
                    # Pad with empty strings if the row is shorter than expected
                    while len(second_part) < expected_cols_2:
                        second_part.append("")
                    table2["rows"].append(second_part)
                elif isinstance(row, list) and len(row) <= split_point:
                    # Row too short, create empty row for second table
                    table2["rows"].append([""] * expected_cols_2)
                else:
                    table2["rows"].append([""] * expected_cols_2)
            table2["table_number"] = len(new_tables) + 2
            new_tables.append(table2)
            
            print(f"✅ Split into 2 tables: {len(table1['headers'])} and {len(table2['headers'])} columns")
            print(f"   Table 1 rows: {len(table1['rows'])}")
            print(f"   Table 2 rows: {len(table2['rows'])}")
        else:
            new_tables.append(table)
    
    table_data["tables"] = new_tables
    return table_data

def translate_table_data(table_data, api_key):
    """
    Translate table headers and data from Sinhala to English using bulk translation
    """
    if not isinstance(table_data, dict) or "tables" not in table_data:
        return table_data
    
    try:
        import google.generativeai as genai
        
        # Configure Gemini client
        genai.configure(api_key=api_key)
        
        # Convert table data to JSON string for translation
        text = json.dumps(table_data, ensure_ascii=False)
        
        # Initialize Gemini model
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Prepare translation prompt
        prompt = (
            "You are a translator that converts Sinhala text into English clearly and accurately. "
            "Keep the same JSON structure and translate only the text content. "
            "Do not remove or rename keys. "
            "If you detect that there are multiple tables combined into one (like two separate bus schedules), "
            "split them into separate table objects in the tables array.\n\n"
            f"{text}"
        )
        
        # Generate translation
        response = model.generate_content(prompt)
        
        # Extract translated text
        translated_text = response.text
        
        # Clean up the response (remove markdown code block markers if present)
        if translated_text.startswith('```json'):
            translated_text = translated_text[7:]
        if translated_text.endswith('```'):
            translated_text = translated_text[:-3]
        translated_text = translated_text.strip()
        
        # Parse the translated JSON
        try:
            translated_data = json.loads(translated_text)
            return translated_data
        except json.JSONDecodeError:
            print("⚠️ Could not parse translated JSON, returning original data")
            return table_data
            
    except Exception as e:
        print(f"Translation error: {e}")
        return table_data  # Return original data if translation fails

def main():
    parser = argparse.ArgumentParser(description="Extract and translate tables from a PDF file")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: same as PDF directory)")
    parser.add_argument("-k", "--api-key", help="Google AI API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--no-translate", action="store_true", help="Skip translation step")
    
    args = parser.parse_args()
    
    print("🚀 Gemini PDF Table Extractor with Translation")
    print("=" * 50)
    
    # Check if PDF exists
    if not os.path.exists(args.pdf_path):
        print(f"❌ PDF file not found: {args.pdf_path}")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_AI_API_KEY')
    
    if not api_key:
        print("❌ No API key found!")
        print("\nTo get your API key:")
        print("1. Visit: https://aistudio.google.com/app/apikey")
        print("2. Create a new API key")
        print("3. Set it as an environment variable:")
        print("   Windows: set GEMINI_API_KEY=your_key_here")
        print("   Linux/Mac: export GEMINI_API_KEY=your_key_here")
        print("\nOr you can enter it now (it won't be saved):")
        
        api_key = input("Enter your Gemini API key: ").strip()
        if not api_key:
            print("❌ No API key provided. Exiting.")
            sys.exit(1)
    
    # Set output directory
    if args.output_dir:
        output_dir = args.output_dir
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = os.path.dirname(args.pdf_path)
    
    # Initialize extractor
    try:
        extractor = GeminiPDFTableExtractorV2(api_key=api_key)
        print("✅ Extractor initialized successfully!")
    except Exception as e:
        print(f"❌ Failed to initialize extractor: {e}")
        sys.exit(1)
    
    print(f"📄 Processing PDF: {os.path.basename(args.pdf_path)}")
    print(f"📁 Output directory: {output_dir}")
    print("🔄 Starting table extraction...")
    
    # Extract tables
    try:
        results = extractor.extract_tables_from_pdf(args.pdf_path, "json")
        
        if results["success"]:
            print("✅ Table extraction completed successfully!")
            
            # Get base filename without extension
            base_name = Path(args.pdf_path).stem
            
            # Display summary and process the extracted data
            extracted_data = results.get("extracted_data", {})
            
            # Try to parse raw response if present
            extracted_data = parse_raw_response(extracted_data)
            
            # Check if we have properly parsed tables
            if isinstance(extracted_data, dict) and "tables" in extracted_data:
                # Try to split combined tables before processing
                extracted_data = split_combined_tables(extracted_data)
                
                # Update the results with the parsed and split data
                results["extracted_data"] = extracted_data
            
            # Save original results (after parsing and splitting)
            original_output = os.path.join(output_dir, f"{base_name}_extracted_tables.json")
            extractor.save_results(results, original_output)
            
            # Display summary after processing
            if isinstance(extracted_data, dict) and "tables" in extracted_data:
                tables = extracted_data["tables"]
                print(f"📊 Found {len(tables)} tables:")
                
                for i, table in enumerate(tables, 1):
                    print(f"  Table {i}: {table.get('title', 'Untitled')}")
                    print(f"    - Page: {table.get('page_number', 'Unknown')}")
                    print(f"    - Columns: {len(table.get('headers', []))}")
                    print(f"    - Rows: {len(table.get('rows', []))}")
            else:
                print("📊 Table data extracted (check output file for details)")
            
            print(f"📁 Original results saved to: {original_output}")
            
            # Translate to English (unless skipped)
            if not args.no_translate:
                print("\n🔄 Translating Sinhala text to English...")
                try:
                    translated_data = translate_table_data(extracted_data, api_key)
                    
                    # Check if translation was successful
                    if translated_data != extracted_data:
                        # Create translated results
                        translated_results = results.copy()
                        translated_results["extracted_data"] = translated_data
                        translated_results["translated"] = True
                        translated_results["translation_method"] = "gemini-2.5-flash"
                        
                        # Save translated results
                        translated_output = os.path.join(output_dir, f"{base_name}_extracted_tables_english.json")
                        extractor.save_results(translated_results, translated_output)
                        
                        print("✅ Translation completed successfully!")
                        print(f"📁 Translated results saved to: {translated_output}")
                        
                        # Display translated summary
                        if isinstance(translated_data, dict) and "tables" in translated_data:
                            print("\n📊 Translated Tables:")
                            for i, table in enumerate(translated_data["tables"], 1):
                                print(f"  Table {i}:")
                                print(f"    Headers: {table.get('headers', [])}")
                                if table.get('rows'):
                                    print(f"    Sample row: {table['rows'][0] if table['rows'] else 'No data'}")
                    else:
                        print("⚠️ Translation returned original data - may have failed")
                        print("Original data is still available in the JSON file.")
                    
                except Exception as e:
                    print(f"❌ Translation failed: {e}")
                    print("Original data is still available in the JSON file.")
            else:
                print("⏭️ Translation skipped as requested")
            
        else:
            print(f"❌ Extraction failed: {results.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
