"""FacePoint - the working code. RE-IMPORTED on every command (hot reload).

Nothing may live in a module global between events: the clicks are kept in a hidden
command input. Click anywhere on a face of a solid and a construction point is created
exactly there - Fusion's own Construct menu can only place points on vertices, edges,
plane intersections and centres. For landmarks on a bone (styloid tips, the three
points of the plano articular, Dlab-IT007 5.4).

Verified (2026-10-30, throwaway documents):
- ConstructionSnapPoint takes the point in WORLD space and puts it on the nearest spot
  of the host face, for a face in the root and for the proxy of a face inside an
  occurrence. So the clicked Selection.point goes in as is. Don't run it through the
  face evaluator first: on a proxy face getParameterAtPoint / getPointAtParameter give
  wrong points.
- Points are created in the root component, hosted on the face as clicked (proxy).
- They don't follow the face if the body changes or moves later, like Point at Vertex.
- The marks MUST be drawn in executePreview. Custom graphics drawn in inputChanged are
  thrown away by Fusion at its next preview cycle (it runs one even without a preview
  handler). The first build did that, and the user saw each earlier point vanish on the
  next click. executePreview only fires while the inputs are valid, so one point is
  always enough to be valid, and an empty name falls back to the default.
- No plane option: removed at the user's request in v0.3. Planes are made with
  Fusion's own Plane Through Three Points on the created points.

Moving a point (v0.4, 2026-11-03). Editing a point from the timeline opens Fusion's own
Point dialog, which has no "on face", and an add-in can't replace it. Instead: select
the point and run Point On Face, or pick it in "Point to move". The next click is its
new place, and OK redefines the SAME point (`redefineBySnapPoint`). Its timeline
position and name stay, and whatever is built on it follows.
"""

import adsk.core
import adsk.fusion

import json

PANELS = ['ConstructionPanel']
AFTER = 'ConstructionPointAlongPathCommand'     # last of Fusion's point commands
MARKS_ID = 'FacePoint_marks'
MARK_RADIUS_CM = 0.025                          # 0.25 mm: the bone landmarks are small
MARK_RGB = (255, 120, 0)
LAST_RGB = (230, 30, 30)
DEFAULT_NAME = 'Punt'

T = adsk.fusion.ConstructionSnapPointTypes
S = adsk.core.SurfaceTypes
SNAP_TYPE = {S.NurbsSurfaceType: T.TangentOnSplineConstructionSnapPointType,
             S.CylinderSurfaceType: T.TangentOnCylinderOrConeConstructionSnapPointType,
             S.ConeSurfaceType: T.TangentOnCylinderOrConeConstructionSnapPointType,
             S.SphereSurfaceType: T.TangentOnSphereConstructionSnapPointType,
             S.TorusSurfaceType: T.TangentOnTorusConstructionSnapPointType}


# --------------------------------------------------------------------------- #
# toolbar
# --------------------------------------------------------------------------- #

def place_button(ui, cmd_def):
    """Add the button to PANELS, after Fusion's point commands. Returns the controls."""
    controls = []
    for pid in PANELS:
        panel = ui.allToolbarPanels.itemById(pid)
        if not panel:
            continue
        old = panel.controls.itemById(cmd_def.id)
        if old:
            old.deleteMe()
        ctrl = (panel.controls.addCommand(cmd_def, AFTER, False)
                if panel.controls.itemById(AFTER) else panel.controls.addCommand(cmd_def))
        ctrl.isPromotedByDefault = False
        controls.append(ctrl)
    return controls


# --------------------------------------------------------------------------- #
# creating the points
# --------------------------------------------------------------------------- #

def point_names(base, n):
    """'Punt' for one point, 'Punt 1' .. 'Punt n' for several."""
    return [base] if n == 1 else ['%s %d' % (base, i + 1) for i in range(n)]


def _face(des, pick):
    found = des.findEntityByToken(pick['face'])
    face = adsk.fusion.BRepFace.cast(found[0]) if found else None
    if face is None:
        raise ValueError('A clicked face is no longer there - clear and click again.')
    return face


def _snap(face, xyz):
    return adsk.fusion.ConstructionSnapPoint.create(
        face, None, adsk.core.Point3D.create(*xyz),
        SNAP_TYPE.get(face.geometry.surfaceType, T.DefaultConstructionSnapPointType))


def create_point(des, face, xyz, name):
    """Construction point in the root, on `face` (as clicked, proxy or not) at the
    world point xyz (cm)."""
    root = des.rootComponent
    inp = root.constructionPoints.createInput()
    inp.setBySnapPoint(_snap(face, xyz))
    cp = root.constructionPoints.add(inp)
    cp.name = name
    return cp


