# AI-Based Attendance Management System

A beginner-friendly Python terminal application. Attendance is stored locally in
`attendance.json`; Python validates every command and calculates all attendance
statistics. An OpenAI API is optional: common requests also work with the local
rule-based fallback.

## Requirements

- Python 3.10 or newer
- An OpenAI API key only if you want AI interpretation (the local fallback does
  not need a key or an internet connection)

## Set up in VS Code

Open this project folder in VS Code, then open **Terminal > New Terminal**.
The commands below are for Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, run this in that terminal and then activate:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

For Windows Command Prompt, activate with `venv\Scripts\activate.bat`. For
macOS/Linux shells, activate with `source venv/bin/activate`.

The separate `api_key.env` file is already present with a placeholder. Replace
`PASTE_YOUR_API_KEY_HERE` on its `AI_API_KEY` line with your own key. Create an
OpenAI API key at <https://platform.openai.com/api-keys>. Keep the key private;
`api_key.env` is excluded by `.gitignore`. The `.env` file is for provider/model
configuration only. The default model is `gpt-4o-mini`; change
`AI_MODEL` to a model available to your API account. `AI_PROVIDER` is currently
`openai`. An optional OpenAI-compatible API endpoint can be set with `AI_BASE_URL`.

Without a configured key, the app prints a JSON notice and uses the local
fallback for its supported request forms. If the API key is rejected, a clear
JSON notice is included and the local fallback is tried. No API key is printed
or stored in attendance data.

## Run

With `venv` activated:

```powershell
python main.py
```

Type a request and press Enter. Type `exit` to quit. Each request result is
printed as JSON.

Examples:

- `What is Aditya's attendance percentage?`
- `Was Sumit present on 10 October 2026?`
- `Mark Lalit present on 12 October 2026.`
- `Mark Anant absent on 13 October 2026.`
- `Remove Krishna's attendance for 9 October 2026.`
- `Show attendance of all students.`
- `Calculate the class average attendance percentage.`

The allowed attendance period is inclusive: 8 October 2026 through 14 October
2026. Marking an existing date updates that record rather than duplicating it.
Removing a record updates the JSON file immediately; removed days no longer
count in that student's total.

## Data and tests

`attendance.json` starts with five sample students and seven explicit daily
records per student. Percentages are recalculated from the records when the
application loads and after every modification. `attendance.json` is
intentionally not ignored by Git.

Run the built-in tests with:

```powershell
python -m unittest discover -s tests -v
```
