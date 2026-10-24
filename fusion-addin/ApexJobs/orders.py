# Order model for Apex Jobs. No Fusion imports here on purpose: the same validation is
# used by the panel, and later by whatever drops Shopify orders into the orders folder.
# See ORDER_FORMAT.md for the file format.

import os, re, json, uuid, datetime

TYPES = ('award', 'birth')
STATUSES = ('pending', 'building', 'review', 'approved', 'rejected', 'failed')

ANIMALS = ['elephant', 'lion', 'unicorn', 'bunny', 'rocking_horse']
ANIMAL_ALIASES = {'rabbit': 'bunny', 'horse': 'rocking_horse', 'rockinghorse': 'rocking_horse'}
COLOURS = ['pink', 'blue']
NARROW_LETTERS = 'IJLTFPY'
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

AWARD_DEFAULTS = {'small_h_mm': 5.1, 'name_h_mm': 6.45}
BIRTH_LIMITS = {  # optional numeric fields: (min, max, default shown in the form)
    'letter_height_mm': (100, 245, 180),
    'letter_thickness_mm': (10, 40, 20),
    'min_overlap': (0.3, 1.0, 0.6),
}


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def is_non_latin(*texts):
    return any(ord(ch) > 0x24F for t in texts for ch in t)


def _num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    m = re.match(r'^\s*(-?\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)\s*$', str(v or ''))
    if not m:
        return None
    return float(m.group(1).replace(',', '.')), m.group(2).lower()


# ----------------------------------------------------------------------------- award (Oscar plaque)
# Rules from the award-text skill: 1-3 lines, the LAST line is the winner's name (printed biggest).
# Lines fit a 46 mm width: ~14 characters at 5.1 mm (small lines), ~11 at 6.45 mm (name); longer lines
# shrink, and the script refuses anything that would need letters under 4 mm.
SMALL_FIT_CHARS, NAME_FIT_CHARS, MAX_CHARS = 14, 11, 18
RTL = re.compile('[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]')   # Hebrew / Arabic


def normalize_type(t):
    return 'award' if t in ('award', 'arch', 'oscar') else t   # 'arch' = order files from before the plaque


def validate_award(f):
    errors, warnings, info = {}, [], []
    raw = f.get('lines') or []
    if isinstance(raw, str):
        raw = raw.splitlines()
    lines = [str(l).strip() for l in raw if str(l).strip()]
    if not lines:
        errors['lines'] = 'Enter at least one line (the last line is the winner name).'
    elif len(lines) > 3:
        errors['lines'] = 'Maximum 3 lines.'
    if lines and RTL.search(''.join(lines)):
        errors['lines'] = ('Arabic / right-to-left text cannot be built here: Fusion reverses it and breaks the letter '
                           'joins. Use the manual Inkscape SVG route from the award-text skill.')
    for i, l in enumerate(lines):
        is_name = i == len(lines) - 1 and len(lines) > 1
        fit = NAME_FIT_CHARS if is_name else SMALL_FIT_CHARS
        if len(l) > MAX_CHARS:
            warnings.append('"%s" is %d characters - it will probably need letters under 4 mm and be refused. '
                            'Move a word to another line.' % (l, len(l)))
        elif len(l) > fit:
            warnings.append('"%s" is %d characters - it will shrink below the standard %s size.%s'
                            % (l, len(l), '6.45 mm name' if is_name else '5.1 mm',
                               ' Under 6 mm the name switches to the lighter font.' if is_name else ''))
    if any(c in ''.join(lines) for c in "'.,`"):
        warnings.append('Punctuation prints as tiny islands - check them on the first print.')
    if lines and not errors.get('lines') and is_non_latin(*lines):
        warnings.append('Non-Latin letters: check the screenshots carefully.')
    clean = {'lines': lines, 'job_name': str(f.get('job_name') or '').strip()}
    for k, lo, hi in (('small_h_mm', 4.0, 6.5), ('name_h_mm', 4.0, 8.0)):
        v = f.get(k)
        if v in (None, ''):
            continue
        n = _num(v)
        n = n if isinstance(n, float) else (n[0] if n else None)
        if n is None or not lo <= n <= hi:
            errors[k] = 'Must be %g-%g mm.' % (lo, hi)
        else:
            clean[k] = n
    return clean, errors, warnings, info


