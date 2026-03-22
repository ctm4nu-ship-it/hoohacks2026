from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
import os
import re

import pandas as pd
import requests
import urllib.parse
import hashlib
import requests
from pathlib import Path
from time import time

from fridge_ai import analyze_fridge_image

ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png'}


def _slugify(text: str) -> str:
    text = str(text or '')
    text = re.sub(r"[^a-z0-9]+", '-', text.lower())
    text = re.sub(r'-+', '-', text).strip('-')
    if not text:
        text = hashlib.sha1(str(text).encode('utf-8')).hexdigest()[:8]
    return text


def _color_for(text: str) -> str:
    h = hashlib.sha1(text.encode('utf-8')).hexdigest()
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    r = 180 + (r // 4)
    g = 160 + (g // 6)
    b = 160 + (b // 6)
    return f'rgb({r},{g},{b})'


def _text_color_for_bg(rgb: str) -> str:
    nums = [int(x) for x in re.findall(r'\d+', rgb)]
    luminance = (0.299 * nums[0] + 0.587 * nums[1] + 0.114 * nums[2]) / 255
    return '#111' if luminance > 0.6 else '#fff'

app = Flask(__name__, static_folder='src', static_url_path='', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fridge-chef-change-me')

SESSION_UPLOAD_OK = 'upload_ok'
SESSION_DIETARY_FILTERS = 'dietary_filters'
SESSION_FRIDGE_INGREDIENTS = 'fridge_ingredients'
SESSION_FRIDGE_NOTE = 'fridge_note'
SESSION_FRIDGE_DEMO = 'fridge_demo'
SESSION_FRIDGE_THUMBS = 'fridge_thumbs'

TOP_FRIDGE_MATCHES = 5

RECIPES_CSV = os.path.join(os.path.dirname(__file__), 'recipes.csv')
_recipes_df = None


def _ensure_photo_dir():
    gen_dir = os.path.join(os.path.dirname(__file__), 'src', 'img', 'generated', 'photos')
    os.makedirs(gen_dir, exist_ok=True)
    return gen_dir


def _cached_photo_path(slug: str, ext: str = 'jpg') -> str:
    d = _ensure_photo_dir()
    return os.path.join(d, f"{slug}.{ext}")


def fetch_unsplash_photo(query: str, slug_hint: str = None):
    key = os.environ.get('UNSPLASH_ACCESS_KEY')
    if not key or not query:
        return None
    slug = _slugify(slug_hint or query)
    cached = _cached_photo_path(slug, 'jpg')
    if os.path.exists(cached):
        return f"/img/generated/photos/{os.path.basename(cached)}"

    url = 'https://api.unsplash.com/search/photos'
    params = {'query': query, 'per_page': 1, 'orientation': 'landscape'}
    headers = {'Authorization': f'Client-ID {key}'}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=6)
        if resp.status_code != 200:
            return None
        data = resp.json()
        results = data.get('results') or []
        if not results:
            return None
        img_url = results[0].get('urls', {}).get('regular') or results[0].get('urls', {}).get('small')
        if not img_url:
            return None
        r = requests.get(img_url, stream=True, timeout=8)
        if r.status_code == 200:
            with open(cached, 'wb') as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return f"/img/generated/photos/{os.path.basename(cached)}"
    except Exception:
        return None
    return None


def _ensure_recipe_generated_dir():
    gen_dir = os.path.join(os.path.dirname(__file__), 'src', 'img', 'generated', 'recipes')
    os.makedirs(gen_dir, exist_ok=True)
    return gen_dir


def _default_local_photo():
    return _default_local_photo_for_seed(None)


def _default_local_photo_for_seed(seed: str = None):
    try:
        d = _ensure_photo_dir()
        files = [f for f in os.listdir(d) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if not files:
            return None
        if seed:
            h = int(hashlib.sha1(seed.encode('utf-8')).hexdigest(), 16)
            idx = h % len(files)
            return f"/img/generated/photos/{files[idx]}"
        return f"/img/generated/photos/{files[0]}"
    except Exception:
        return None


def generate_recipe_svg(title: str, subtitle: str = ''):
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


def _extract_primary_ings(ingredient_text: str, max_tokens: int = 2) -> str:
    if not ingredient_text:
        return ''
    toks = re.split(r'[^A-Za-z0-9]+', ingredient_text.lower())
    seen = []
    for t in toks:
        t = t.strip()
        if len(t) <= 2:
            continue
        if t in seen:
            continue
        seen.append(t)
        if len(seen) >= max_tokens:
            break
    return ' '.join(seen)


def _build_photo_queries_for_item(item: dict) -> list:
    title = (item.get('recipe_title') or '').strip()
    category = (item.get('category') or '').strip()
    matched = item.get('matched_ingredients') or []
    ingredient_text = (item.get('ingredient_text') or '').strip()

    if matched:
        ing_terms = ' '.join([str(x).strip() for x in matched[:2] if x])
    else:
        ing_terms = _extract_primary_ings(ingredient_text, max_tokens=2)

    queries = []
    if title and ing_terms:
        queries.append(f"{title} {ing_terms}")
    if title and category:
        queries.append(f"{title} {category}")
    if ing_terms and category:
        queries.append(f"{ing_terms} {category}")
    if ing_terms and title:
        queries.append(f"{ing_terms} {title}")
    if title:
        queries.append(title)
        queries.append(f"{title} recipe")
    if ing_terms:
        queries.append(ing_terms)
    queries.append(f"food {title}" if title else 'food')
    return queries


def _try_queries_for_photo(queries: list, slug_hint: str = None):
    for q in queries:
        try:
            p = fetch_unsplash_photo(q, slug_hint)
            if p:
                return p
        except Exception:
            continue
    return None


DIETARY_FILTER_MAP = {
    'vegan': 'is_vegan',
    'vegetarian': 'is_vegetarian',
    'gluten_free': 'is_gluten_free',
    'dairy_free': 'is_dairy_free',
    'nut_free': 'is_nut_free',
    'halal': 'is_halal',
    'kosher': 'is_kosher',
}

RESULTS_DISPLAY_LIMIT = 10


def get_recipes():
    global _recipes_df
    if _recipes_df is None:
        _recipes_df = pd.read_csv(RECIPES_CSV)
    return _recipes_df


def parse_dietary_form():
    return {key: request.form.get(key, 'No') for key in DIETARY_FILTER_MAP}


def apply_dietary_filters(df, selections):
    out = df
    for form_key, col in DIETARY_FILTER_MAP.items():
        if selections.get(form_key) == 'Yes':
            out = out[out[col] == True]
    return out


def recipes_for_template(df_slice):
    cols = ['recipe_title', 'category', 'subcategory', 'description', 'difficulty', 'ingredient_text']
    present = [c for c in cols if c in df_slice.columns]
    sub = df_slice[present].copy()
    if 'description' in sub.columns:
        sub['description'] = sub['description'].fillna('').astype(str)
    sub = sub.fillna('')
    return sub.to_dict('records')


def ingredient_overlap_score(fridge_items, ingredient_text):
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
            'description': str(row.get('description', '')),
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
    # Clear only application-specific keys but preserve flashed messages
    for k in (SESSION_UPLOAD_OK, SESSION_DIETARY_FILTERS, SESSION_FRIDGE_INGREDIENTS,
              SESSION_FRIDGE_NOTE, SESSION_FRIDGE_DEMO, SESSION_FRIDGE_THUMBS):
        session.pop(k, None)
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
    return render_template('selectFilters.html', fridge_ingredients=session.get(SESSION_FRIDGE_INGREDIENTS) or [])


@app.route('/validate_ingredient', methods=['POST'])
def validate_ingredient():
    data = request.get_json()
    ingredient = (data.get('ingredient') or '').strip()
    if not ingredient:
        return jsonify({'valid': False})

    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        return jsonify({'valid': True})

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[{
                'role': 'user',
                'content': f'Is "{ingredient}" a food ingredient or cooking item? Reply only "yes" or "no".'
            }],
            max_tokens=3
        )
        answer = response.choices[0].message.content.strip().lower()
        return jsonify({'valid': answer.startswith('yes')})
    except Exception:
        return jsonify({'valid': True})


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
    potential_recipes = recipes_for_template(filtered)

    fridge_items = session.get(SESSION_FRIDGE_INGREDIENTS) or []
    kept = request.form.get('fridge_ingredients_kept', '') if request.method == 'POST' else ''
    if kept:
        fridge_items = [i.strip() for i in kept.split(',') if i.strip()]
    extra_ingredients = request.form.get('extra_ingredients', '') if request.method == 'POST' else ''
    if extra_ingredients:
        fridge_items = fridge_items + [i.strip() for i in extra_ingredients.split(',') if i.strip()]
    fridge_note = session.get(SESSION_FRIDGE_NOTE, '')
    fridge_demo = session.get(SESSION_FRIDGE_DEMO, False)
    show_fridge_panel = SESSION_FRIDGE_INGREDIENTS in session
    top_fridge = top_fridge_recipes(filtered, fridge_items, n=TOP_FRIDGE_MATCHES)

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

    try:
        def _dedupe_by_title(lst):
            out = []
            seen = set()
            for item in lst:
                t = (item.get('recipe_title') or '').strip().lower()
                if not t:
                    out.append(item)
                    continue
                if t in seen:
                    continue
                seen.add(t)
                out.append(item)
            return out

        top_fridge = _dedupe_by_title(top_fridge)
        recipes = _dedupe_by_title(recipes)
        potential_recipes = _dedupe_by_title(potential_recipes)

        generic_food = fetch_unsplash_photo('food', 'food') or _default_local_photo()

        def _ensure_photo_for_item(item, slug_hint=None, seed=None):
            title = (item.get('recipe_title') or '').strip()
            if not title and not item:
                return generic_food
            queries = _build_photo_queries_for_item(item)
            photo = _try_queries_for_photo(queries, slug_hint or title)
            if not photo:
                return _default_local_photo_for_seed(seed or (slug_hint or title)) or generic_food
            return photo

        for r in top_fridge:
            r['image_url'] = _ensure_photo_for_item(r, slug_hint=r.get('recipe_title'), seed=r.get('recipe_title'))

        for rec in recipes:
            rec['image_url'] = _ensure_photo_for_item(rec, slug_hint=rec.get('recipe_title'), seed=rec.get('recipe_title'))

        for p in potential_recipes[:RESULTS_DISPLAY_LIMIT]:
            p['image_url'] = _ensure_photo_for_item(p, slug_hint=p.get('recipe_title'), seed=p.get('recipe_title'))
    except Exception:
        pass

    return render_template(
        'results.html',
        recipes=recipes,
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


@app.route('/upload', methods=['POST'])
def upload_image():
    try:
        if 'pdfFile' not in request.files:
            flash('Please upload an image before analyzing.')
            return redirect(url_for('home'))

        file = request.files['pdfFile']

        if file.filename == '':
            flash('Please select an image to upload.')
            return redirect(url_for('home'))

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            flash('Only JPEG and PNG files are allowed. Please upload a supported image.')
            return redirect(url_for('home'))

        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
            flash("Could not analyze the image. Check OPENAI_API_KEY and your network, or try again in a moment.")
            return redirect(url_for('home'))

        if not analysis.get('is_fridge'):
            flash("That photo doesn't look like the inside of a fridge. Please upload a clear photo of your refrigerator contents.")
            return redirect(url_for('home'))

        session[SESSION_FRIDGE_INGREDIENTS] = analysis.get('ingredients') or []
        session[SESSION_FRIDGE_NOTE] = analysis.get('short_notes', '')
        session[SESSION_FRIDGE_DEMO] = bool(analysis.get('demo'))

        try:
            ings = session.get(SESSION_FRIDGE_INGREDIENTS) or []
            thumbs = {}
            for ing in ings:
                try:
                    photo = fetch_unsplash_photo(ing, ing)
                    if not photo:
                        photo = fetch_unsplash_photo(f'food {ing}', ing)
                    if not photo:
                        photo = fetch_unsplash_photo('food', 'food')
                    if photo:
                        thumbs[str(ing)] = photo
                except Exception:
                    continue
            session[SESSION_FRIDGE_THUMBS] = thumbs
        except Exception:
            session[SESSION_FRIDGE_THUMBS] = {}

        session[SESSION_UPLOAD_OK] = True
        return redirect(url_for('select_filters'))

    except Exception as e:
        print(f"Upload error: {e}")
        return f"Upload failed: {str(e)}", 500


if __name__ == '__main__':
    app.run(debug=True, port=1025)