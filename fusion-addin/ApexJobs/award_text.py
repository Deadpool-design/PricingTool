# Oscar award plaque builder - Script A from the award-text skill (formerly arch-award-text).
# Only change from the skill: run(_context) became build(overrides) so the add-in can pass
# the panel's values without editing CONFIG. Keep it in sync when the skill's Script A changes.
import adsk.core, adsk.fusion, os, struct, re, math

# ======================= JOB CONFIG (edit per order) =======================
CONFIG = {
    'lines': ['Sep 26 Winners', 'Team', 'Farah Helmy'],  # 1-3 lines, top to bottom. LAST line = winner name (biggest)
    'job_name': '',                       # blank = built from the lines
    'small_h_mm': 5.1,                    # letter (cap) height of every line except the last
    'name_h_mm': 6.45,                    # max letter height of the last line; shrinks to fit the width
    'line_heights_mm': None,              # optional explicit list of max heights, one per line (overrides the two above)
    'small_font': 'Franklin Gothic Medium Cond', 'small_font_file': 'FRAMDCN.TTF',
    'name_font': 'Franklin Gothic Demi Cond', 'name_font_file': 'FRADMCN.TTF',
    'name_font_min_h_mm': 6.0,            # if the name shrinks below this, it switches to small_font (Demi 'a' hole closes up)
    # plaque (fits the recess of "Oscar Base v3 - 50x34 Plaque": 51 x 34.6 mm flat)
    'plaque_w_mm': 50.0, 'plaque_h_mm': 34.0, 'plaque_t_mm': 2.0,
    'corner_r_mm': 1.5, 'front_chamfer_mm': 0.4,
    'text_mode': 'raised',                # 'raised' = letters stand proud: ONE colour change per plate. 'inlay' = flush (ragged on X2D, Oct 2026)
    'text_raise_mm': 0.6, 'inlay_depth_mm': 0.6,
    'max_line_len_mm': 46.0, 'line_gap_mm': 3.6, 'v_margin_mm': 3.5,
    'min_text_h_mm': 4.0,                 # refuse below this (counters < ~1 mm, strokes < ~0.6 mm)
    'min_counter_mm': 0.95,               # warn when an enclosed letter hole is narrower (0.68 mm filled in; 1.0+ printed clean)
    'print_face_down': False,             # False = front face up (proven). True = STLs exported front-down (untested)
    'preview_on_base': True,              # adds a non-exported base copy and mounts the plaque on it for the screenshot
    'plaque_color_note': 'gold', 'text_color_note': 'black',
    'out_root': os.path.join(os.path.expanduser('~'), 'Downloads', 'Apex Prints - Oscar', 'Plaque Jobs'),
}
# ===========================================================================

P3 = adsk.core.Point3D.create
VI = adsk.core.ValueInput.createByReal
CM = 0.1  # mm -> cm
FO = adsk.fusion.FeatureOperations

# Oscar base v3 recess (original base size; flat plane 28.174 mm from the axis, floor z 22.5, ceiling z 57.1)
BASE_FLAT_P = 28.174
BASE_FLOOR_Z = 22.5
BASE_PROFILE = [  # (kind, mid, end) in (r, z) mm, starting at (0, 0); 'L' line, 'A' 3-point arc
    ('L', None, (58, 0)), ('L', None, (58, 5.5)),
    ('A', (57.7134, 6.2007), (57.1724, 6.485)), ('A', (56.492, 6.9478), (56.389, 7.7641)),
    ('L', None, (57.7291, 12.1196)), ('A', (57.6368, 12.918), (57.1447, 13.3421)),
    ('L', None, (39.2572, 20.4971)), ('A', (38.2546, 21.3775), (38.0, 22.3541)),
    ('L', None, (38.0, 57.2213)), ('A', (38.1952, 58.0832), (38.5265, 58.5737)),
    ('L', None, (42.964, 63.4084)), ('A', (43.6683, 66.1477), (41.782, 68.2552)),
    ('L', None, (37.0, 70.0)), ('L', None, (6.0, 70.0)), ('L', None, (0.0, 76.0)),
]


