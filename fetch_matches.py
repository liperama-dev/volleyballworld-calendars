import requests
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import pytz
import os
import time
from tqdm import tqdm
import argparse
import questionary
from tzlocal import get_localzone

# --- Configuration ---
VW_API_BASE_URL = "https://en.volleyballworld.com/api/v1/"
TOURNAMENT_API_BASE_URL = f"{VW_API_BASE_URL}volley-tournament/"

OUTPUT_DIR = "calendars"  # Generic name for the output directory
ICS_FILENAME_FORMAT = "{season}/{league_slug}.ics"
# SEASON_YEARS is now determined dynamically

# --- Helper Functions ---

def fetch_active_competitions(target_year, headers):
    """
    Fetches the global list of competitions and filters for currently active ones.
    """
    competitions_url = f"{VW_API_BASE_URL}globalschedule/competitions/{target_year}/"
    print(f"Fetching all available competitions from: {competitions_url}")
    try:
        response = requests.get(competitions_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        active_competitions = []
        now = datetime.now(pytz.utc)

        for comp in data.get('competitions', []):
            start_date_str = comp.get('startDate')
            end_date_str = comp.get('endDate')

            if not start_date_str or not end_date_str:
                continue

            start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))

            if start_date <= now <= end_date:
                # Generate a slug from the URL, e.g., /.../superliga-masculina/ -> superliga-masculina
                url_parts = comp.get('url', '').strip('/').split('/')
                slug = url_parts[-1] if url_parts else 'unknown'
                if not slug or '20' in slug: # Handle cases like /2024-2025/
                    slug = url_parts[-2] if len(url_parts) > 1 else 'unknown'


                tournament_id = comp.get('menTournaments') or comp.get('womenTournaments')

                if tournament_id and slug != 'unknown':
                    active_competitions.append({
                        "id": tournament_id,
                        "fullName": comp.get('competitionFullName', 'Unknown Competition'),
                        "startDate": start_date,
                        "endDate": end_date,
                        "slug": slug,
                        "season": comp.get('season')
                    })
        
        if not active_competitions:
            print(f"Warning: Could not find any active competitions for the season starting in {target_year}.")

        return active_competitions
    except requests.exceptions.RequestException as e:
        print(f"Error fetching competitions data: {e}")
        return []


def get_calendar_date_range(filepath):
    """
    Reads an .ics file and returns the earliest and latest event dates.
    """
    if not os.path.exists(filepath):
        return None, None

    try:
        with open(filepath, 'rb') as f:
            cal = Calendar.from_ical(f.read())
        
        event_starts = [component.get('dtstart').dt for component in cal.walk('VEVENT')]
        
        if not event_starts:
            return None, None
            
        # Ensure all datetimes are timezone-aware for correct comparison
        aware_starts = [dt.astimezone(pytz.utc) if dt.tzinfo is None else dt for dt in event_starts]

        return min(aware_starts), max(aware_starts)
    except Exception as e:
        print(f"Warning: Could not read or parse existing calendar {filepath}. It will be updated. Error: {e}")
        return None, None


def fetch_with_retries(url, headers):
    """
    A wrapper for requests.get to handle retries on network errors with exponential backoff.
    """
    retries = 4
    base_delay = 1  # seconds
    for i in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, requests.exceptions.SSLError) as e:
            delay = base_delay * (2 ** i)
            print(f"Request failed: {e}. Attempt {i + 1} of {retries}. Retrying in {delay}s...")
            if i < retries - 1:
                time.sleep(delay)
            else:
                print("Max retries reached. Giving up on this request.")
                return None


def fetch_match_days(tournament_id, year, headers):
    """
    Fetches the specific dates that have matches for a given year and tournament.
    """
    api_url = f"{TOURNAMENT_API_BASE_URL}matchdays/{year}/-04:00/{tournament_id}"
    print(f"Fetching match days from: {api_url}")
    data = fetch_with_retries(api_url, headers)
    if data:
        return data.get('matchDays', [])
    return []

def fetch_schedule_from_api(tournament_id, start_date, end_date, headers):
    """
    Fetches match schedule from the Volleyball World API for a given period.
    """
    if not tournament_id:
        print("Invalid tournament_id provided.")
        return None

    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    api_url = f"{TOURNAMENT_API_BASE_URL}{start_date_str}/{end_date_str}/{tournament_id}"
    print(f"Fetching schedule from: {api_url}")
    return fetch_with_retries(api_url, headers)


