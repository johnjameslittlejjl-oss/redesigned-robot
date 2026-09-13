import requests
from bs4 import BeautifulSoup
import datetime
import re
import json
from collections import defaultdict

UPRN = "63073803"
URL = f"https://www.wakefield.gov.uk/where-i-live?uprn={UPRN}&a=15%20Meadowcroft%20Road%20Outwood%20Wakefield%20WF1%203TA&usrn=41802624&e=433795&n=424258&p=WF1%203TA"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9"
}

MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12
}

def parse_date_string(text, today):
    # Matches: "Friday 18 September", "Friday, 18th Sept 2026", "18/09/2026", etc.
    # 1. Day of week (optional) + Day number (with optional st/nd/rd/th) + Month + Year (optional)
    m = re.search(r'(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month_str = m.group(2).lower()
        if month_str in MONTH_MAP:
            month = MONTH_MAP[month_str]
            year = int(m.group(3)) if m.group(3) else today.year
            try:
                d = datetime.date(year, month, day)
                if d < today and not m.group(3):
                    d = datetime.date(year + 1, month, day)
                return d
            except ValueError:
                pass

    # 2. DD/MM/YYYY numeric format
    m_num = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', text)
    if m_num:
        day = int(m_num.group(1))
        month = int(m_num.group(2))
        raw_year = int(m_num.group(3))
        year = raw_year if raw_year > 100 else 2000 + raw_year
        try:
            return datetime.date(year, month, day)
        except ValueError:
            pass

    return None

def get_ordinal_suffix(day):
    if 11 <= day <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

def fallback_schedule(today):
    # Fortnightly Friday anchor calculation if council site blocks request
    anchor_general = datetime.date(2026, 1, 9) # Known Friday reference
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_friday = today + datetime.timedelta(days=days_ahead)
    weeks_diff = (next_friday - anchor_general).days // 7
    
    # In season (March to November), General Waste runs alongside Garden Waste
    in_garden_season = (3 <= next_friday.month <= 11)
    if weeks_diff % 2 == 0:
        bin_desc = "General and Garden" if in_garden_season else "General Waste"
    else:
        bin_desc = "Mixed Recycling"
    return next_friday, bin_desc

def main():
    today = datetime.date.today()
    date_to_bins = defaultdict(set)

    try:
        resp = requests.get(URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for tag in soup.find_all(["div", "li", "p", "tr", "section"]):
            text = tag.get_text(" ", strip=True)
            text_lower = text.lower()

            categories = []
            if "household" in text_lower or "general waste" in text_lower or "black bin" in text_lower:
                categories.append("General Waste")
            if "garden" in text_lower or "brown bin" in text_lower:
                categories.append("Garden Waste")
            if "mixed recycling" in text_lower or "green bin" in text_lower or "recycling" in text_lower:
                categories.append("Mixed Recycling")

            if categories:
                d = parse_date_string(text, today)
                if d and d >= today:
                    for cat in categories:
                        date_to_bins[d].add(cat)

    except Exception as e:
        print(f"Scraper notice ({e}). Using scheduled calculation.")

    # Select earliest collection date
    if date_to_bins:
        next_date = min(date_to_bins.keys())
        bins_found = date_to_bins[next_date]

        if "General Waste" in bins_found and "Garden Waste" in bins_found:
            display_bin = "General and Garden"
        elif "General Waste" in bins_found:
            display_bin = "General Waste"
        elif "Garden Waste" in bins_found:
            display_bin = "Garden Waste"
        elif "Mixed Recycling" in bins_found:
            display_bin = "Mixed Recycling"
        else:
            display_bin = " / ".join(sorted(bins_found))[:16]
    else:
        next_date, display_bin = fallback_schedule(today)

    # Format date: "Fri 18th Sep"
    day_name = next_date.strftime("%a")
    day_num = next_date.day
    suffix = get_ordinal_suffix(day_num)
    month_name = next_date.strftime("%b")
    formatted_date = f"{day_name} {day_num}{suffix} {month_name}"

    payload = {
        "address": "15 Meadowcroft Road",
        "uprn": UPRN,
        "bin": display_bin,
        "date": formatted_date
    }

    print("Output JSON:", json.dumps(payload, indent=2))
    with open("bins.json", "w") as f:
        json.dump(payload, f, indent=2)

if __name__ == "__main__":
    main()
