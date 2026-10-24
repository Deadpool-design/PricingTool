# Apex Jobs - Fusion 360 add-in.
# One "Apex Orders" button on the Design > Solid tab opens a docked panel (palette/index.html):
#   New order - pick Oscar Award or Baby Birth Letter, fill the form, add to queue or build now.
#   Queue     - every order file in the orders folder (manual now, Shopify later). Build them,
#               then review the screenshots and approve or reject.
# Every build runs in a NEW document, exports STLs and saves review screenshots.

import adsk.core, adsk.fusion, traceback, os, io, re, json, base64, contextlib, threading

from . import award_text
from . import orders as O

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, 'settings.json')
DEFAULT_SETTINGS = {
    'birth_letter_script': r'C:\Users\Mina\Desktop\Apex Prints\Products\Letters\Scripts\birth_letter.py',
    'orders_folder': os.path.join(os.path.expanduser('~'), 'Documents', 'Apex Orders'),
    'letter_overrides': {},     # letter -> {'LAYOUT': {...}, 'SIZE': {...}} saved on approve
}

PANEL_ID = 'ApexPrintsPanel'
CMD_ID = 'ApexOrdersCmd'
PALETTE_ID = 'ApexOrdersPalette'
RUN_EVENT_ID = 'ApexJobsRunEvent'
OPEN_EVENT_ID = 'ApexJobsOpenPanelEvent'
# The desktop shortcut (tools/open-apex-orders.ps1) drops this file to ask for the panel.
OPEN_FLAG = os.path.join(HERE, 'open-panel.flag')

CHECKS = {
    'award': ['Spelling matches the order exactly (customer approves from the screenshot)',
              'Every line reads correctly and nothing touches the plaque edge',
              'No WARNING about a letter hole under 0.95 mm (or it was fixed)',
              'Name is on the LAST line, biggest'],
    'birth': ['Name read LETTER BY LETTER against the order (no dropped letters)',
              'Time, date, weight and height match the order',
              'Logo on the back reads left-to-right',
              'Animal is one clean piece (no blobs between legs)'],
}

app = adsk.core.Application.get()
ui = app.userInterface
_handlers = []      # Fusion only keeps weak refs to handlers
_birth_defaults = None


# ----------------------------------------------------------------------------- settings
def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


def store():
    return O.Store(load_settings()['orders_folder'])


# ----------------------------------------------------------------------------- birth_letter.py
def load_birth_script(path):
    if not os.path.isfile(path):
        raise FileNotFoundError('birth_letter.py not found at %s' % path)
    g = {'__name__': 'birth_letter', '__file__': path}
    with open(path, encoding='utf-8') as f:
        exec(compile(f.read(), path, 'exec'), g)
    return g


def _jsonable(d):
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
        elif isinstance(v, (list, tuple)) and v and all(isinstance(x, (int, float)) for x in v):
            out[k] = list(v)
    return out


def birth_defaults(reload=False):
    """LAYOUT / SIZE defaults read from the real script, so the form always matches it."""
    global _birth_defaults
    if _birth_defaults is None or reload:
        path = load_settings()['birth_letter_script']
        try:
            g = load_birth_script(path)
            _birth_defaults = {'LAYOUT': _jsonable(g.get('LAYOUT')), 'SIZE': _jsonable(g.get('SIZE')),
                               'error': None}
        except Exception as e:
            _birth_defaults = {'LAYOUT': {}, 'SIZE': {}, 'error': str(e)}
    return _birth_defaults


# ----------------------------------------------------------------------------- building
def _shot(path, orientation=None):
    vp = app.activeViewport
    if orientation is not None:
        cam = vp.camera
        cam.viewOrientation = orientation
        cam.isSmoothTransition = False
        vp.camera = cam
        vp.fit()
    adsk.doEvents()
    vp.saveAsImageFile(path, 1200, 800)
    return os.path.basename(path)


def screenshots(order):
    d = store().media_dir(order['id'])
    V = adsk.core.ViewOrientations
    if order['type'] == 'award':   # the script leaves the camera on the plaque mounted on the base
        views = [('on-base', None), ('front', V.FrontViewOrientation)]
    else:   # the script leaves a 3/4 front view - keep that one first
        views = [('three-quarter', None), ('front', V.FrontViewOrientation), ('back', V.BackViewOrientation)]
    out = []
    for name, ori in views:
        try:
            out.append(_shot(os.path.join(d, name + '.png'), ori))
        except Exception:
            pass
    return out


def stl_folder(output):
    for line in output.splitlines():
        m = re.search(r'([A-Za-z]:\\.*?\.stl|/.*?\.stl)\s*$', line, re.I)
        if m:
            return os.path.dirname(m.group(1))
    return None


def run_order(order):
    cfg = O.build_config(order['type'], order['clean'])
    if order['type'] == 'award':
        award_text.build(cfg)
        return
    g = load_birth_script(load_settings()['birth_letter_script'])
    g['CONFIG'].update(cfg)
    for group in ('LAYOUT', 'SIZE'):
        for k, v in (order.get('overrides') or {}).get(group, {}).items():
            g[group][k] = tuple(v) if isinstance(v, list) else v
    g['run']('')