def process_api_response(api_data, league_type, league_slug):
    """
    Processes the JSON API response and extracts relevant match details.
    """
    events = []
    if not api_data or 'matches' not in api_data:
        print("No match data found in API response.")
        return events

    teams = {team['no']: team['name'] for team in api_data.get('allTeams', [])}

    for match in api_data['matches']:
        try:
            match_id = match.get('matchNo')
            home_team_no = match.get('teamANo')
            away_team_no = match.get('teamBNo')
            home_team = teams.get(home_team_no, 'N/A')
            away_team = teams.get(away_team_no, 'N/A')

            start_time_utc_str = match.get('matchDateUtc')
            location = match.get('city', 'Local Desconhecido')

            if not start_time_utc_str:
                print(f"Skipping match {match_id}: No match time provided.")
                continue

            # Parse UTC time from API
            dt_utc = datetime.fromisoformat(start_time_utc_str.replace('Z', '+00:00'))

            # Estimate end time (e.g., 2 hours later)
            dt_end_utc = dt_utc + timedelta(hours=2)

            summary = f"{home_team} x {away_team} - {league_type}"
            description = f"{league_type} - Match ID: {match_id}"
            # UID should be stable and not dependent on the match time, which can change.
            uid = f"volleyballworld-{league_slug}-{match_id}"

            events.append({
                'summary': summary,
                'dtstart': dt_utc,
                'dtend': dt_end_utc,
                'location': location,
                'description': description,
                'uid': uid
            })
        except Exception as e:
            print(f"Error processing match data: {match.get('matchNo', 'Unknown ID')} - {e}")
            continue
    return events


def generate_ics_file(events, filename, league_name):
    """
    Generates an .ics file from a list of event dictionaries.
    """
    cal = Calendar()
    cal.add('prodid', f'-//Volleyball World {league_name} Calendar//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', f'{league_name}')
    
    # Use the system's local timezone
    local_tz = get_localzone()
    cal.add('x-wr-timezone', local_tz.zone)

    for event_data in events:
        event = Event()
        event.add('summary', event_data['summary'])
        event.add('dtstart', event_data['dtstart'])
        event.add('dtend', event_data['dtend'])
        event.add('location', event_data['location'])
        event.add('description', event_data['description'])
        event.add('uid', event_data['uid'])
        event.add('dtstamp', datetime.now(pytz.utc))  # Creation timestamp in UTC
        cal.add_component(event)

    # The directory creation is now handled in the main loop
    with open(filepath, 'wb') as f:
        f.write(cal.to_ical())
    print(f"Generated {filepath}")