def move_point(cp, face, xyz):
    """Put an existing construction point on `face` at xyz, in place: same timeline
    position, same name, dependents follow."""
    redefine = getattr(cp.definition, 'redefineBySnapPoint', None)
    if redefine is None:
        raise ValueError('"%s" is not a point Point On Face can move (it is a %s).'
                         % (cp.name, cp.definition.objectType.split('::')[-1]))
    if not redefine(_snap(face, xyz)):
        raise ValueError('Fusion refused to move "%s" there. Is that face made later in '
                         'the timeline than the point?' % cp.name)


def point_of(entity):
    """The construction point behind a selection: the point itself, or its timeline item."""
    cp = adsk.fusion.ConstructionPoint.cast(entity)
    if cp is None:
        tl = adsk.fusion.TimelineObject.cast(entity)
        cp = adsk.fusion.ConstructionPoint.cast(tl.entity) if tl else None
    return cp


def create_all(des, picks, name, group=False):
    """Points for every pick, optionally all in one timeline group named `name`
    (Dlab-IT007 groups each measurement's entities). Returns the points."""
    points = [create_point(des, _face(des, p), p['xyz'], n)
              for p, n in zip(picks, point_names(name, len(picks)))]
    if group and len(points) > 1 and des.designType == adsk.fusion.DesignTypes.ParametricDesignType:
        g = des.timeline.timelineGroups.add(points[0].timelineObject.index,
                                            points[-1].timelineObject.index)
        g.name = name
    return points


# --------------------------------------------------------------------------- #
# marks - custom graphics found by id, never held in a global
# --------------------------------------------------------------------------- #

def clear_marks(app):
    des = adsk.fusion.Design.cast(app.activeProduct)
    if not des:
        return
    groups = des.rootComponent.customGraphicsGroups
    for i in range(groups.count - 1, -1, -1):
        if groups.item(i).id == MARKS_ID:
            groups.item(i).deleteMe()


def show_marks(app, picks):
    """A small sphere at every click; the last one red."""
    clear_marks(app)
    if picks:
        des = adsk.fusion.Design.cast(app.activeProduct)
        group = des.rootComponent.customGraphicsGroups.add()
        group.id = MARKS_ID
        tbm = adsk.fusion.TemporaryBRepManager.get()
        for i, p in enumerate(picks):
            rgb = LAST_RGB if i == len(picks) - 1 else MARK_RGB
            cg = group.addBRepBody(tbm.createSphere(adsk.core.Point3D.create(*p['xyz']),
                                                    MARK_RADIUS_CM))
            cg.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(
                adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255))
            cg.isSelectable = False
    app.activeViewport.refresh()


# --------------------------------------------------------------------------- #
# command handlers (called by the shell)
# --------------------------------------------------------------------------- #

def _picks(inputs):
    """The stored clicks: [{'xyz': [x, y, z] cm, 'face': token, 'body': name}, ...].

    Fusion lets an entity be selected only once per command, and clicking a selected
    face deselects it, so several points on one face can't all stay selected. Each
    click is recorded here and its selection cleared, leaving the face free."""
    raw = inputs.itemById('picks').value
    return json.loads(raw) if raw else []


def _save_picks(inputs, picks):
    inputs.itemById('picks').value = json.dumps(picks) if picks else ''


def _moving(inputs):
    """The point being moved ("Point to move"), or None when creating new points."""
    sel = inputs.itemById('move')
    return point_of(sel.selection(0).entity) if sel.selectionCount else None


def _record_pick(inputs):
    sel = inputs.itemById('pick')
    if sel.selectionCount == 0:             # our own clearSelection() echoing back
        return False
    s = sel.selection(0)
    face = adsk.fusion.BRepFace.cast(s.entity)
    picks = [] if _moving(inputs) else _picks(inputs)       # moving: the last click wins
    picks.append({'xyz': [s.point.x, s.point.y, s.point.z], 'face': face.entityToken,
                  'body': face.body.name})
    _save_picks(inputs, picks)
    sel.clearSelection()
    return True


def _name(inputs):
    return inputs.itemById('name').value.strip() or DEFAULT_NAME


def _mm(p):
    return '(%.2f, %.2f, %.2f) mm' % (p[0] * 10, p[1] * 10, p[2] * 10)


def _report(inputs):
    picks = _picks(inputs)
    cp = _moving(inputs)
    if cp:
        old = 'Moving <b>%s</b>, now at %s.' % (cp.name, _mm(cp.geometry.asArray()))
        if not picks:
            return old + ('<br>Click on a face where it should go.<br>To create new points '
                          'instead, clear "Point to move".')
        return old + '<br>New place: %s %s<br>Same timeline position; what is built on it ' \
                     'follows.' % (picks[-1]['body'], _mm(picks[-1]['xyz']))
    if not picks:
        return ('Click on a face where you want a point. Click again for more points.<br>'
                'To move an existing point instead, click the "Point to move" box and pick it.')
    return '<br>'.join('<b>%s</b>: %s &nbsp;%s' % (n, p['body'], _mm(p['xyz']))
                       for n, p in zip(point_names(_name(inputs), len(picks)), picks))