def _is_new_unsaved(doc, before):
    try:
        return doc is not None and doc != before and doc.dataFile is None
    except Exception:
        return False


def build(oid, close_after):
    st = store()
    order = st.get(oid)
    clean, ov, errors, warnings, _ = O.validate(order, birth_defaults())
    if errors:
        order.update(status='failed', result={'error': 'Order is invalid: ' + '; '.join(
            '%s: %s' % kv for kv in errors.items())})
        st.save(order); notify(order); return
    order['clean'] = {k: v for k, v in clean.items() if not k.startswith('_')}   # fields stay as typed
    order['overrides'] = ov
    note = []
    if order['type'] == 'birth' and not ov:
        saved = load_settings()['letter_overrides'].get(clean['_letter'])
        if saved:
            order['overrides'] = saved
            note.append('Used the saved layout for letter %s.' % clean['_letter'])
    order['status'] = 'building'
    st.save(order); notify(order)
    adsk.doEvents()

    before = app.activeDocument
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            run_order(order)
        out = buf.getvalue().strip()
        shots = screenshots(order)
        order['status'] = 'review'
        order['result'] = {
            'output': out, 'notes': note,
            'warnings': warnings + [l for l in out.splitlines() if 'WARNING' in l.upper()],
            'stl_folder': stl_folder(out), 'screenshots': shots,
        }
    except Exception as e:
        order['status'] = 'failed'
        order['result'] = {'error': str(e), 'output': buf.getvalue().strip(), 'notes': note,
                           'trace': traceback.format_exc()}
    if close_after and _is_new_unsaved(app.activeDocument, before):
        try:
            app.activeDocument.close(False)
        except Exception:
            pass
    st.save(order); notify(order)


class RunJobHandler(adsk.core.CustomEventHandler):
    """Builds run from a custom event, outside any command, one per event, so the panel
    stays responsive and each new document is independent."""

    def notify(self, args):
        try:
            data = json.loads(args.additionalInfo)
            build(data['id'], data.get('close_after', False))
        except Exception:
            ui.messageBox('Apex Jobs build error:\n' + traceback.format_exc())


# ----------------------------------------------------------------------------- panel messaging
def palette():
    return ui.palettes.itemById(PALETTE_ID)


def summary(o):
    r = o.get('result') or {}
    return {'id': o['id'], 'type': o.get('type'), 'status': o.get('status'), 'title': O.title(o),
            'source': o.get('source', 'manual'), 'ref': o.get('ref') or {}, 'created': o.get('created'),
            'updated': o.get('updated'), 'warnings': len(r.get('warnings') or []),
            'error': r.get('error')}


def notify(order):
    p = palette()
    if p:
        p.sendInfoToHTML('orderUpdated', json.dumps(summary(order)))


def _img(path):
    with open(path, 'rb') as f:
        return 'data:image/png;base64,' + base64.b64encode(f.read()).decode('ascii')


def handle(action, data):
    st = store()
    s = load_settings()
    if action == 'init':
        bd = birth_defaults()
        return {'settings': {k: s[k] for k in ('birth_letter_script', 'orders_folder')},
                'animals': O.ANIMALS, 'colours': O.COLOURS, 'birthLimits': O.BIRTH_LIMITS,
                'awardDefaults': O.AWARD_DEFAULTS, 'birthDefaults': bd,
                'savedLetters': sorted(s['letter_overrides']),
                'orders': [summary(o) for o in st.all()]}
    if action == 'validate':
        clean, ov, errors, warnings, info = O.validate(data, birth_defaults())
        return {'errors': errors, 'warnings': warnings, 'info': info, 'letter': clean.get('_letter')}
    if action == 'letterOverrides':
        return {'overrides': s['letter_overrides'].get(str(data.get('letter', '')).upper())}
    if action == 'save':
        order = {k: data[k] for k in ('type', 'fields', 'overrides', 'notes') if k in data}
        if data.get('id'):     # editing an existing order keeps its id, source and Shopify ref
            old = st.get(data['id'])
            order = dict(old, **order)
            order.pop('result', None)
        _, _, errors, _, _ = O.validate(order, birth_defaults())
        if errors:
            return {'errors': errors}
        order['status'] = 'pending'
        order = st.save(order)
        if data.get('buildNow'):
            app.fireCustomEvent(RUN_EVENT_ID, json.dumps({'id': order['id'], 'close_after': False}))
        return {'order': summary(order)}
    if action == 'build':
        for oid in data['ids']:
            app.fireCustomEvent(RUN_EVENT_ID, json.dumps({'id': oid, 'close_after': data.get('closeAfter')}))
        return {}
    if action == 'list':
        return {'orders': [summary(o) for o in st.all()]}
    if action == 'get':
        o = st.get(data['id'])
        r = o.get('result') or {}
        d = os.path.join(st.root, o['id'])
        r['images'] = [{'name': n, 'src': _img(os.path.join(d, n))}
                       for n in r.get('screenshots') or [] if os.path.isfile(os.path.join(d, n))]
        o['result'] = r
        o['checks'] = CHECKS[o['type']]
        return {'order': o}
    if action == 'setStatus':
        o = st.get(data['id'])
        o['status'] = data['status']
        if data['status'] == 'approved' and o['type'] == 'birth' and o.get('overrides'):
            letter = (o['clean'].get('letter') or o['clean']['baby_name'][:1]).upper()
            s['letter_overrides'][letter] = o['overrides']
            save_settings(s)
        st.save(o)
        return {'order': summary(o)}
    if action == 'delete':
        st.delete(data['id'])
        return {}
    if action == 'openFolder':
        o = st.get(data['id'])
        folder = (o.get('result') or {}).get('stl_folder') or st.root
        if os.path.isdir(folder) and hasattr(os, 'startfile'):
            os.startfile(folder)
        return {'folder': folder}
    if action == 'saveSettings':
        for k in ('birth_letter_script', 'orders_folder'):
            if data.get(k):
                s[k] = data[k].strip()
        save_settings(s)
        return {'birthDefaults': birth_defaults(reload=True)}
    raise ValueError('Unknown action %s' % action)


