import sys
import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel

# Plugin information
PLUGIN_NAME = "SelectSimilarColoredFaces"
MENU_NAME = "ToolsMenu"
MENU_LABEL = "Tools"
MENU_ENTRY_LABEL = "Select Similar Colored Faces"
MENU_PARENT = "MayaWindow"

__menu_entry_name = ""  # Store generated menu item, used when unregistering


def maya_useNewAPI():
    """
    The presence of this function tells Maya that the plugin produces, and
    expects to be passed, objects created using the Maya Python API 2.0.
    """
    pass


# =============================== Command ===========================================

class SelectSimilarColoredFacesCmd(om.MPxCommand):
    command_name = "selectSimilarColoredFaces"

    def __init__(self):
        om.MPxCommand.__init__(self)
        
    @staticmethod
    def cmdCreator():
        return SelectSimilarColoredFacesCmd()

    def doIt(self, args):
        select_similar_colored_faces()


def register_command(plugin):
    pluginFn = om.MFnPlugin(plugin)
    try:
        pluginFn.registerCommand(SelectSimilarColoredFacesCmd.command_name, SelectSimilarColoredFacesCmd.cmdCreator)
    except Exception as e:
        sys.stderr.write(f"Failed to register command: {SelectSimilarColoredFacesCmd.command_name}\n")
        raise e


def unregister_command(plugin):
    pluginFn = om.MFnPlugin(plugin)
    try:
        pluginFn.deregisterCommand(SelectSimilarColoredFacesCmd.command_name)
    except Exception as e:
        sys.stderr.write(f"Failed to unregister command: {SelectSimilarColoredFacesCmd.command_name}\n")
        raise e


# =============================== Function Implementation ===========================================

def select_similar_colored_faces():
    """Selects faces on a mesh that have similar vertex colors to the currently selected face."""
    selection = cmds.ls(selection=True)
    if not selection:
        om.MGlobal.displayWarning("Please select a face.")
        return

    mesh = selection[0].split('.')[0]

    # Get the RGB color of the selected face's vertex
    colors = cmds.polyColorPerVertex(selection[0], query=True, colorRGB=True)
    if not colors or len(colors) == 0:
        om.MGlobal.displayWarning("No vertex colors found on the selected face.")
        return

    # Compute the average color for the selected face
    r_average = sum(colors[0::3]) / len(colors[0::3])
    g_average = sum(colors[1::3]) / len(colors[1::3])
    b_average = sum(colors[2::3]) / len(colors[2::3])
    target_color = (r_average, g_average, b_average)

    # Threshold for color matching
    threshold = 0.01

    # Get all faces in the mesh
    all_faces = cmds.ls(mesh + '.f[*]', flatten=True)

    matching_faces = []
    for face in all_faces:
        face_colors = cmds.polyColorPerVertex(face, query=True, colorRGB=True)
        if face_colors:
            r_avg = sum(face_colors[0::3]) / len(face_colors[0::3])
            g_avg = sum(face_colors[1::3]) / len(face_colors[1::3])
            b_avg = sum(face_colors[2::3]) / len(face_colors[2::3])

            if (abs(r_avg - target_color[0]) < threshold and
                abs(g_avg - target_color[1]) < threshold and
                abs(b_avg - target_color[2]) < threshold):
                matching_faces.append(face)

    # Select matching faces
    if matching_faces:
        cmds.select(matching_faces, replace=True)
    else:
        om.MGlobal.displayInfo("No matching faces found.")


# =============================== Menu ===========================================

def show(*args):
    """Runs the command when clicked in the Maya menu."""
    cmds.selectSimilarColoredFaces()


def loadMenu():
    """Setup the Maya menu, runs on plugin enable"""
    global __menu_entry_name

    # Ensure the menu parent exists
    mel.eval("evalDeferred buildFileMenu")

    if not cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
        cmds.menu(MENU_NAME, label=MENU_LABEL, parent=MENU_PARENT)
    
    __menu_entry_name = cmds.menuItem(label=MENU_ENTRY_LABEL, command=show, parent=MENU_NAME)


def unloadMenuItem():
    """Remove the created Maya menu entry, runs on plugin disable"""
    if cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
        menu_long_name = f"{MENU_PARENT}|{MENU_NAME}"
        
        if cmds.menuItem(__menu_entry_name, exists=True):
            cmds.deleteUI(__menu_entry_name, menuItem=True)
        
        if not cmds.menu(menu_long_name, query=True, itemArray=True):
            cmds.deleteUI(menu_long_name, menu=True)


# =============================== Plugin (Un)Load ===========================================

def initializePlugin(plugin):
    """Code to run when the Maya plugin is enabled."""
    register_command(plugin)
    loadMenu()
    om.MGlobal.displayInfo(f"{PLUGIN_NAME} plugin loaded.")


def uninitializePlugin(plugin):
    """Code to run when the Maya plugin is disabled."""
    unregister_command(plugin)
    unloadMenuItem()
    om.MGlobal.displayInfo(f"{PLUGIN_NAME} plugin unloaded.")
