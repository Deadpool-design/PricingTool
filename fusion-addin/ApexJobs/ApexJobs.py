# Apex Jobs - Fusion 360 add-in.
# Adds an "Apex Prints" panel to the Design > Solid tab with two buttons:
#   Oscar Award        -> arch_award.build()   (from the arch-award-text skill)
#   Baby Birth Letter  -> birth_letter.py on this PC (from the birth-letter skill)
# Each button opens a dialog for the job info, then builds the design in a NEW document
# and exports the STLs. Open designs are never touched.

import adsk.core, adsk.fusion, traceback, os, io, re, json, datetime, contextlib

from . import arch_award

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, 'settings.json')
DEFAULT_SETTINGS = {
    'birth_letter_script': r'C:\Users\Mina\Desktop\Apex Prints\Products\Letters\Scripts\birth_letter.py',
}

PANEL_ID = 'ApexPrintsPanel'
ARCH_CMD_ID = 'ApexOscarAwardCmd'
BIRTH_CMD_ID = 'ApexBabyBirthLetterCmd'
RUN_EVENT_ID = 'ApexJobsRunEvent'

ANIMALS = ['elephant', 'lion', 'unicorn', 'bunny', 'rocking_horse']
COLOURS = ['pink', 'blue']
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']

app = adsk.core.Application.get()
ui = app.userInterface
_handlers = []      # Fusion only keeps weak refs to handlers
_run_event = None


# ----------------------------------------------------------------------------- settings
def load_settings():
    s = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


# ----------------------------------------------------------------------------- job runners
def run_arch(order):
    arch_award.build(order)


def run_birth_letter(order):
    script = order.pop('_script')
    if not os.path.isfile(script):
        raise FileNotFoundError('birth_letter.py not found at:\n%s\n\nFix the path under '
                                '"Advanced" in the Baby Birth Letter dialog.' % script)
    g = {'__name__': 'birth_letter', '__file__': script}
    with open(script, encoding='utf-8') as f:
        exec(compile(f.read(), script, 'exec'), g)
    g['CONFIG'].update(order)
    g['run']('')


JOBS = {
    'arch': ('Oscar Award', run_arch,
             'Get the customer to approve the spelling from the screen before printing.'),
    'birth': ('Baby Birth Letter', run_birth_letter,
              'Read the NAME LETTER BY LETTER against the order (a dropped letter is the known '
              'failure), check the logo on the back reads left-to-right, and get the customer to '
              'approve spelling, time, date, weight and height before printing.'),
}


def stl_folder(output):
    for line in output.splitlines():
        m = re.search(r'([A-Za-z]:\\.*?\.stl|/.*?\.stl)\s*$', line, re.I)
        if m:
            return os.path.dirname(m.group(1))
    return None


class RunJobHandler(adsk.core.CustomEventHandler):
    """Builds run here, outside the command, so the new document is not tied to
    the command's transaction on whatever document was open."""

    def notify(self, args):
        try:
            data = json.loads(args.additionalInfo)
            title, runner, check = JOBS[data['job']]
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    runner(data['order'])
            except Exception as e:
                out = buf.getvalue().strip()
                ui.messageBox('%s FAILED:\n\n%s\n\n%s\n\nClose the Untitled document it left open '
                              '(do not save).' % (title, e, out), title)
                return
            out = buf.getvalue().strip()
            warn = [l for l in out.splitlines() if 'WARNING' in l.upper()]
            msg = '%s built.\n\n' % title
            if data.get('non_latin'):
                msg += ('!! Text is not Latin script - right-to-left shaping is untested. '
                        'Check the design on screen very carefully.\n\n')
            if warn:
                msg += '!! WARNINGS:\n' + '\n'.join(warn) + '\n\n'
            msg += out + '\n\nCHECK BEFORE PRINTING: ' + check
            folder = stl_folder(out)
            if folder and os.path.isdir(folder) and hasattr(os, 'startfile'):
                msg += '\n\nOpen the STL folder now?'
                r = ui.messageBox(msg, title, adsk.core.MessageBoxButtonTypes.YesNoButtonType)
                if r == adsk.core.DialogResults.DialogYes:
                    os.startfile(folder)
            else:
                ui.messageBox(msg, title)
        except Exception:
            ui.messageBox('Apex Jobs error:\n' + traceback.format_exc())


def fire(job, order, non_latin=False):
    app.fireCustomEvent(RUN_EVENT_ID, json.dumps({'job': job, 'order': order, 'non_latin': non_latin}))


def is_non_latin(*texts):
    return any(ord(ch) > 0x24F for t in texts for ch in t)