class FromHTML(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            data = json.loads(args.data) if args.data else {}
            args.returnData = json.dumps({'ok': True, **(handle(args.action, data) or {})})
        except Exception as e:
            args.returnData = json.dumps({'ok': False, 'error': str(e), 'trace': traceback.format_exc()})


def show_palette():
    p = palette()
    if not p:
        url = os.path.join(HERE, 'palette', 'index.html').replace('\\', '/')
        p = ui.palettes.add(PALETTE_ID, 'Apex Orders', url, True, True, True, 480, 820, True)
        p.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        h = FromHTML(); p.incomingFromHTML.add(h); _handlers.append(h)
    p.isVisible = True


class OpenExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            show_palette()
        except Exception:
            ui.messageBox('Apex Jobs error:\n' + traceback.format_exc())


class OpenCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        h = OpenExecute(); args.command.execute.add(h); _handlers.append(h)


# ----------------------------------------------------------------------------- desktop shortcut
class OpenPanelHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            show_palette()
        except Exception:
            ui.messageBox('Apex Jobs error:\n' + traceback.format_exc())


_stop_watch = threading.Event()


def _watch_flag():
    """Background thread: the shortcut drops OPEN_FLAG; only fireCustomEvent is safe off the main thread."""
    while not _stop_watch.wait(1.0):
        if os.path.exists(OPEN_FLAG):
            try:
                os.remove(OPEN_FLAG)
            except OSError:
                continue
            app.fireCustomEvent(OPEN_EVENT_ID, '')


# ----------------------------------------------------------------------------- add-in lifecycle
def _solid_tab():
    return ui.workspaces.itemById('FusionSolidEnvironment').toolbarTabs.itemById('SolidTab')


def run(context):
    try:
        ev = app.registerCustomEvent(RUN_EVENT_ID)
        h = RunJobHandler(); ev.add(h); _handlers.append(h)
        ev = app.registerCustomEvent(OPEN_EVENT_ID)
        h = OpenPanelHandler(); ev.add(h); _handlers.append(h)
        _stop_watch.clear()
        threading.Thread(target=_watch_flag, daemon=True).start()
        tab = _solid_tab()
        panel = tab.toolbarPanels.itemById(PANEL_ID) or tab.toolbarPanels.add(PANEL_ID, 'Apex Prints')
        defs = ui.commandDefinitions
        cd = defs.itemById(CMD_ID) or defs.addButtonDefinition(
            CMD_ID, 'Apex Orders', 'Oscar Award and Baby Birth Letter orders: fill in, build, review',
            os.path.join(HERE, 'resources'))
        h = OpenCreated(); cd.commandCreated.add(h); _handlers.append(h)
        if not panel.controls.itemById(CMD_ID):
            panel.controls.addCommand(cd).isPromoted = True
    except Exception:
        ui.messageBox('Apex Jobs failed to start:\n' + traceback.format_exc())


def stop(context):
    _stop_watch.set()
    try:
        if palette():
            palette().deleteMe()
        panel = _solid_tab().toolbarPanels.itemById(PANEL_ID)
        if panel and panel.controls.itemById(CMD_ID):
            panel.controls.itemById(CMD_ID).deleteMe()
        if ui.commandDefinitions.itemById(CMD_ID):
            ui.commandDefinitions.itemById(CMD_ID).deleteMe()
        if panel:
            panel.deleteMe()
        app.unregisterCustomEvent(RUN_EVENT_ID)
        app.unregisterCustomEvent(OPEN_EVENT_ID)
    except Exception:
        ui.messageBox('Apex Jobs failed to stop:\n' + traceback.format_exc())
