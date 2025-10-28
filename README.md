# Volleyball Calendar Generator

A Python script to fetch match schedules from the Volleyball World API and generate universal `.ics` calendar files that you can import into any standard calendar application (Google Calendar, Apple Calendar, etc.).

This script is fully automated and interactive, allowing you to generate and maintain up-to-date calendars for your favorite professional volleyball championships.

## Features

- **Universal Championship Discovery:** Automatically discovers all currently active championships from the Volleyball World API.
- **Interactive Selection:** Presents a checklist of all active championships, allowing you to choose which ones to process.
- **Smart Updates:** Intelligently checks for existing calendars and only fetches new matches, making subsequent runs very fast and efficient.
- **Automated Mode:** Run the script with a flag (`--update-existing`) to automatically update only the calendars you've already generated, perfect for scheduled tasks (e.g., a cron job).
- **Safe Dry-Run Mode:** Preview which championships are active without fetching any data or writing any files using the `--dry-run` flag.
- **Resilient Fetching:** Automatically retries API requests with exponential backoff to handle temporary network issues.
- **Timezone Aware:** The generated calendar's metadata is set to your local system's timezone. All event times are stored in UTC, ensuring they display correctly for anyone in the world.
- **Organized Output:** Saves calendar files into a clean, organized directory structure based on the season (e.g., `calendars/2025/superliga-masculina.ics`).

## Setup

1.  **Prerequisites:**
    - Python 3.x

2.  **Installation:**
    - It is recommended to use a virtual environment to keep dependencies isolated.
      ```bash
      python3 -m venv venv
      source venv/bin/activate
      ```
    - Install the required Python libraries from the `requirements.txt` file:
      ```bash
      pip install -r requirements.txt
      ```

## Usage

The script offers three modes of operation:

### 1. Interactive Mode (Default)

This is the primary mode for discovering and creating new calendars. The script will find all active championships and present you with a checklist.

```bash
python3 fetch_matches.py
```

You will see a prompt like this, with championships you already have a calendar for pre-selected:

```
? Which active championships would you like to process?
❯◯ SuperLiga Feminina 2025-2026 (superliga-feminina)
 ◉ SuperLiga Masculina 2025-2026 (superliga-masculina)
 ◯ SV-Men 2025-2026 (svleague-men)
 ...
```

### 2. Automated Update Mode

This non-interactive mode is perfect for setting up a scheduled task (like a daily or weekly cron job) to keep your calendars up-to-date. It will only process championships for which a calendar file already exists in the `calendars/` directory.

```bash
python3 fetch_matches.py --update-existing
```

### 3. Dry-Run (Discovery) Mode

Use this safe, read-only mode to see a list of all currently active championships without fetching any match data or writing any files.

```bash
python3 fetch_matches.py --dry-run
```

## Output

The script will generate `.ics` files in the `calendars/` directory, organized into subdirectories by season. For example:

```
calendars/
└── 2025/
    ├── superliga-feminina.ics
    └── superliga-masculina.ics
```

You can import these files directly into your calendar application of choice.