# ----------------------------------------------------------------------------- birth
def parse_time(s):
    m = re.match(r'^\s*(\d{1,2})[:.h](\d{2})\s*([ap]\.?m\.?)?\s*$', str(s or ''), re.I)
    if not m:
        return None, False
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap:
        if not 1 <= h <= 12:
            return None, True
        h = h % 12 + (12 if ap.lower().startswith('p') else 0)
    if h > 23 or mi > 59:
        return None, bool(ap)
    return '%02d:%02d' % (h, mi), bool(ap)


def parse_date(s):
    s = str(s or '').strip()
    m = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)   # ISO, what Shopify date pickers send
        if not m:
            return None
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime.date(y, mo, d)
    except ValueError:
        return None


def validate_birth(f, overrides=None, known=None):
    """known: {'LAYOUT': {...}, 'SIZE': {...}} defaults read from birth_letter.py, if available."""
    errors, warnings, info = {}, [], []
    clean = {}
    name = str(f.get('baby_name') or '').strip()
    if not name:
        errors['baby_name'] = 'Enter the baby name.'
    clean['baby_name'] = name

    t, had_ampm = parse_time(f.get('time'))
    if not t:
        errors['time'] = 'Use HH:MM (24-hour), e.g. 11:10.'
    else:
        clean['time'] = t
        if had_ampm:
            info.append('Time converted to 24-hour: %s (printed without AM/PM).' % t)

    raw_date = str(f.get('date') or '').strip()
    d = parse_date(raw_date)
    if not d:
        errors['date'] = ('Use dd.mm.yyyy (or yyyy-mm-dd). Slashes are refused on purpose: '
                          '01/12 could be 1 Dec or 12 Jan.')
    else:
        clean['date'] = '%02d.%02d.%04d' % (d.day, d.month, d.year)
        info.append('Date reads as: %d %s %d' % (d.day, MONTHS[d.month - 1], d.year))
        if d > datetime.date.today():
            warnings.append('Date is in the future - check it.')

    w = _num(f.get('weight'))
    if isinstance(w, tuple):
        w = w[0] * 1000 if w[1] in ('kg',) else (w[0] if w[1] in ('', 'g', 'gr') else None)
    if w is None or not 300 <= w <= 7000:
        errors['weight'] = 'Weight in grams, 300-7000 (e.g. 3415 or 3.415 kg).'
    else:
        clean['weight_g'] = int(round(w))

    h = _num(f.get('height'))
    if isinstance(h, tuple):
        h = h[0] / 10 if h[1] == 'mm' else (h[0] if h[1] in ('', 'cm') else None)
    if h is None or not 25 <= h <= 70:
        errors['height'] = 'Height in cm, 25-70 (e.g. 51).'
    else:
        clean['height_cm'] = round(h, 1)

    a = re.sub(r'[\s-]+', '_', str(f.get('animal') or '').strip().lower())
    a = ANIMAL_ALIASES.get(a.replace('_', ''), a)
    if a not in ANIMALS:
        errors['animal'] = 'Pick one of: %s.' % ', '.join(ANIMALS)
    clean['animal'] = a

    c = str(f.get('colour') or f.get('color') or '').strip().lower()
    if c not in COLOURS:
        errors['colour'] = 'Pink or blue.'
    clean['colour'] = c

    letter = str(f.get('letter') or '').strip().upper()
    if letter and len(letter) != 1:
        errors['letter'] = 'One character only.'
    if letter:
        clean['letter'] = letter
    eff_letter = letter or name[:1].upper()
    clean['_letter'] = eff_letter

    for k, (lo, hi, _) in BIRTH_LIMITS.items():
        v = f.get(k)
        if v in (None, ''):
            continue
        n = _num(v)
        n = n if isinstance(n, float) else (n[0] if n else None)
        if n is None or not lo <= n <= hi:
            errors[k] = 'Must be %g-%g.' % (lo, hi)
        else:
            clean[k] = n

    if eff_letter and eff_letter in NARROW_LETTERS:
        warnings.append('Narrow letter %s: not everything fits at default sizes. Expect WARNING lines '
                        'and use the layout overrides if an insert sits badly.' % eff_letter)
    if clean.get('letter_height_mm', 180) > 200 and clean.get('letter_thickness_mm', 20) < 25:
        warnings.append('Over 200 mm tall: set thickness to 25 mm so it does not tip.')
    if is_non_latin(name):
        warnings.append('Non-Latin name: right-to-left shaping is untested. Check the screenshots carefully.')

    ov, ov_err = clean_overrides(overrides or {}, known)
    if ov_err:
        errors['overrides'] = ov_err
    return clean, errors, warnings, info, ov