def _refresh(inputs):
    """Dialog text, and the inputs that only make sense when creating. The marks are
    drawn by on_preview."""
    moving = _moving(inputs) is not None
    for i in ('undo', 'reset', 'group'):
        inputs.itemById(i).isVisible = not moving
    inputs.itemById('report').formattedText = _report(inputs)


def on_created(app, cmd):
    """'Click on face' comes FIRST: Fusion gives the focus to the first selection input,
    and only the focused one takes clicks. With 'Point to move' first (v0.4), clicks on a
    face did nothing and the dialog could only move points (the user, 2026-11-04)."""
    inputs = cmd.commandInputs
    sel = inputs.addSelectionInput(
        'pick', 'Click on face',
        'Click anywhere on a face of a solid (a bone, NURBS or faceted). Each click adds a '
        'point exactly there; several on the same face are fine.')
    sel.addSelectionFilter('SolidFaces')
    sel.setSelectionLimits(0, 1)
    move = inputs.addSelectionInput(
        'move', 'Point to move (optional)',
        'Leave empty to create new points. To move an existing point instead, click this box '
        'and pick the point: the next click on a face is its new place. It keeps its '
        'timeline position and name, and what is built on it follows.')
    move.addSelectionFilter('ConstructionPoints')
    move.setSelectionLimits(0, 1)
    inputs.addStringValueInput('picks', 'picks', '').isVisible = False
    inputs.addBoolValueInput('undo', 'Remove last point', True, '', False)
    inputs.addBoolValueInput('reset', 'Clear all points', True, '', False)
    inputs.addStringValueInput('name', 'Name', DEFAULT_NAME)
    inputs.addBoolValueInput('group', 'Group in timeline', True, '', True)
    inputs.addTextBoxCommandInput('report', 'Points', '', 6, True)
    # a point selected before the command (timeline or browser) is the one to move
    pre = None
    sels = app.userInterface.activeSelections
    for i in range(sels.count):
        pre = point_of(sels.item(i).entity)
        if pre:
            break
    if pre:
        if move.selectionCount == 0:
            move.addSelection(pre)
        inputs.itemById('name').value = pre.name
        cmd.okButtonText = 'Move point'
    else:
        cmd.okButtonText = 'OK'
    sel.hasFocus = True
    cmd.setDialogMinimumSize(380, 300)
    _refresh(inputs)


def on_input_changed(app, inputs, input_id):
    if input_id == 'pick':
        if not _record_pick(inputs):
            return
    elif input_id == 'move':
        cp = _moving(inputs)
        if cp:
            inputs.itemById('name').value = cp.name
            picks = _picks(inputs)
            _save_picks(inputs, picks[-1:])         # moving takes one place
        try:
            inputs.command.okButtonText = 'Move point' if cp else 'OK'
        except Exception:
            pass
        inputs.itemById('pick').hasFocus = True     # back to clicking on faces
    elif input_id in ('undo', 'reset'):
        box = inputs.itemById(input_id)
        if not box.value:                  # our own untick echoing back
            return
        box.value = False
        picks = _picks(inputs)
        _save_picks(inputs, picks[:-1] if input_id == 'undo' else [])
    elif input_id != 'name':
        return
    _refresh(inputs)


def on_validate(inputs):
    """One point is enough. Anything stricter would also stop the preview, and with it
    the marks (see the module docstring)."""
    return bool(_picks(inputs))


def on_preview(app, cmd):
    """Marks at the clicks; when moving, the point's current place too (orange) with the
    new one red."""
    inputs = cmd.commandInputs
    cp = _moving(inputs)
    old = [{'xyz': list(cp.geometry.asArray())}] if cp else []
    show_marks(app, old + _picks(inputs))


def on_execute(app, cmd):
    clear_marks(app)
    inputs = cmd.commandInputs
    des = adsk.fusion.Design.cast(app.activeProduct)
    cp = _moving(inputs)
    if cp:
        pick = _picks(inputs)[-1]
        move_point(cp, _face(des, pick), pick['xyz'])
        if _name(inputs) != cp.name and inputs.itemById('name').value.strip():
            cp.name = _name(inputs)
        return
    create_all(des, _picks(inputs), _name(inputs), inputs.itemById('group').value)


def on_destroy(app):
    clear_marks(app)
