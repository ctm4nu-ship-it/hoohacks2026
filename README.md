# SnapshotChef 📸🍳

An AI-powered web app that analyzes your fridge and suggests recipes based on what's inside.

## How It Works

1. **Upload a fridge photo** — Take a photo of the inside of your fridge
2. **AI analyzes ingredients** — OpenAI's vision model identifies what's in your fridge
3. **Set dietary filters** — Choose from vegan, vegetarian, gluten-free, dairy-free, nut-free, halal, or kosher
4. **Get recipe matches** — See personalized recipe suggestions ranked by ingredient overlap, with food photos powered by Unsplash

## Tech Stack

- **Backend:** Python, Flask
- **AI:** OpenAI API (vision model for fridge analysis)
- **Images:** Unsplash API
- **Data:** Pandas + recipes.csv dataset
- **Frontend:** HTML, CSS, JavaScript (Jinja2 templates)

## Setup

1. Clone the repository:
```bash
   git clone https://github.com/Alish-12/hoohacks2026.git
   cd hoohacks2026/my-website
```

2. Create and activate a virtual environment:
```bash
   python3 -m venv venv
   source venv/bin/activate
```

3. Install dependencies:
```bash
   pip3 install -r requirements.txt
```

4. Create a `.env` file in `my-website/`:
```
   OPENAI_API_KEY=your_openai_key_here
   UNSPLASH_ACCESS_KEY=your_unsplash_key_here
```

5. Run the app:
```bash
   python3 app.py
```

6. Open your browser and go to `http://127.0.0.1:1025`

## Project Structure
```
my-website/
├── app.py              # Flask backend
├── fridge_ai.py        # OpenAI vision analysis
├── recipes.csv         # Recipe dataset
├── requirements.txt
├── templates/          # HTML templates
│   ├── base.html
│   ├── home.html
│   ├── findRecipe.html
│   ├── selectFilters.html
│   └── results.html
├── src/
│   ├── css/
│   ├── js/
│   └── img/
└── uploads/            # Uploaded fridge photos
```

## Built at HooHacks 2026 🎉

Made by the SnapshotChef team at the University of Virginia.