def _font_ok(fname):
    dirs = [r'C:\Windows\Fonts', os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts')]
    return any(os.path.exists(os.path.join(d, fname)) for d in dirs)


def _stl(path, bodies, name, face_down, t_mm):
    tris = []
    for b in bodies:
        calc = b.meshManager.createMeshCalculator()
        calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.VeryHighQualityTriangleMesh)
        m = calc.calculate()
        c, idx = m.nodeCoordinatesAsDouble, m.nodeIndices
        for i in range(0, len(idx), 3):
            pts = []
            for k in idx[i:i + 3]:
                x, y, z = c[3 * k] * 10, c[3 * k + 1] * 10, c[3 * k + 2] * 10
                if face_down:            # 180 deg about X: front face lands on the bed, text still reads correctly
                    y, z = -y, t_mm - z
                pts.append((x, y, z))
            a, bb, d = pts
            u = (bb[0] - a[0], bb[1] - a[1], bb[2] - a[2]); v = (d[0] - a[0], d[1] - a[1], d[2] - a[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            L = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1.0
            tris.append(((n[0] / L, n[1] / L, n[2] / L), pts))
    with open(path, 'wb') as f:
        f.write(name.encode('ascii', 'replace')[:80].ljust(80, b' '))
        f.write(struct.pack('<I', len(tris)))
        for n, pts in tris:
            f.write(struct.pack('<3f', *n))
            for p in pts:
                f.write(struct.pack('<3f', *p))
            f.write(b'\x00\x00')
    return len(tris)


def build(overrides=None):
    """Run one plaque job. overrides: dict of CONFIG keys to change for this job only."""
    cfg = dict(CONFIG)
    cfg.update(overrides or {})
    lines = [l for l in cfg['lines'] if l.strip()]
    if not 1 <= len(lines) <= 3:
        raise ValueError('Need 1-3 non-empty text lines, got %d' % len(lines))
    for key in ('small_font_file', 'name_font_file'):
        if cfg[key] and not _font_ok(cfg[key]):
            raise RuntimeError('Font file %s is not installed on this PC' % cfg[key])
    job = cfg['job_name'] or ' - '.join(lines)
    job = re.sub(r'[<>:"/\\|?*]', '', job).strip()[:80]
    W, H, T = cfg['plaque_w_mm'], cfg['plaque_h_mm'], cfg['plaque_t_mm']
    n = len(lines)
    if cfg['line_heights_mm']:
        hmax = list(cfg['line_heights_mm'])
        if len(hmax) != n:
            raise ValueError('line_heights_mm needs %d values' % n)
    else:
        hmax = [cfg['small_h_mm']] * (n - 1) + [cfg['name_h_mm']]
    fonts = [cfg['small_font']] * (n - 1) + [cfg['name_font']]

    # --- new Z-up document (never touch Mina's open designs)
    app = adsk.core.Application.get()
    prefs = app.preferences.generalPreferences
    old = prefs.defaultModelingOrientation
    try:
        prefs.defaultModelingOrientation = adsk.core.DefaultModelingOrientations.ZUpModelingOrientation
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    finally:
        prefs.defaultModelingOrientation = old
    design = adsk.fusion.Design.cast(app.activeProduct)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
    root = design.rootComponent
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = 'Plaque'
    feats = comp.features
    ext = feats.extrudeFeatures

    # --- plaque blank, rounded corners, front-edge chamfer
    sk = comp.sketches.add(comp.xYConstructionPlane); sk.name = 'Plaque outline'
    sk.sketchCurves.sketchLines.addTwoPointRectangle(sk.modelToSketchSpace(P3(-W / 2 * CM, -H / 2 * CM, 0)),
                                                     sk.modelToSketchSpace(P3(W / 2 * CM, H / 2 * CM, 0)))
    ei = ext.createInput(sk.profiles.item(0), FO.NewBodyFeatureOperation)
    ei.setDistanceExtent(False, VI(T * CM))
    f = ext.add(ei); f.name = 'Plaque blank'; f.bodies.item(0).name = 'Plaque'
    plaque = comp.bRepBodies.itemByName('Plaque')
    edges = adsk.core.ObjectCollection.create()
    for e in plaque.edges:
        g = e.geometry
        if isinstance(g, adsk.core.Line3D) and abs(g.startPoint.x - g.endPoint.x) < 1e-6 and abs(g.startPoint.y - g.endPoint.y) < 1e-6:
            edges.add(e)
    fi = feats.filletFeatures.createInput()
    try:
        fi.edgeSetInputs.addConstantRadiusEdgeSet(edges, VI(cfg['corner_r_mm'] * CM), True)
    except Exception:
        fi.addConstantRadiusEdgeSet(edges, VI(cfg['corner_r_mm'] * CM), True)
    feats.filletFeatures.add(fi).name = 'Corner fillets'
    plaque = comp.bRepBodies.itemByName('Plaque')
    top = [fc for fc in plaque.faces if isinstance(fc.geometry, adsk.core.Plane) and fc.geometry.normal.z > 0.99
           and abs(fc.pointOnFace.z - T * CM) < 1e-6][0]
    ce = adsk.core.ObjectCollection.create()
    for e in top.edges:
        ce.add(e)
    ci = feats.chamferFeatures.createInput2()
    ci.chamferEdgeSets.addEqualDistanceChamferEdgeSet(ce, VI(cfg['front_chamfer_mm'] * CM), True)
    feats.chamferFeatures.add(ci).name = 'Front edge chamfer'

    # --- text sketch on the front face plane
    cpi = comp.constructionPlanes.createInput()
    cpi.setByOffset(comp.xYConstructionPlane, VI(T * CM))
    cp = comp.constructionPlanes.add(cpi); cp.name = 'Plaque front'; cp.isLightBulbOn = False
    ts = comp.sketches.add(cp); ts.name = 'Plaque text'

    def S(x, y):
        return ts.modelToSketchSpace(P3(x * CM, y * CM, T * CM))

    def make(s, h, font, xc, yc):
        ti = ts.sketchTexts.createInput2(s, h * CM)
        ti.setAsMultiLine(S(xc - 40, yc - h * 1.5), S(xc + 40, yc + h * 1.5),
                          adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
                          adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0)
        ti.fontName = font
        return ts.sketchTexts.add(ti)

    def bbox(t):
        xs = []; ys = []
        for c in t.asCurves():
            ev = c.evaluator
            ok, p0, p1 = ev.getParameterExtents()
            ok, pts = ev.getStrokes(p0, p1, 0.0005)
            for p in pts:
                xs.append(p.x / CM); ys.append(p.y / CM)
        return min(xs), max(xs), min(ys), max(ys)

    # fit each line to the width; the name falls back to the lighter font when it has to shrink a lot
    hs = []
    for i, s in enumerate(lines):
        for attempt in range(2):
            t = make(s, hmax[i], fonts[i], 0, 0)
            bx = bbox(t); t.deleteMe()
            w = bx[1] - bx[0]
            h = hmax[i] if w <= cfg['max_line_len_mm'] else hmax[i] * cfg['max_line_len_mm'] / w
            if i == n - 1 and n > 1 and fonts[i] != cfg['small_font'] and h < cfg['name_font_min_h_mm'] and attempt == 0:
                fonts[i] = cfg['small_font']
                continue
            break
        hs.append(math.floor(h * 20) / 20.0)
    # fit the block to the plaque height
    usable = H - 2 * cfg['v_margin_mm']
    block = sum(hs) + cfg['line_gap_mm'] * (n - 1)
    if block > usable:
        k = (usable - cfg['line_gap_mm'] * (n - 1)) / sum(hs)
        hs = [math.floor(x * k * 20) / 20.0 for x in hs]
        block = sum(hs) + cfg['line_gap_mm'] * (n - 1)
    if min(hs) < cfg['min_text_h_mm'] - 1e-9:
        raise ValueError('Text too long: needs %.2f mm letters (min %.1f). Shorten the wording or split it into another line.'
                         % (min(hs), cfg['min_text_h_mm']))
    # baseline offset of each font (baseline = text box centre + k*h)
    kf = {}
    for fnt in set(fonts):
        pr = make('H', 10.0, fnt, 0, 0)
        kf[fnt] = bbox(pr)[2] / 10.0
        pr.deleteMe()
    captop = block / 2.0
    info = []
    for i, s in enumerate(lines):
        h = hs[i]
        yb = captop - h
        yc = yb - kf[fonts[i]] * h
        t = make(s, h, fonts[i], 0, yc)
        bx = bbox(t)
        dx = -(bx[0] + bx[1]) / 2.0
        if abs(dx) > 0.02:
            t.deleteMe()
            t = make(s, h, fonts[i], dx, yc)
            bx = bbox(t)
        info.append({'text': s, 'font': fonts[i], 'h': h, 'w': bx[1] - bx[0]})
        captop = yb - cfg['line_gap_mm']
    ts.isVisible = False

    # --- letters as new bodies (one extrude per line); inlay mode also cuts pockets with them
    raised = cfg['text_mode'] == 'raised'
    tdist = cfg['text_raise_mm'] if raised else cfg['inlay_depth_mm']
    tdir = adsk.fusion.ExtentDirections.PositiveExtentDirection if raised else adsk.fusion.ExtentDirections.NegativeExtentDirection
    ztop = T + cfg['text_raise_mm'] if raised else T
    letters = []
    for i in range(ts.sketchTexts.count):
        nb = ext.createInput(ts.sketchTexts.item(i), FO.NewBodyFeatureOperation)
        nb.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(VI(tdist * CM)), tdir)
        nf = ext.add(nb); nf.name = ('Raised text line %d' if raised else 'Text inlay line %d') % (i + 1)
        holes = []
        for j in range(nf.bodies.count):
            b = nf.bodies.item(j)
            letters.append(b)
            for fc in b.faces:
                g = fc.geometry
                if isinstance(g, adsk.core.Plane) and g.normal.z > 0.99 and fc.pointOnFace.z > (ztop - 0.01) * CM:
                    for lp in fc.loops:
                        if not lp.isOuter:
                            lb = lp.boundingBox
                            holes.append(min(lb.maxPoint.x - lb.minPoint.x, lb.maxPoint.y - lb.minPoint.y) * 10)
        info[i]['min_hole'] = min(holes) if holes else None
    for j, b in enumerate(letters, 1):
        b.name = 'Text %02d' % j
    if not raised:
        tools = adsk.core.ObjectCollection.create()
        for b in letters:
            tools.add(b)
        cc = feats.combineFeatures.createInput(comp.bRepBodies.itemByName('Plaque'), tools)
        cc.operation = FO.CutFeatureOperation
        cc.isKeepToolBodies = True
        feats.combineFeatures.add(cc).name = 'Text pockets'
    plaque = comp.bRepBodies.itemByName('Plaque')
    face_down = cfg['print_face_down'] and not raised   # raised letters can only print front up
    bad = [x.name for x in design.timeline if x.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState]
    if bad:
        raise RuntimeError('Unhealthy features: %s' % bad)

    # --- export two STLs (component coordinates, before any preview transform)
    folder = os.path.join(cfg['out_root'], job + (' (raised text)' if raised else ' (inlay)'))
    os.makedirs(folder, exist_ok=True)
    pp = os.path.join(folder, job + ' - PLAQUE.stl')
    pt = os.path.join(folder, job + ' - TEXT.stl')
    _stl(pp, [plaque], 'PLAQUE ' + job, face_down, T)
    _stl(pt, letters, 'TEXT ' + job, face_down, T)

    # --- appearances + optional preview on a copy of the base (not exported)
    try:
        lib = app.materialLibraries.itemByName('Fusion Appearance Library')
        look = {'gold': 'Gold - Polished', 'black': 'Paint - Enamel Glossy (Black)', 'white': 'Paint - Enamel Glossy (White)',
                'silver': 'Aluminum - Polished'}
        ap = lib.appearances.itemByName(look.get(cfg['plaque_color_note'], 'Gold - Polished'))
        at = lib.appearances.itemByName(look.get(cfg['text_color_note'], 'Paint - Enamel Glossy (Black)'))
        plaque.appearance = ap
        for b in letters:
            b.appearance = at
    except Exception:
        lib = None
    if cfg['preview_on_base']:
        bocc = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        bc = bocc.component; bc.name = 'Base preview (not exported)'
        bs = bc.sketches.add(bc.xZConstructionPlane); bs.name = 'Base profile'

        def BP(rz):
            return bs.modelToSketchSpace(P3(rz[0] * CM, 0, rz[1] * CM))
        first = None; sp = None
        for kind, mid, end in BASE_PROFILE:
            if sp is None:
                l0 = bs.sketchCurves.sketchLines.addByTwoPoints(BP((0, 0)), BP(end))
                first, sp = l0.startSketchPoint, l0.endSketchPoint
            elif kind == 'L':
                sp = bs.sketchCurves.sketchLines.addByTwoPoints(sp, BP(end)).endSketchPoint
            else:
                a = bs.sketchCurves.sketchArcs.addByThreePoints(sp, BP(mid), BP(end))
                e = BP(end)
                sp = a.startSketchPoint if a.startSketchPoint.geometry.distanceTo(e) < a.endSketchPoint.geometry.distanceTo(e) else a.endSketchPoint
        bs.sketchCurves.sketchLines.addByTwoPoints(sp, first)
        rin = bc.features.revolveFeatures.createInput(bs.profiles.item(0), bc.zConstructionAxis, FO.NewBodyFeatureOperation)
        rin.setAngleExtent(False, adsk.core.ValueInput.createByString('360 deg'))
        bbody = bc.features.revolveFeatures.add(rin).bodies.item(0)
        rs = bc.sketches.add(bc.yZConstructionPlane)

        def RQ(y, z):
            return rs.modelToSketchSpace(P3(0, y * CM, z * CM))
        rs.sketchCurves.sketchLines.addTwoPointRectangle(RQ(-BASE_FLAT_P, BASE_FLOOR_Z), RQ(-60.0, 57.1))
        ri = bc.features.extrudeFeatures.createInput(rs.profiles.item(0), FO.CutFeatureOperation)
        ri.setSymmetricExtent(adsk.core.ValueInput.createByString('120 mm'), True)
        ri.participantBodies = [bbody]
        bc.features.extrudeFeatures.add(ri)
        if lib:
            bc.bRepBodies.item(0).appearance = lib.appearances.itemByName('Paint - Enamel Glossy (Black)')
        m = adsk.core.Matrix3D.create()
        m.setWithCoordinateSystem(P3(0, -BASE_FLAT_P * CM, (BASE_FLOOR_Z + H / 2) * CM), adsk.core.Vector3D.create(1, 0, 0),
                                  adsk.core.Vector3D.create(0, 0, 1), adsk.core.Vector3D.create(0, -1, 0))
        occ.transform2 = m
        vp = app.activeViewport
        cam = vp.camera
        cam.cameraType = adsk.core.CameraTypes.OrthographicCameraType
        cam.eye = P3(-6, -30, 6.0); cam.target = P3(0, 0, 3.6); cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
        cam.isSmoothTransition = False; cam.isFitView = True
        vp.camera = cam

    # --- report
    vp_ = plaque.volume * 1000; vt = sum(b.volume for b in letters) * 1000
    print('JOB:', job)
    print('Plaque: %.1f x %.1f x %.1f mm, text %s %.1f mm, printed %s' % (W, H, T, 'RAISED' if raised else 'inlaid', tdist, 'FRONT DOWN' if face_down else 'front up'))
    if cfg['print_face_down'] and raised:
        print('NOTE: print_face_down ignored - raised letters must print front up.')
    for i, d in enumerate(info):
        print('Line %d "%s": %s %.2f mm, width %.1f mm, smallest letter hole %s'
              % (i + 1, d['text'], d['font'], d['h'], d['w'], ('%.2f mm' % d['min_hole']) if d['min_hole'] is not None else 'none'))
        if d['min_hole'] is not None and d['min_hole'] < cfg['min_counter_mm']:
            print('WARNING: line %d has a letter hole of %.2f mm (< %.1f). It will likely fill in (blob). '
                  'Use the lighter font, bigger letters or capitals for this line.' % (i + 1, d['min_hole'], cfg['min_counter_mm']))
    if fonts[-1] != cfg['name_font']:
        print('NOTE: the name had to shrink below %.1f mm, so it uses %s instead of %s.' % (cfg['name_font_min_h_mm'], fonts[-1], cfg['name_font']))
    print('Letter bodies: %d' % len(letters))
    print('Volume: plaque %.0f mm3 (~%.2f g), text %.0f mm3 (~%.2f g) at 1.24 g/cm3' % (vp_, vp_ * 0.00124, vt, vt * 0.00124))
    print('PLAQUE STL:', pp)
    print('TEXT STL:', pt)
