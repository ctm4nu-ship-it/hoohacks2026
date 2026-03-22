from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import os
import re

import pandas as pd

from fridge_ai import analyze_fridge_image
import hashlib


def _slugify(text: str) -> str:
    text = str(text or '')
    text = re.sub(r"[^a-z0-9]+", '-', text.lower())
    text = re.sub(r'-+', '-', text).strip('-')
    if not text:
        text = hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:8]
    return text


def _ensure_generated_dir():
    gen_dir = os.path.join(os.path.dirname(__file__), 'src', 'img', 'generated')
    os.makedirs(gen_dir, exist_ok=True)
    return gen_dir


def _color_for(text: str) -> str:
    h = hashlib.sha1(text.encode('utf-8')).hexdigest()
    # take first 6 hex for color, but keep it soft
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    # lighten
    r = 180 + (r // 4)
    g = 160 + (g // 6)
    b = 160 + (b // 6)
    return f'rgb({r},{g},{b})'


def _text_color_for_bg(rgb: str) -> str:
    # rgb(r,g,b)
    nums = [int(x) for x in re.findall(r'\d+', rgb)]
    luminance = (0.299 * nums[0] + 0.587 * nums[1] + 0.114 * nums[2]) / 255
    return '#111' if luminance > 0.6 else '#fff'


def generate_ingredient_svg(name: str):
    """Create a simple SVG thumbnail for an ingredient and save to src/img/generated/<slug>.svg"""
    if not name:
        return None
    slug = _slugify(name)
    gen_dir = _ensure_generated_dir()
    path = os.path.join(gen_dir, f"{slug}.svg")
    if os.path.exists(path):
        return f"/img/generated/{slug}.svg"

        bg = _color_for(name)
        fg = _text_color_for_bg(bg)
        label = name.title()
        # Small emoji map for common ingredients
        emoji_map = {
            'milk': '🥛', 'eggs': '🥚', 'cheese': '🧀', 'tomatoes': '🍅', 'lettuce': '🥬',
            'chicken': '🍗', 'beef': '🥩', 'onion': '🧅', 'pepper': '🌶️', 'avocado': '🥑',
            'carrot': '🥕', 'banana': '🍌', 'apple': '🍎', 'potato': '🥔', 'bread': '🍞'
        }
        key = name.strip().lower().split()[0]
        emoji = emoji_map.get(key, '')

        if emoji:
            # big emoji only (no large label) for clearer thumbnails
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="260" viewBox="0 0 400 260">
      <defs>
        <linearGradient id="g" x1="0" x2="1">
          <stop offset="0%" stop-color="{bg}" stop-opacity="0.95"/>
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0.06"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" rx="18" ry="18" fill="url(#g)" />
      <text x="50%" y="52%" dominant-baseline="middle" text-anchor="middle" font-family="Segoe UI Emoji, Noto Color Emoji, Arial" font-size="84">{emoji}</text>
    </svg>'''
        else:
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="260" viewBox="0 0 400 260">
      <rect width="100%" height="100%" rx="18" ry="18" fill="{bg}" />
      <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="30" fill="{fg}">{label}</text>
    </svg>'''

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(svg)
            return f"/img/generated/{slug}.svg"
        except Exception:
            return None


def _ensure_recipe_generated_dir():
    gen_dir = os.path.join(os.path.dirname(__file__), 'src', 'img', 'generated', 'recipes')
    os.makedirs(gen_dir, exist_ok=True)
    return gen_dir


def generate_recipe_svg(title: str, subtitle: str = ''):
    """Generate a simple SVG for a recipe title and return the web path."""
    if not title:
        return None
    slug = _slugify(title)
    gen_dir = _ensure_recipe_generated_dir()
    path = os.path.join(gen_dir, f"{slug}.svg")
    if os.path.exists(path):
        return f"/img/generated/recipes/{slug}.svg"

    bg = _color_for(title)
    fg = _text_color_for_bg(bg)
    title_text = title.title()
    subtitle_text = (subtitle or '').strip()

    # compose SVG with headline and optional subline
    if subtitle_text:
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="340" viewBox="0 0 600 340">
  <rect width="100%" height="100%" rx="18" ry="18" fill="{bg}" />
  <text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="28" fill="{fg}" font-weight="700">{title_text}</text>
  <text x="50%" y="63%" dominant-baseline="middle" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="16" fill="{fg}">{subtitle_text}</text>
</svg>'''
    else:
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="600" height="340" viewBox="0 0 600 340">
  <rect width="100%" height="100%" rx="18" ry="18" fill="{bg}" />
  <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="32" fill="{fg}" font-weight="700">{title_text}</text>
</svg>'''

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(svg)
        return f"/img/generated/recipes/{slug}.svg"
    except Exception:
        return None

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}

app = Flask(__name__, static_folder='src', static_url_path='', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fridge-chef-change-me')

SESSION_UPLOAD_OK = 'upload_ok'
SESSION_DIETARY_FILTERS = 'dietary_filters'
SESSION_FRIDGE_INGREDIENTS = 'fridge_ingredients'
SESSION_FRIDGE_NOTE = 'fridge_note'
SESSION_FRIDGE_DEMO = 'fridge_demo'

TOP_FRIDGE_MATCHES = 5

RECIPES_CSV = os.path.join(os.path.dirname(__file__), 'recipes.csv')
_recipes_df = None

# Form field name -> CSV column (boolean)
DIETARY_FILTER_MAP = {
    'vegan': 'is_vegan',
    'vegetarian': 'is_vegetarian',
    'gluten_free': 'is_gluten_free',
    'dairy_free': 'is_dairy_free',
    'nut_free': 'is_nut_free',
    'halal': 'is_halal',
    'kosher': 'is_kosher',
}

RESULTS_DISPLAY_LIMIT = 100


def get_recipes():
    global _recipes_df
    if _recipes_df is None:
        _recipes_df = pd.read_csv(RECIPES_CSV)
    return _recipes_df


# register slugify for templates
def _jinja_slugify(s):
    return _slugify(s)

app.jinja_env.filters['slugify'] = _jinja_slugify


def parse_dietary_form():
    return {key: request.form.get(key, 'No') for key in DIETARY_FILTER_MAP}


def apply_dietary_filters(df, selections):
    out = df
    for form_key, col in DIETARY_FILTER_MAP.items():
        if selections.get(form_key) == 'Yes':
            out = out[out[col] == True]
    return out


def recipes_for_template(df_slice):
    cols = ['recipe_title', 'category', 'subcategory', 'description', 'difficulty']
    present = [c for c in cols if c in df_slice.columns]
    sub = df_slice[present].copy()
    if 'description' in sub.columns:
        sub['description'] = sub['description'].fillna('').astype(str).str.slice(0, 280)
    sub = sub.fillna('')
    return sub.to_dict('records')


def ingredient_overlap_score(fridge_items, ingredient_text):
    """Return (score, list of matched fridge terms) for recipe ingredient_text."""
    text = (ingredient_text or '').lower()
    matched = []
    score = 0
    seen = set()
    for fi in fridge_items:
        fi = str(fi).strip().lower()
        if len(fi) < 2:
            continue
        if fi in text:
            if fi not in seen:
                matched.append(fi)
                seen.add(fi)
            score += 4
            continue
        for w in re.split(r'[\s,;/]+', fi):
            w = w.strip()
            if len(w) > 2 and w in text and w not in seen:
                matched.append(w)
                seen.add(w)
                score += 1
    return score, matched


def top_fridge_recipes(filtered_df, fridge_items, n=TOP_FRIDGE_MATCHES):
    """
    Rank filtered recipes by overlap between fridge_items and ingredient_text.
    Returns list of dicts with match_score and matched_ingredients.
    """
    if not fridge_items or filtered_df.empty:
        return []

    df = filtered_df.copy()
    if 'ingredient_text' not in df.columns:
        return []

    def score_row(text):
        if pd.isna(text):
            text = ''
        return ingredient_overlap_score(fridge_items, str(text))

    packed = df['ingredient_text'].apply(score_row)
    df['_match_score'] = packed.apply(lambda x: x[0])
    df['_matched'] = packed.apply(lambda x: x[1])
    df = df.sort_values('_match_score', ascending=False)
    top = df.head(n)

    out = []
    for _, row in top.iterrows():
        rec = {
            'recipe_title': row.get('recipe_title', ''),
            'category': row.get('category', ''),
            'subcategory': row.get('subcategory', ''),
            'description': str(row.get('description', ''))[:280],
            'difficulty': row.get('difficulty', ''),
            'match_score': int(row['_match_score']),
            'matched_ingredients': row['_matched'],
        }
        out.append(rec)
    return out


@app.route('/findRecipe.html')
def legacy_find_recipe():
    return redirect(url_for('find_recipe'), code=301)


@app.route('/selectFilters.html')
def legacy_select_filters():
    return redirect(url_for('select_filters'), code=301)


@app.route('/')
def home():
    session.clear()
    return render_template('home.html')


@app.route('/findRecipe')
def find_recipe():
    session.pop(SESSION_UPLOAD_OK, None)
    session.pop(SESSION_DIETARY_FILTERS, None)
    session.pop(SESSION_FRIDGE_INGREDIENTS, None)
    session.pop(SESSION_FRIDGE_NOTE, None)
    session.pop(SESSION_FRIDGE_DEMO, None)
    return render_template('findRecipe.html')


@app.route('/selectFilters')
def select_filters():
    if not session.get(SESSION_UPLOAD_OK):
        flash('Upload a fridge photo first — that unlocks the next step.')
        return redirect(url_for('find_recipe'))
    return render_template('selectFilters.html')


@app.route('/results', methods=['GET', 'POST'])
def results():
    if not session.get(SESSION_UPLOAD_OK):
        flash('Upload a fridge photo first.')
        return redirect(url_for('find_recipe'))

    if request.method == 'POST':
        selections = parse_dietary_form()
        session[SESSION_DIETARY_FILTERS] = selections
    else:
        selections = session.get(SESSION_DIETARY_FILTERS)
        if not selections:
            flash('Choose your dietary filters and press Enter selections.')
            return redirect(url_for('select_filters'))

    df = get_recipes()
    filtered = apply_dietary_filters(df, selections)
    total = len(filtered)
    limited = filtered.head(RESULTS_DISPLAY_LIMIT)
    recipes = recipes_for_template(limited)

    # full potential recipes list
    potential_recipes = recipes_for_template(filtered)

    fridge_items = session.get(SESSION_FRIDGE_INGREDIENTS) or []
    fridge_note = session.get(SESSION_FRIDGE_NOTE, '')
    fridge_demo = session.get(SESSION_FRIDGE_DEMO, False)
    show_fridge_panel = SESSION_FRIDGE_INGREDIENTS in session
    top_fridge = top_fridge_recipes(filtered, fridge_items, n=TOP_FRIDGE_MATCHES)

    # generate recipe images (title-based) and attach `image_url` for template use
    try:
        for r in top_fridge:
            r['image_url'] = generate_recipe_svg(r.get('recipe_title') or '', r.get('category') or '')
        for p in potential_recipes:
            p['image_url'] = generate_recipe_svg(p.get('recipe_title') or '', p.get('category') or '')
    except Exception:
        pass

    labels = {
        'vegan': 'Vegan',
        'vegetarian': 'Vegetarian',
        'gluten_free': 'Gluten-free',
        'dairy_free': 'Dairy-free',
        'nut_free': 'Nut-free',
        'halal': 'Halal',
        'kosher': 'Kosher',
    }
    active_filters = [labels[k] for k, v in selections.items() if v == 'Yes']
    return render_template(
        'results.html',
        recipes=recipes,
        potential_recipes=potential_recipes,
        total_count=total,
        shown_count=min(total, RESULTS_DISPLAY_LIMIT),
        display_limit=RESULTS_DISPLAY_LIMIT,
        selections=selections,
        active_filters=active_filters,
        fridge_ingredients=fridge_items,
        fridge_note=fridge_note,
        fridge_demo=fridge_demo,
        show_fridge_panel=show_fridge_panel,
        top_fridge_recipes=top_fridge,
        top_fridge_count=TOP_FRIDGE_MATCHES,
    )


@app.route('/result', methods=['GET'])
def result_json():
    """Return JSON with listed ingredients and potential recipes matching dietary filters.

    Reads the upload/check state and dietary selections from session and returns:
      {"listed_ingredients": [...], "potential_recipes": [...]} or an error.
    """
    if not session.get(SESSION_UPLOAD_OK):
        return jsonify({"error": "Upload a fridge photo first."}), 400

    selections = session.get(SESSION_DIETARY_FILTERS)
    if not selections:
        return jsonify({"error": "No dietary filters selected."}), 400

    df = get_recipes()
    filtered = apply_dietary_filters(df, selections)

    # Return the full set of filtered recipes (not just the displayed slice).
    potential = recipes_for_template(filtered)

    fridge_items = session.get(SESSION_FRIDGE_INGREDIENTS) or []

    return jsonify({
        "listed_ingredients": fridge_items,
        "potential_recipes": potential,
    })

@app.route('/upload', methods=['POST'])
def upload_image():
    """Handle image file upload from form"""
    try:
        if 'pdfFile' not in request.files:
            return "No file provided", 400
        
        file = request.files['pdfFile']
        
        if file.filename == '':
            return "No file selected", 400
        
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return "Only JPEG and PNG files are allowed", 400
        
        # Create uploads folder if it doesn't exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Save the file (secure name; phones often use .JPG / .PNG)
        filename = secure_filename(file.filename)
        if not filename:
            return "Invalid file name", 400
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        print(f"File saved: {filepath}")
        
        try:
            analysis = analyze_fridge_image(filepath)
        except Exception as exc:
            print(f"Fridge AI error: {exc}")
            flash((
                "Could not analyze the image. Check OPENAI_API_KEY and your network, "
                "or try again in a moment."
            ))
            return redirect(url_for('find_recipe'))

        if not analysis.get('is_fridge'):
            flash(
                "That photo doesn’t look like the inside of a fridge. "
                "Please upload a clear photo of your refrigerator contents."
            )
            return redirect(url_for('find_recipe'))

        session[SESSION_FRIDGE_INGREDIENTS] = analysis.get('ingredients') or []
        session[SESSION_FRIDGE_NOTE] = analysis.get('short_notes', '')
        session[SESSION_FRIDGE_DEMO] = bool(analysis.get('demo'))

        # Generate small SVG thumbnails for detected ingredients so templates can show images.
        try:
            ings = session.get(SESSION_FRIDGE_INGREDIENTS) or []
            for ing in ings:
                try:
                    generate_ingredient_svg(ing)
                except Exception:
                    pass
        except Exception:
            pass

        session[SESSION_UPLOAD_OK] = True
        return redirect(url_for('select_filters'))
    
    except Exception as e:
        print(f"Upload error: {e}")
        return f"Upload failed: {str(e)}", 500 
    

    

if __name__ == '__main__':
    app.run(debug=True, port=1025)
