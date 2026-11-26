#!/usr/bin/env python3
import datetime
import sys
import json
import re

def calculate_license_remaining_days(input_text):
    """
    Finds the last date in the input string and calculates days remaining.
    """
    try:
        # Remove dashes and find all 8-digit sequences
        clean_text = input_text.replace('-', '')
        dates = re.findall(r'\d{8}', clean_text)
        
        if not dates:
            return None
            
        # Use the last date found as the expiration date
        expiration_str = dates[-1]
        expiration_date = datetime.datetime.strptime(expiration_str, "%Y%m%d").date()
        
        today = datetime.date.today()
        delta = expiration_date - today
        
        return delta.days
    except Exception:
        return None

if __name__ == "__main__":
    # Get original arguments for JSON output
    start_str = sys.argv[1] if len(sys.argv) > 1 else "N/A"
    end_str = sys.argv[2] if len(sys.argv) > 2 else "N/A"
    
    # Join all arguments for calculation
    input_text = " ".join(sys.argv[1:])
    
    days = calculate_license_remaining_days(input_text)
    
    if days is not None:
        resultado = {
            "data_inicial": start_str,
            "data_final": end_str,
            "dias_restantes": days
        }
        print(json.dumps(resultado))
    else:
        print(json.dumps({"error": "No valid dates found", "dias_restantes": -1}))
