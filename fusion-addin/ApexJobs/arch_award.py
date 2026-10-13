# Arch award builder - copied from the arch-award-text skill script.
# Only change from the skill: run(_context) became build(overrides) so the add-in
# can pass the dialog values without editing CONFIG.
import adsk.core, adsk.fusion, os, struct, re

# ======================= JOB CONFIG (edit per order) =======================
CONFIG = {
    'lines': ['Sept Winners', 'Team Farah'],    # 1-3 lines, top to bottom
    'job_name': '',                             # blank = built from the lines
    'arch_color_note': 'gold', 'text_color_note': 'black',
    # geometry (matches the original oscar arch STL, thickened, widened to fill the base neck)
    'inner_r_mm': 38.1, 'thickness_mm': 1.2, 'width_mm': 35.0, 'span_deg': 120.0,
    # text
    'font': 'Arial', 'bold': True, 'text_raise_mm': 0.8,
    'max_text_h_mm': 7.0, 'min_text_h_mm': 3.5, 'max_line_len_mm': 56.0,
    'edge_margin_mm': 3.0, 'line_pitch_factor': 1.75,
    'out_root': os.path.join(os.path.expanduser('~'), 'Downloads', 'Apex Arch Jobs'),
    'new_document': True,
}
# ===========================================================================

P3 = adsk.core.Point3D.create
VI = adsk.core.ValueInput
CM = 0.1  # mm -> cm


