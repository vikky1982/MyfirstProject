# Word Quest

Word Quest helps a child learn vocabulary a little at a time.

- **5 new words** each day, with a meaning, a tip, an example, and a quick check
- Words move through six levels — Seedling, Sprout, Explorer, Scholar, Champion, and Word Wizard — so they **get harder as you go**
- A **10-question quiz** after every **30 words**, before the next words unlock
- **Progress** is saved on this browser: words learned, streak, level, and quiz scores
- **15 minutes** of active use per day, then the lesson locks until the next local day

Unfinished words carry to the next day and count toward that day's five. Time away from the page does not count. The day follows the clock on the device.

## Run it

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/ and enter a name. Olive gives you a return code so the same progress can be opened on another device. The same first name does not share someone else's words.

The older employee pages are still at `/employee/` on your own computer. They are hidden when the site is started for the public internet.

## Tests

```bash
python manage.py test vocabulary
```
