"""FacePoint - Fusion 360 add-in. THIS FILE IS THE SHELL, NOT THE WORK.

Lifecycle, the toolbar button and event wiring. All the real code lives in fp_core.py
and is RE-IMPORTED FRESH on every command, so editing it takes effect on the next
click. Only changes to this file need the add-in stopped and run again.
"""

import adsk.core
import adsk.fusion

import importlib
import os
import sys
import time
import traceback

CMD_ID = 'FacePoint_PointOnFace'
CMD_NAME = 'Point On Face'
CMD_TOOLTIP = (
    'Create construction points exactly where you click on a face.\n\n'
    'Click anywhere on a solid, including an organic NURBS bone: each click adds a point, '
    'several on the same face are fine. For landmarks such as the styloid tips or the '
    'points of the plano articular (Dlab-IT007 5.4).'
)

ADDIN_DIR = os.path.dirname(os.path.realpath(__file__))
RES_DIR = os.path.join(ADDIN_DIR, 'resources', 'FacePoint')
LOG_PATH = os.path.join(ADDIN_DIR, 'FacePoint.log')
OWN_MODULES = ('fp_core',)

_app = None
_ui = None
_handlers = []
_controls = []


def _log(msg):
    try:
        with open(LOG_PATH, 'a', encoding='utf-8') as fh:
            fh.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


def _core():
    """Fresh import of the worker module. This is the hot reload.

    Fusion runs every add-in and script in ONE Python: drop a same-named module loaded
    from elsewhere and keep this folder first on sys.path, so the add-in always runs
    its own installed files."""
    while ADDIN_DIR in sys.path:
        sys.path.remove(ADDIN_DIR)
    sys.path.insert(0, ADDIN_DIR)
    here = os.path.normcase(ADDIN_DIR)
    for name in OWN_MODULES:
        mod = sys.modules.get(name)
        if mod and os.path.normcase(os.path.dirname(os.path.realpath(mod.__file__))) != here:
            del sys.modules[name]
    if 'fp_core' in sys.modules:
        return importlib.reload(sys.modules['fp_core'])
    return importlib.import_module('fp_core')


def _fail(where):
    tb = traceback.format_exc()
    _log('%s\n%s' % (where, tb))
    if _ui:
        _ui.messageBox('%s\n\n%s\n\nFull traceback in\n%s'
                       % (where, tb.strip().splitlines()[-1], LOG_PATH), CMD_NAME)


# --------------------------------------------------------------------------- #
# command handlers - thin, they only delegate
# --------------------------------------------------------------------------- #

class _Created(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            cmd = args.command
            _core().on_created(_app, cmd)
            for h, ev in ((_Execute(), cmd.execute),
                          (_Preview(), cmd.executePreview),
                          (_Changed(), cmd.inputChanged),
                          (_Validate(), cmd.validateInputs),
                          (_Destroy(), cmd.destroy)):
                ev.add(h)
                _handlers.append(h)
        except Exception:
            _fail('Point On Face could not open its dialog.')


class _Execute(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            sys.modules['fp_core'].on_execute(_app, args.command)
        except Exception:
            _fail('Point On Face failed.')


class _Preview(adsk.core.CommandEventHandler):
    """Draws the marks: graphics drawn anywhere else are dropped by Fusion."""

    def notify(self, args):
        try:
            sys.modules['fp_core'].on_preview(_app, args.command)
        except Exception:
            _log(traceback.format_exc())


class _Changed(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            sys.modules['fp_core'].on_input_changed(
                _app, args.input.parentCommand.commandInputs, args.input.id)
        except Exception:
            _log(traceback.format_exc())


class _Validate(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            args.areInputsValid = sys.modules['fp_core'].on_validate(args.inputs)
        except Exception:
            args.areInputsValid = False


class _Destroy(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            sys.modules['fp_core'].on_destroy(_app)
        except Exception:
            _log(traceback.format_exc())


# --------------------------------------------------------------------------- #
# add-in entry points
# --------------------------------------------------------------------------- #

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        old = _ui.commandDefinitions.itemById(CMD_ID)
        if old:
            old.deleteMe()
        cmd_def = _ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, CMD_TOOLTIP, RES_DIR)
        h = _Created()
        cmd_def.commandCreated.add(h)
        _handlers.append(h)
        _controls[:] = _core().place_button(_ui, cmd_def)
        _log('started, button in %d panel(s)' % len(_controls))
    except Exception:
        _fail('FacePoint failed to start.')


def stop(context):
    try:
        for ctrl in _controls:
            try:
                ctrl.deleteMe()
            except Exception:
                pass
        _controls[:] = []
        cmd_def = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.deleteMe()
        _handlers[:] = []
        _log('stopped')
    except Exception:
        _fail('FacePoint failed to stop.')
