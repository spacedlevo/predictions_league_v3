# Deploying to PythonAnywhere

This guide covers the initial setup and ongoing update workflow for the Predictions League site on PythonAnywhere.

---

## Prerequisites

- A PythonAnywhere account (free tier works for the subdomain; Hacker+ plan required for a custom domain)
- The repo pushed to GitHub (or another host reachable from PythonAnywhere)

---

## Handling old apps

If you have a previous version of the site (e.g. `predictions_league_v2`) already running on PythonAnywhere, deal with it before creating the new web app.

**Free tier:** PythonAnywhere's free plan allows only one web app. You must delete the old app before you can create a new one.

1. Dashboard → **Web**
2. Scroll to the old app and click **Delete**
3. Confirm the deletion

Once deleted, proceed with the first-time setup below. You can also clean up the old repo directory if you no longer need it:

```bash
rm -rf ~/predictions_league_v2   # adjust the path to match your old repo
```

**Paid plan:** You can run multiple web apps simultaneously. You may keep the old app running while setting up the new one, then delete it once the new one is verified.

---

## First-time setup

### 1. Open a Bash console

From the PythonAnywhere dashboard: **Consoles → Bash**

### 2. Clone the repo

```bash
git clone https://github.com/<your-user>/<your-repo>.git ~/predictions_league_v3
cd ~/predictions_league_v3
```

### 3. Create a virtualenv and install dependencies

```bash
mkvirtualenv --python=python3.10 predictions_league
pip install -r requirements.txt
```

Make a note of the virtualenv path printed at the end (something like `/home/<username>/.virtualenvs/predictions_league`) — you'll need it in step 7.

### 4. Create the `.env` file

```bash
nano ~/predictions_league_v3/.env
```

Paste in the following, filling in your real values:

```
DB_HOST=<username>.mysql.pythonanywhere-services.com
DB_USER=<username>
DB_PASSWORD=<your-mysql-password>
DB_NAME=<username>$predictions
SECRET_KEY=<long-random-string>
```

> **Important:** Do not set `SQLITE_PATH` here. Its absence is what tells the app to use MySQL instead of SQLite.

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

### 5. Create the web app

- Dashboard → **Web → Add a new web app**
- Click **Next**, then choose **Manual configuration** (not "Flask" — that option overwrites your WSGI file)
- Select **Python 3.10**

### 6. Configure the WSGI file

In the Web tab, click the link to your WSGI configuration file (named something like `/var/www/<username>_pythonanywhere_com_wsgi.py`).

Delete the existing contents and replace with:

```python
import sys
import os
from dotenv import load_dotenv

path = '/home/<username>/predictions_league_v3'
if path not in sys.path:
    sys.path.insert(0, path)

load_dotenv(os.path.join(path, '.env'))

from app import create_app
application = create_app()
```

Replace `<username>` with your PythonAnywhere username. Save the file.

> Note: The `wsgi.py` file in the project root is kept for reference only. PythonAnywhere uses its own generated WSGI file (configured above) as the entry point.

### 7. Set the virtualenv path

In the Web tab, find the **Virtualenv** section and enter the path from step 3:

```
/home/<username>/.virtualenvs/predictions_league
```

### 8. Configure static files

In the Web tab, find the **Static files** section and add an entry:

| URL | Directory |
|---|---|
| `/static/` | `/home/<username>/predictions_league_v3/static` |

### 9. Reload and verify

Click **Reload** in the Web tab, then visit:

```
https://<username>.pythonanywhere.com
```

The homepage should load with the league standings.

---

## Updating after code changes

Whenever you push changes to the repo:

```bash
# 1. Open a Bash console on PythonAnywhere
cd ~/predictions_league_v3
git pull

# 2. Only needed if requirements.txt changed
workon predictions_league
pip install -r requirements.txt

# 3. Reload the app
# Option A: Click Reload in the Web tab (simplest)
# Option B: From the Bash console:
touch /var/www/<username>_pythonanywhere_com_wsgi.py
```

All changes — Python code, templates, static files — take effect after a reload. The database is managed by an external script and needs no action here.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| 500 error on every page | Check the error log linked in the Web tab |
| `ModuleNotFoundError` | Virtualenv path is wrong, or `pip install -r requirements.txt` wasn't run |
| Database connection error | Check `.env` values; the `DB_HOST` must use the PythonAnywhere format |
| Static files returning 404 | Confirm the URL and directory in the static files mapping both end with `/` |
| Old code still running after `git pull` | The app wasn't reloaded — hit Reload in the Web tab |
