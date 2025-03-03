import sys
import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel

# Plugin information
PLUGIN_NAME = "Magic Wand for Vertex Colors"
MENU_NAME = "ToolsMenu"
MENU_LABEL = "Tools"
MENU_ENTRY_LABEL = "Magic Wand for Vertex Colors"
MENU_PARENT = "MayaWindow"
DEFAULT_THRESHOLD = 1

__menu_entry_name = ""  # Store generated menu item, used when unregistering
_last_message = None  # Store the last displayed message
_threshold_slider = None  # Store reference to the threshold slider
_last_threshold_value = DEFAULT_THRESHOLD  # Store last used threshold value
_color_picker = None  # Store reference to the color picker
_fill_color = [1.0, 1.0, 1.0]  # Default white color
_fill_frame = None  # Store reference to the collapsible frame


def maya_useNewAPI():
	pass


def display_message(message, level="info"):
	"""Displays messages only if they are different from the last one."""
	global _last_message
	if message != _last_message:
		_last_message = message
		if level == "info":
			om.MGlobal.displayInfo(message)
		elif level == "warning":
			om.MGlobal.displayWarning(message)
		elif level == "error":
			om.MGlobal.displayError(message)


def selection_changed_callback(*args):
	"""Callback function that runs whenever the selection changes."""
	global _threshold_slider, _last_threshold_value
	if _threshold_slider and cmds.floatSliderGrp(_threshold_slider, exists=True):
		threshold_value = cmds.floatSliderGrp(_threshold_slider, query=True, value=True)
		_last_threshold_value = threshold_value # Store last used value
		cmds.selectSimilarColoredFaces(threshold_value)
	else:
		cmds.selectSimilarColoredFaces(_last_threshold_value)


def apply_fill_color(*args):
	"""Applies the selected fill color to all selected vertices."""
	global _fill_color
	selection = cmds.ls(selection=True, flatten=True)
	if not selection:
		display_message("Please select vertices to apply the color.", "info")
		return

	try:
		for vertex in selection:
			cmds.polyColorPerVertex(vertex, colorRGB=_fill_color, colorDisplayOption=True)
	except Exception as e:
		display_message(f"Error applying vertex colors: {e}", "error")


def update_fill_color(*args):
	"""Updates the fill color from the RGB UI input and applies it to selected vertices."""
	global _color_picker, _fill_color
	if _color_picker:
		_fill_color = cmds.colorSliderGrp(_color_picker, query=True, rgbValue=True)


def clear_vertex_colors(*args):
	"""Removes vertex colors from the selected faces."""
	selection = cmds.ls(selection=True, flatten=True)
	if not selection:
		display_message("Please, select faces or vertices to clear vertex colors.", "info")
		return
	
	for face in selection:
		try:
			cmds.polyColorPerVertex(face, remove=True)
		except Exception as e:
			continue


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


def select_similar_colored_faces(threshold=DEFAULT_THRESHOLD):
	"""Selects faces on a mesh that have similar vertex colors to the currently selected face."""
	try:
		selection = cmds.ls(selection=True)
		if not selection:
			display_message("Please, select a face.", "info")
			return

		original_face = selection[0]
		mesh = original_face.split('.')[0]
		colors = None

		try:
			# Get the RGB color of the selected face's vertex
			colors = cmds.polyColorPerVertex(original_face, query=True, colorRGB=True)
			if not colors:
				raise ValueError("No vertex colors found on the selected face.")
		except Exception:
			display_message("No vertex colors found on the selected face.", "warning")
			return

		# Compute the average color for the selected face
		r_average = sum(colors[0::3]) / len(colors[0::3])
		g_average = sum(colors[1::3]) / len(colors[1::3])
		b_average = sum(colors[2::3]) / len(colors[2::3])
		target_color = (r_average, g_average, b_average)

		# Convert percentage to actual threshold
		threshold = threshold / 100.0

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

		# Ensure original face is the first in selection
		if original_face in matching_faces:
			matching_faces.remove(original_face)
			matching_faces.insert(0, original_face)

		# Select matching faces
		if matching_faces:
			# Only update selection if it has changed to prevent recursive calls
			current_selection = cmds.ls(selection=True, flatten=True)
			if set(current_selection) != set(matching_faces):
				cmds.select(matching_faces, replace=True)
		else:
			display_message("No matching faces found.", "info")

	except Exception as e:
		display_message(f"Error updating selection: {e}", "error")


def show(*args):
	"""Runs the command when clicked in the Maya menu."""
	open_gui()
	cmds.selectSimilarColoredFaces(_last_threshold_value)


def open_gui():
	"""Creates the GUI for selecting similar faces with a threshold slider."""
	global _threshold_slider
	global _last_threshold_value
	global _color_picker
	global _fill_frame

	if cmds.window("MagicWandForVertexColors", exists=True):
		cmds.deleteUI("MagicWandForVertexColors")

	window = cmds.window("MagicWandForVertexColors", title=MENU_ENTRY_LABEL, widthHeight=(1, 1), resizeToFitChildren=True)
	cmds.columnLayout(adjustableColumn=True)

	_threshold_slider = cmds.floatSliderGrp(
		label="Color Tolerance (%)", field=True, minValue=0, maxValue=100, fieldMinValue=0, fieldMaxValue=100, value=_last_threshold_value,
		dragCommand=lambda x: selection_changed_callback())

	cmds.separator(style="in")

	_fill_frame = cmds.frameLayout(label="Fill Color", collapsable=True, collapse=True, borderStyle="etchedOut")
	cmds.columnLayout(adjustableColumn=True, backgroundColor=[0.25, 0.25, 0.25])
	_color_picker = cmds.colorSliderGrp(label="Fill Color", rgb=_fill_color, changeCommand=update_fill_color)
	cmds.button(label="Apply Fill", command=apply_fill_color)
	cmds.button(label="Clear", command=clear_vertex_colors)
	cmds.setParent('..')
	cmds.setParent('..')

	cmds.separator(style="in")

	cmds.showWindow(window)
	cmds.scriptJob(event=["SelectionChanged", selection_changed_callback], parent=window)


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