# ----------------------------------------------------------------------------- Oscar Award dialog
class ArchCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.okButtonText = 'Build'
            ins = cmd.commandInputs
            ins.addTextBoxCommandInput('info', '', '1-3 lines, top to bottom. Letters auto-shrink '
                                       'to fit; over ~20 characters per line gets too small to '
                                       'print well - split it.', 3, True)
            ins.addStringValueInput('line1', 'Line 1 (top)', '')
            ins.addStringValueInput('line2', 'Line 2', '')
            ins.addStringValueInput('line3', 'Line 3', '')
            ins.addStringValueInput('job', 'Job name (optional)', '')
            ins.addTextBoxCommandInput('status', '', '', 2, True)
            adv = ins.addGroupCommandInput('adv', 'Advanced (only if needed)')
            adv.isExpanded = False
            a = adv.children
            a.addStringValueInput('font', 'Font', arch_award.CONFIG['font'])
            a.addFloatSpinnerCommandInput('thick', 'Thickness (mm)', '', 0.8, 3.0, 0.1,
                                          arch_award.CONFIG['thickness_mm'])
            a.addFloatSpinnerCommandInput('raise', 'Text raise (mm)', '', 0.4, 2.0, 0.1,
                                          arch_award.CONFIG['text_raise_mm'])
            for h, cls in ((cmd.inputChanged, ArchChanged), (cmd.validateInputs, ArchValidate),
                           (cmd.execute, ArchExecute)):
                hd = cls(); h.add(hd); _handlers.append(hd)
        except Exception:
            ui.messageBox('Apex Jobs error:\n' + traceback.format_exc())


def arch_lines(ins):
    return [ins.itemById(k).value.strip() for k in ('line1', 'line2', 'line3')
            if ins.itemById(k).value.strip()]