def _stl(path, bodies, name):
    tris = []
    for b in bodies:
        calc = b.meshManager.createMeshCalculator()
        calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.VeryHighQualityTriangleMesh)
        m = calc.calculate()
        c, idx = m.nodeCoordinatesAsDouble, m.nodeIndices
        for i in range(0, len(idx), 3):
            pts = [(c[3*k]*10, c[3*k+1]*10, c[3*k+2]*10) for k in idx[i:i+3]]
            a, bb, d = pts
            u = (bb[0]-a[0], bb[1]-a[1], bb[2]-a[2]); v = (d[0]-a[0], d[1]-a[1], d[2]-a[2])
            n = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            L = (n[0]**2 + n[1]**2 + n[2]**2) ** 0.5 or 1.0
            tris.append(((n[0]/L, n[1]/L, n[2]/L), pts))
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
    """Run one arch job. overrides: dict of CONFIG keys to change for this job only."""
    cfg = dict(CONFIG)
    cfg.update(overrides or {})
    lines = [l for l in cfg['lines'] if l.strip()]
    if not 1 <= len(lines) <= 3:
        raise ValueError('Need 1-3 non-empty text lines, got %d' % len(lines))
    job = cfg['job_name'] or ' - '.join(lines)
    job = re.sub(r'[<>:"/\\|?*]', '', job).strip()[:80]

    app = adsk.core.Application.get()
    if cfg['new_document']:
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    root = design.rootComponent
    feats = root.features

    ri, t, w = cfg['inner_r_mm']*CM, cfg['thickness_mm']*CM, cfg['width_mm']*CM
    ro = ri + t

    # --- arch profile on YZ plane, revolved about Z axis (centre = origin, apex at +Y)
    sk = root.sketches.add(root.yZConstructionPlane); sk.name = 'Arch Profile'

    def s(sketch, x, y, z):
        p = sketch.modelToSketchSpace(P3(x, y, z)); return P3(p.x, p.y, 0)

    sk.sketchCurves.sketchLines.addTwoPointRectangle(s(sk, 0, ri, 0), s(sk, 0, ro, w))
    prof = sk.profiles.item(0)

    def revolve(name):
        ri_ = feats.revolveFeatures.createInput(prof, root.zConstructionAxis,
                                                adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
        ri_.setAngleExtent(True, VI.createByString('%g deg' % (cfg['span_deg'] / 2)))
        f = feats.revolveFeatures.add(ri_); f.name = name
        return f.bodies.item(0)

    embossed = revolve('Arch Revolve')

    # --- text sketch on plane 10 mm above the apex
    pi = root.constructionPlanes.createInput()
    pi.setByOffset(root.xZConstructionPlane, VI.createByReal(ro + 1.0))
    pl = root.constructionPlanes.add(pi); pl.name = 'Text Plane'; pl.isLightBulbOn = False
    tsk = root.sketches.add(pl); tsk.name = 'Text'

    def place(h):
        while tsk.sketchTexts.count:
            tsk.sketchTexts.item(0).deleteMe()
        pitch = h * cfg['line_pitch_factor']
        n = len(lines)
        out = []
        for i, txt in enumerate(lines):
            z = w / 2 + (i - (n - 1) / 2) * pitch      # first line = smallest Z = top when read
            c = s(tsk, 0, ro + 1.0, z)
            ti = tsk.sketchTexts.createInput2(txt, h)
            ti.setAsMultiLine(P3(c.x - 6.0, c.y + pitch / 2, 0), P3(c.x + 6.0, c.y - pitch / 2, 0),
                              adsk.core.HorizontalAlignments.CenterHorizontalAlignment,
                              adsk.core.VerticalAlignments.MiddleVerticalAlignment, 0)
            ti.fontName = cfg['font']
            if cfg['bold']:
                ti.textStyle = adsk.fusion.TextStyles.TextStyleBold
            out.append(tsk.sketchTexts.add(ti))
        return out

    def widths(texts):
        return [(x.boundingBox.maxPoint.x - x.boundingBox.minPoint.x) * 10 for x in texts]

    h = cfg['max_text_h_mm'] * CM
    texts = place(h)
    wmax = max(widths(texts))
    # fit width
    if wmax > cfg['max_line_len_mm']:
        h = h * cfg['max_line_len_mm'] / wmax * 0.98
    # fit height (lines stacked across the band width)
    usable = w - 2 * cfg['edge_margin_mm'] * CM
    hfit = usable / (len(lines) * cfg['line_pitch_factor'] - (cfg['line_pitch_factor'] - 1))
    h = min(h, hfit)
    if h < cfg['min_text_h_mm'] * CM - 1e-9:
        raise ValueError('Text too long: would need %.1f mm letters (min %.1f). Shorten text or split lines.'
                         % (h * 10, cfg['min_text_h_mm']))
    texts = place(h)
    ws = widths(texts)
    if max(ws) > cfg['max_line_len_mm'] + 0.5:
        raise ValueError('Line still too wide after fit: %s mm' % [round(x, 1) for x in ws])

    # --- emboss onto the outer cylindrical face
    outer = max((f for f in embossed.faces if f.geometry.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType),
                key=lambda f: f.geometry.radius)
    ei = feats.embossFeatures.createInput(texts, [outer], VI.createByReal(cfg['text_raise_mm'] * CM))
    feats.embossFeatures.add(ei).name = 'Emboss Text'
    tsk.isVisible = False

    # --- split text from arch: plain arch copy, cut it out of the embossed body
    plain = revolve('Arch Plain Revolve')
    tools = adsk.core.ObjectCollection.create(); tools.add(plain)
    ci = feats.combineFeatures.createInput(embossed, tools)
    ci.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    ci.isKeepToolBodies = True
    feats.combineFeatures.add(ci).name = 'Split Text from Arch'
    plain.name = 'Arch'
    letters = [b for b in root.bRepBodies if b.entityToken != plain.entityToken]
    letters.sort(key=lambda b: (b.boundingBox.minPoint.z, b.boundingBox.minPoint.x))
    for i, b in enumerate(letters, 1):
        b.name = 'Text %02d' % i

    bad = [x.name for x in design.timeline
           if x.healthState != adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState]
    if bad:
        raise RuntimeError('Unhealthy features: %s' % bad)

    # --- export two STLs
    folder = os.path.join(cfg['out_root'], job)
    os.makedirs(folder, exist_ok=True)
    pa = os.path.join(folder, job + ' - ARCH.stl')
    pt = os.path.join(folder, job + ' - TEXT.stl')
    _stl(pa, [plain], 'ARCH ' + job)
    _stl(pt, letters, 'TEXT ' + job)

    va = plain.volume * 1000; vt = sum(b.volume for b in letters) * 1000
    bb = plain.boundingBox
    print('JOB:', job)
    print('Arch size mm: %.2f x %.2f x %.2f' % tuple((bb.maxPoint.asArray()[i] - bb.minPoint.asArray()[i]) * 10 for i in range(3)))
    print('Text height used: %.2f mm | line widths mm: %s' % (h * 10, [round(x, 1) for x in ws]))
    if h * 10 < 4.5:
        print('WARNING: text auto-shrunk to %.1f mm - strokes ~%.1f mm wide, borderline for a 0.4 mm nozzle. '
              'Consider shorter wording or splitting into more lines.' % (h * 10, h * 10 * 0.16))
    print('Letter bodies: %d' % len(letters))
    print('Volume: arch %.0f mm3 (~%.2f g), text %.0f mm3 (~%.2f g) at 1.24 g/cm3' % (va, va * 0.00124, vt, vt * 0.00124))
    print('ARCH STL:', pa)
    print('TEXT STL:', pt)