# --- Main Script Execution ---

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate .ics calendar files for volleyball matches.")
    parser.add_argument("--dry-run", action="store_true", help="Lists active championships without fetching details or writing files.")
    parser.add_argument("--update-existing", action="store_true", help="Run non-interactively and only update calendars that already exist.")
    args = parser.parse_args()

    # Define headers once to be reused by all API calls
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7',
        'cache-control': 'no-cache',
        'dnt': '1',
        'origin': 'https://en.volleyballworld.com',
        'pragma': 'no-cache',
        'referer': 'https://en.volleyballworld.com/',
        'sec-ch-ua': '"Chromium";v="141", "Not?A_Brand";v="8"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
    }

    # Discover all currently active competitions
    current_year = 2025 #datetime.now().year
    active_competitions = fetch_active_competitions(current_year, headers)

    if not active_competitions:
        print("Could not find any active competitions. Exiting.")
        exit()

    # In dry-run mode, just list findings and exit
    if args.dry_run:
        print("\n*** --- DRY RUN MODE --- ***")
        print("--- Active Competitions Found ---")
        for comp in active_competitions:
            print(f"- {comp['fullName']} (Slug: {comp['slug']})")
        exit()

    # --- Interactive or Automated Selection ---
    if args.update_existing:
        print("`--update-existing` flag is set. Processing only championships with existing calendars.")
        selected_comps = []
        for comp in active_competitions:
            filename = ICS_FILENAME_FORMAT.format(
                season=comp['season'],
                league_slug=comp['slug']
            )
            filepath = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(filepath):
                selected_comps.append(comp)
    else:
        choices = []
        for comp in active_competitions:
            filename = ICS_FILENAME_FORMAT.format(
                season=comp['season'],
                league_slug=comp['slug']
            )
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            choices.append({
                'name': f"{comp['fullName']} ({comp['slug']})",
                'value': comp,
                'checked': os.path.exists(filepath)
            })

        selected_comps = questionary.checkbox(
            'Which active championships would you like to process?',
            choices=choices
        ).ask()

    if not selected_comps:
        print("No championships selected. Exiting.")
        exit()

    for comp_details in selected_comps:
        league_season_name = comp_details['fullName']
        print(f"\n--- Processing {league_season_name} ---")

        tournament_id = comp_details.get('id')
        start_date = comp_details.get('startDate')
        end_date = comp_details.get('endDate')
        
        season_years = list(range(start_date.year, end_date.year + 1))
        
        filename = ICS_FILENAME_FORMAT.format(
            season=comp_details['season'],
            league_slug=comp_details['slug']
        )
        filepath = os.path.join(OUTPUT_DIR, filename)

        # --- Efficiency Check ---
        # Get the date of the latest event in the existing calendar
        _, max_cal_date = get_calendar_date_range(filepath)
        if max_cal_date:
             print(f"Found existing calendar with events up to {max_cal_date.strftime('%Y-%m-%d')}.")
        
        # Fetch all official match days for the entire season
        all_match_days = []
        for year in season_years:
            match_days_for_year = fetch_match_days(tournament_id, year, headers)
            if match_days_for_year:
                all_match_days.extend(match_days_for_year)
        
        # Filter for match days that are newer than what we already have
        if max_cal_date:
            all_match_days = [
                day_str for day_str in all_match_days 
                if datetime.strptime(day_str, '%Y-%m-%d').date() > max_cal_date.date()
            ]

        if not all_match_days:
            print(f"Calendar is already up-to-date. No new match days found.")
            continue # Move to the next competition
        
        print(f"Found {len(all_match_days)} new match days to process. Grouping into weekly fetches.")

        # Convert to datetime objects and sort, just in case
        all_match_dates = sorted([datetime.strptime(day_str, '%Y-%m-%d') for day_str in all_match_days])
        
        # Group match days into 7-day chunks for efficient fetching
        fetch_ranges = []
        while all_match_dates:
            start_date_chunk = all_match_dates[0]
            end_date_chunk = start_date_chunk + timedelta(days=6)
            fetch_ranges.append((start_date_chunk, end_date_chunk))
            # Prepare for the next chunk by removing dates covered by this one
            all_match_dates = [d for d in all_match_dates if d > end_date_chunk]

        all_fetched_events = []
        print("Fetching schedules in weekly chunks...")
        for start_chunk, end_chunk in tqdm(fetch_ranges, desc="Processing Weeks"):
            # Fetch schedule for the 7-day chunk
            api_data = fetch_schedule_from_api(tournament_id, start_chunk, end_chunk, headers)
            
            if api_data:
                events = process_api_response(api_data, league_season_name, comp_details['slug'])
                if events:
                    all_fetched_events.extend(events)
            
            time.sleep(0.5) # A polite delay between weekly fetches

        # Add only new events to the calendar
        new_events_count = 0
        all_events_for_ics = []
        
        # Add existing events first to preserve them
        existing_uids = set()
        if os.path.exists(filepath):
            try:
                with open(filepath, 'rb') as f:
                    existing_cal = Calendar.from_ical(f.read())
                    for component in existing_cal.walk('VEVENT'):
                        # Check for UID to avoid adding event data if it's missing
                        if component.get('uid'):
                            uid_str = component.get('uid')
                            existing_uids.add(uid_str)
                            event_data = {
                                'summary': component.get('summary'),
                                'dtstart': component.get('dtstart').dt,
                                'dtend': component.get('dtend').dt,
                                'location': component.get('location'),
                                'description': component.get('description'),
                                'uid': uid_str
                            }
                            all_events_for_ics.append(event_data)
            except Exception as e:
                print(f"Warning: Could not read events from existing calendar {filepath}. Error: {e}")

        for event in all_fetched_events:
            if event['uid'] not in existing_uids:
                all_events_for_ics.append(event)
                new_events_count += 1
        
        print(f"Added {new_events_count} new events.")

        if all_events_for_ics or (not new_events_count and os.path.exists(filepath)):
            # Ensure the target directory exists before writing the file
            directory = os.path.dirname(filepath)
            os.makedirs(directory, exist_ok=True)
            generate_ics_file(all_events_for_ics, filepath, league_season_name)
        else:
            print(f"No events to generate calendar for {league_season_name}.")

    print("\nScript finished. Check the 'calendars' directory for your .ics files.")
    print("You can import these files directly into Apple Calendar or other calendar applications.")