def clean_overrides(ov, known=None):
    out = {}
    for group in ('LAYOUT', 'SIZE'):
        for k, v in (ov.get(group) or {}).items():
            if v in (None, '', []):
                continue
            if known and known.get(group) and k not in known[group]:
                return out, 'Unknown %s key "%s".' % (group, k)
            try:
                if isinstance(v, (list, tuple)):
                    default = (known or {}).get(group, {}).get(k)
                    vals = []
                    for i, x in enumerate(v):
                        if x in (None, ''):
                            if not default:
                                raise ValueError
                            x = default[i]
                        vals.append(float(x))
                    if group == 'LAYOUT' and not all(-0.2 <= x <= 1.2 for x in vals):
                        return out, 'LAYOUT %s must be fractions of the letter (0-1).' % k
                    v = vals
                else:
                    v = float(v)
                    if v <= 0:
                        raise ValueError
            except (TypeError, ValueError, IndexError):
                return out, 'Bad value for %s %s.' % (group, k)
            out.setdefault(group, {})[k] = v
    return out, None


def validate(order, known=None):
    """Returns (clean_fields, overrides, errors, warnings, info)."""
    otype = normalize_type(order.get('type'))
    if otype == 'award':
        f, e, w, i = validate_award(order.get('fields') or {})
        return f, {}, e, w, i
    if otype == 'birth':
        f, e, w, i, ov = validate_birth(order.get('fields') or {}, order.get('overrides'), known)
        return f, ov, e, w, i
    return {}, {}, {'type': 'Unknown order type.'}, [], []


def title(order):
    f = order.get('fields') or {}
    if normalize_type(order.get('type')) == 'award':
        raw = f.get('lines') or []
        raw = raw.splitlines() if isinstance(raw, str) else raw
        return ' / '.join(str(l).strip() for l in raw if str(l).strip()) or 'Oscar Award'
    return f.get('baby_name') or 'Baby Birth Letter'


def build_config(otype, f):
    """Validated fields -> the CONFIG keys each script expects."""
    if normalize_type(otype) == 'award':
        cfg = {'lines': f['lines'], 'job_name': f.get('job_name', '')}
        for k in ('small_h_mm', 'name_h_mm'):
            if k in f:
                cfg[k] = f[k]
        return cfg
    cfg = {
        'baby_name': f['baby_name'], 'time': f['time'], 'date': f['date'],
        'weight': '%d g' % f['weight_g'], 'height': '%g cm' % f['height_cm'],
        'animal': f['animal'], 'colour': f['colour'],
    }
    for k in ('letter', 'letter_height_mm', 'letter_thickness_mm', 'min_overlap'):
        if k in f:
            cfg[k] = f[k]
    return cfg


# ----------------------------------------------------------------------------- store
class Store:
    """One JSON file per order in <root>/<id>.json; screenshots in <root>/<id>/."""

    def __init__(self, root):
        self.root = root
        os.makedirs(root, exist_ok=True)

    def path(self, oid):
        return os.path.join(self.root, oid + '.json')

    def media_dir(self, oid):
        d = os.path.join(self.root, oid)
        os.makedirs(d, exist_ok=True)
        return d

    def new_id(self, order):
        slug = re.sub(r'[^a-z0-9]+', '-', title(order).lower()).strip('-')[:30] or order['type']
        return '%s-%s-%s' % (datetime.datetime.now().strftime('%Y%m%d-%H%M%S'), slug, uuid.uuid4().hex[:4])

    def save(self, order):
        order.setdefault('id', self.new_id(order))
        order.setdefault('created', now())
        order.setdefault('status', 'pending')
        order.setdefault('source', 'manual')
        order['updated'] = now()
        tmp = self.path(order['id']) + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(order, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path(order['id']))
        return order

    def get(self, oid):
        with open(self.path(oid), encoding='utf-8') as fh:
            o = json.load(fh)
        o['id'] = oid   # file name wins, so a hand-written file cannot point elsewhere
        o['type'] = normalize_type(o.get('type'))
        return o

    def all(self):
        out = []
        for fn in os.listdir(self.root):
            if not fn.endswith('.json'):
                continue
            try:
                o = self.get(fn[:-5])
            except (OSError, ValueError):
                continue
            if o.get('status') not in STATUSES:
                o['status'] = 'pending'
            out.append(o)
        out.sort(key=lambda o: o.get('created', ''), reverse=True)
        return out

    def delete(self, oid):
        import shutil
        try:
            os.remove(self.path(oid))
        except OSError:
            pass
        shutil.rmtree(os.path.join(self.root, oid), ignore_errors=True)