class ArchChanged(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        ins = args.firingEvent.sender.commandInputs  # args.inputs is only the changed input's group
        lines = arch_lines(ins)
        notes = []
        long_ = [l for l in lines if len(l) > 20]
        if long_:
            notes.append('Long line (%d chars) will shrink below ~4.5 mm.' % max(len(l) for l in long_))
        if any(c in ''.join(lines) for c in "'.,`"):
            notes.append('Punctuation prints as tiny islands - may look like blobs.')
        if is_non_latin(*lines):
            notes.append('Non-Latin text: untested, check the result carefully.')
        ins.itemById('status').formattedText = '<b>' + ' '.join(notes) + '</b>' if notes else ''


class ArchValidate(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        args.areInputsValid = len(arch_lines(args.inputs)) >= 1


class ArchExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        ins = args.command.commandInputs
        lines = arch_lines(ins)
        order = {
            'lines': lines,
            'job_name': ins.itemById('job').value.strip(),
            'font': ins.itemById('font').value.strip() or arch_award.CONFIG['font'],
            'thickness_mm': ins.itemById('thick').value,
            'text_raise_mm': ins.itemById('raise').value,
        }
        fire('arch', order, is_non_latin(*lines))


# ----------------------------------------------------------------------------- Baby Birth Letter dialog
TIME_RE = re.compile(r'^([01]?\d|2[0-3]):[0-5]\d$')
DATE_RE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$')


def parse_date(s):
    m = DATE_RE.match(s.strip())
    if not m:
        return None
    try:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


class BirthCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            cmd.okButtonText = 'Build'
            ins = cmd.commandInputs
            ins.addStringValueInput('name', 'Baby name', '')
            ins.addStringValueInput('time', 'Time (HH:MM)', '')
            ins.addStringValueInput('date', 'Date (dd.mm.yyyy)', '')
            ins.addIntegerSpinnerCommandInput('weight', 'Weight (g)', 500, 7000, 10, 3400)
            ins.addFloatSpinnerCommandInput('height', 'Height (cm)', '', 30, 70, 0.5, 50)
            dd = ins.addDropDownCommandInput('animal', 'Animal',
                                             adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, a in enumerate(ANIMALS):
                dd.listItems.add(a.replace('_', ' ').title(), i == 0)
            dd = ins.addDropDownCommandInput('colour', 'Colour',
                                             adsk.core.DropDownStyles.TextListDropDownStyle)
            for i, c in enumerate(COLOURS):
                dd.listItems.add(c.title(), i == 0)
            ins.addTextBoxCommandInput('status', '', '', 3, True)
            adv = ins.addGroupCommandInput('adv', 'Advanced (only if needed)')
            adv.isExpanded = False
            a = adv.children
            a.addStringValueInput('letter', 'Letter (blank = first of name)', '')
            a.addIntegerSpinnerCommandInput('lh', 'Letter height (mm)', 120, 245, 5, 180)
            a.addFloatSpinnerCommandInput('overlap', 'Min overlap', '', 0.4, 1.0, 0.05, 0.6)
            a.addStringValueInput('script', 'birth_letter.py path', load_settings()['birth_letter_script'])
            for h, cls in ((cmd.inputChanged, BirthChanged), (cmd.validateInputs, BirthValidate),
                           (cmd.execute, BirthExecute)):
                hd = cls(); h.add(hd); _handlers.append(hd)
        except Exception:
            ui.messageBox('Apex Jobs error:\n' + traceback.format_exc())


def birth_problems(ins):
    p = []
    if not ins.itemById('name').value.strip():
        p.append('Enter the baby name.')
    if not TIME_RE.match(ins.itemById('time').value.strip()):
        p.append('Time must be HH:MM, 24-hour, no AM/PM.')
    if not parse_date(ins.itemById('date').value):
        p.append('Date must be a real date as dd.mm.yyyy.')
    letter = ins.itemById('letter').value.strip()
    if letter and len(letter) != 1:
        p.append('Letter override must be one character.')
    return p


class BirthChanged(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        ins = args.firingEvent.sender.commandInputs  # args.inputs is only the changed input's group
        notes = []
        d = parse_date(ins.itemById('date').value)
        if d:
            # Spell the date out so 01.12 vs 12.01 mix-ups are caught before building.
            notes.append('Date reads as: <b>%d %s %d</b>' % (d.day, MONTHS[d.month - 1], d.year))
        name = ins.itemById('name').value.strip()
        letter = (ins.itemById('letter').value.strip() or name[:1]).upper()
        if letter in 'IJLTFPY' and letter:
            notes.append('<b>Narrow letter %s: not everything may fit - read the WARNING lines.</b>' % letter)
        if ins.itemById('lh').value > 200:
            notes.append('Over 200 mm tall: consider 25 mm thickness so it does not tip.')
        if is_non_latin(name):
            notes.append('<b>Non-Latin name: untested, check the result carefully.</b>')
        notes += birth_problems(ins)
        ins.itemById('status').formattedText = '<br>'.join(notes)


class BirthValidate(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        args.areInputsValid = not birth_problems(args.inputs)


class BirthExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        ins = args.command.commandInputs
        d = parse_date(ins.itemById('date').value)
        h = ins.itemById('height').value
        script = ins.itemById('script').value.strip()
        order = {
            'baby_name': ins.itemById('name').value.strip(),
            'time': ins.itemById('time').value.strip(),
            'date': '%02d.%02d.%04d' % (d.day, d.month, d.year),
            'weight': '%d g' % ins.itemById('weight').value,
            'height': ('%g cm' % round(h, 1)),
            'animal': ANIMALS[ins.itemById('animal').selectedItem.index],
            'colour': COLOURS[ins.itemById('colour').selectedItem.index],
            '_script': script,
        }
        # Only send overrides that differ from the script defaults.
        if ins.itemById('letter').value.strip():
            order['letter'] = ins.itemById('letter').value.strip().upper()
        if ins.itemById('lh').value != 180:
            order['letter_height_mm'] = ins.itemById('lh').value
        if abs(ins.itemById('overlap').value - 0.6) > 1e-6:
            order['min_overlap'] = ins.itemById('overlap').value
        s = load_settings()
        if script and script != s['birth_letter_script']:
            s['birth_letter_script'] = script
            save_settings(s)
        fire('birth', order, is_non_latin(order['baby_name']))


# ----------------------------------------------------------------------------- add-in lifecycle
def _solid_tab():
    ws = ui.workspaces.itemById('FusionSolidEnvironment')
    return ws.toolbarTabs.itemById('SolidTab')


def run(context):
    global _run_event
    try:
        _run_event = app.registerCustomEvent(RUN_EVENT_ID)
        h = RunJobHandler(); _run_event.add(h); _handlers.append(h)

        defs = ui.commandDefinitions
        panel = _solid_tab().toolbarPanels.itemById(PANEL_ID) or \
            _solid_tab().toolbarPanels.add(PANEL_ID, 'Apex Prints')
        for cid, name, tip, cls in (
                (ARCH_CMD_ID, 'Oscar Award', 'Curved arch award with custom text (ARCH + TEXT STLs)', ArchCreated),
                (BIRTH_CMD_ID, 'Baby Birth Letter', 'Birth-stats letter with inserts (LETTER + inserts STLs)', BirthCreated)):
            cd = defs.itemById(cid) or defs.addButtonDefinition(cid, name, tip)
            hd = cls(); cd.commandCreated.add(hd); _handlers.append(hd)
            if not panel.controls.itemById(cid):
                panel.controls.addCommand(cd).isPromoted = True
    except Exception:
        ui.messageBox('Apex Jobs failed to start:\n' + traceback.format_exc())


def stop(context):
    try:
        panel = _solid_tab().toolbarPanels.itemById(PANEL_ID)
        for cid in (ARCH_CMD_ID, BIRTH_CMD_ID):
            if panel and panel.controls.itemById(cid):
                panel.controls.itemById(cid).deleteMe()
            if ui.commandDefinitions.itemById(cid):
                ui.commandDefinitions.itemById(cid).deleteMe()
        if panel:
            panel.deleteMe()
        app.unregisterCustomEvent(RUN_EVENT_ID)
    except Exception:
        ui.messageBox('Apex Jobs failed to stop:\n' + traceback.format_exc())
