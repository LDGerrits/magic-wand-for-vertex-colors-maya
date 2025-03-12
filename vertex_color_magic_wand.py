import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel
import math
import colorsys

# Plugin information
PLUGIN_NAME = "Magic Wand for Vertex Colors"
MENU_NAME = "ToolsMenu"
MENU_LABEL = "Tools"
MENU_ENTRY_LABEL = "Magic Wand for Vertex Colors"
MENU_PARENT = "MayaWindow"
IMAGE_ICON_NAME = "magic_wand_icon.png"
DEFAULT_THRESHOLD = 1
MAX_RGB_DISTANCE = math.sqrt(3)  # max distance possible in RGB
DEFAULT_INACTIVE_COLOR = [0.0, 0.0, 0.0]

__menu_entry_name = ""  # Store generated menu item, used when unregistering
_last_message = None  # Store the last displayed message
_threshold_slider = None  # Store reference to the threshold slider
_last_threshold_value = DEFAULT_THRESHOLD  # Store last used threshold value
_color_picker = None  # Store reference to the color picker
_fill_color = DEFAULT_INACTIVE_COLOR
_fill_frame = None  # Store reference to the collapsible frame
_continuous_checkbox = None
_target_color = None  # Persistently stores the initial selected face color
_initial_face = None  # Stores the initially selected face
_current_color_display = None  # UI element for showing current selected color
_current_color_text = None  # Text field for RGB/HSV values
_stored_selected_faces = set() # Holds previously selected faces for multi-selection


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
	try:
		global _threshold_slider, _last_threshold_value, _target_color, _initial_face, _stored_selected_faces

		# om.MGlobal.displayInfo("Selection changed")
	
		current_selection = cmds.ls(selection=True, flatten=True)

		# Case 1: Selection is cleared (reset variables)
		if not current_selection:
			_initial_face = None
			_target_color = None
			_stored_selected_faces.clear()
			update_current_color_display(None)  # Clear UI
			return

		# Find the newest selected face
		new_faces = set(current_selection) - _stored_selected_faces  # Faces in current_selection but NOT in _stored_selected_faces

		# Detect if Shift is held (multi-selection mode)
		shift_pressed = cmds.getModifiers() & 1  # Shift key = 1

		# Case 2: New selection
		# user_selected = _initial_face not in current_selection
		if new_faces and len(new_faces)>0: # and user_selected:
			selected_face = list(new_faces)[0]  # Pick one of the newly added faces
			om.MGlobal.displayInfo(f"Newest Selected Face: {selected_face}")

			if shift_pressed:
				# om.MGlobal.displayInfo("Multi-selection mode enabled (Shift held).")
				_stored_selected_faces.update(current_selection)  # Store all selected faces
			# else:
			# 	om.MGlobal.displayInfo("Single-selection mode.")
			# 	_stored_selected_faces.clear()  # Reset stored selections

			# Update _initial_face & _target_color
			_initial_face = selected_face
			_target_color = get_face_color(_initial_face)
			update_current_color_display(_target_color)

		# Case 3: User moves the slider, but selection remains
		if _threshold_slider and cmds.floatSliderGrp(_threshold_slider, exists=True):
			threshold_value = cmds.floatSliderGrp(_threshold_slider, query=True, value=True)
			_last_threshold_value = threshold_value

		select_similar_colored_faces(threshold_value, shift_pressed)
	
	except Exception as e:
		return


def slider_changed_callback(*args):
	global _threshold_slider, _last_threshold_value, _stored_selected_faces
	if _threshold_slider and cmds.floatSliderGrp(_threshold_slider, exists=True):
		threshold_value = cmds.floatSliderGrp(_threshold_slider, query=True, value=True)
		_last_threshold_value = threshold_value

	# om.MGlobal.displayInfo(f"{len(_stored_selected_faces)}")
	select_similar_colored_faces(threshold_value, len(_stored_selected_faces) > 0)
	
	
def apply_fill_color(*args):
	"""Applies the selected fill color to all selected vertices."""
	global _fill_color
	selection = cmds.ls(selection=True, flatten=True)
	if not selection:
		display_message("Please select vertices to apply the color.", "info")
		return
	try:
		for vertex in selection:
			cmds.polyColorPerVertex(
				vertex, colorRGB=_fill_color, colorDisplayOption=True
			)
		if _initial_face:
			_target_color = get_face_color(_initial_face)
			update_current_color_display(_target_color)
	except Exception as e:
		display_message(f"Error applying vertex colors: {e}", "error")


def fill_color_changed_callback(*args):
	"""Updates the fill color from the RGB UI input and applies it to selected vertices."""
	global _color_picker, _fill_color
	if _color_picker:
		_fill_color = cmds.colorSliderGrp(_color_picker, query=True, rgbValue=True)


def clear_vertex_colors(*args):
	"""Removes vertex colors from the selected faces."""
	selection = cmds.ls(selection=True, flatten=True)
	if not selection:
		display_message(
			"Please, select faces or vertices to clear vertex colors.", "info"
		)
		return

	for face in selection:
		try:
			cmds.polyColorPerVertex(face, remove=True)
		except Exception as e:
			continue


def select_similar_colored_faces(threshold=DEFAULT_THRESHOLD, shift_pressed=False):
	"""Selects faces on a mesh that have similar vertex colors to the currently selected face."""
	try:
		global _continuous_checkbox, _initial_face, _target_color, _stored_selected_faces

		selection = cmds.ls(selection=True, flatten=True)
		if not selection or not _target_color:
			display_message("Please, select a face.", "info")
			return

		mesh = _initial_face.split(".")[0]

		# Convert percentage to actual threshold
		threshold_distance = (threshold / 100.0) * MAX_RGB_DISTANCE

		continuous = cmds.checkBox(_continuous_checkbox, query=True, value=True)

		if continuous:
			matching_faces = continuous_selection(
				mesh, _initial_face, _target_color, threshold_distance
			)
		else:
			matching_faces = non_continuous_selection(
				mesh, _target_color, threshold_distance
			)
		
		# Handle selection based on Shift key
		if shift_pressed:
			# In multi-selection mode, recompute entirely but preserve manual additions
			_stored_selected_faces.update(selection)  # Keep manually selected faces
			new_selection = set(matching_faces).union(
				_stored_selected_faces - set(cmds.ls(f"{mesh}.f[*]", flatten=True))
			)  # Only keep stored faces that are still valid
		else:
			# In single-selection mode, reset and use only the new matches
			_stored_selected_faces.clear()
			new_selection = set(matching_faces)

		_stored_selected_faces.update(new_selection)  # Update stored selections

		# Select matching faces
		if new_selection:
			current_selection = set(cmds.ls(selection=True, flatten=True))
			if current_selection != new_selection:
				cmds.select(list(new_selection), replace=True)
		else:
			display_message("No matching faces found.", "info")

	except Exception as e:
		display_message(f"Error updating selection: {e}", "error")


def color_distance(color_a, color_b):
	return math.sqrt(sum((a - b) ** 2 for a, b in zip(color_a, color_b)))


def get_face_color(face):
	face_colors = cmds.polyColorPerVertex(face, query=True, colorRGB=True)
	if face_colors:
		return [
			sum(face_colors[0::3]) / len(face_colors[0::3]),
			sum(face_colors[1::3]) / len(face_colors[1::3]),
			sum(face_colors[2::3]) / len(face_colors[2::3]),
		]
	return None


def continuous_selection(mesh, start_face, target_color, threshold_distance):
	visited = set()
	matching_faces = set()
	face_queue = [start_face]

	while face_queue:
		current_face = face_queue.pop(0)

		if current_face in visited:
			continue

		visited.add(current_face)

		current_face_color = get_face_color(current_face)
		if current_face_color and color_distance(current_face_color, target_color) <= threshold_distance:
			matching_faces.add(current_face)

			edges = cmds.polyListComponentConversion(current_face, toEdge=True)
			edges = cmds.ls(edges, flatten=True)

			adjacent_faces = cmds.polyListComponentConversion(edges, toFace=True)
			adjacent_faces = cmds.ls(adjacent_faces, flatten=True)

			for adj_face in adjacent_faces:
				if adj_face not in visited:
					face_queue.append(adj_face)

	return list(matching_faces)


def non_continuous_selection(mesh, target_color, threshold_distance):
	matching_faces = []
	all_faces = cmds.ls(f"{mesh}.f[*]", flatten=True)

	for face in all_faces:
		face_color = get_face_color(face)
		if (
			face_color
			and color_distance(face_color, target_color) <= threshold_distance
		):
			matching_faces.append(face)

	return matching_faces


def update_current_color_display(color_rgb):
	global _current_color_display
	global _current_color_text

	if color_rgb is None:
		color_rgb = DEFAULT_INACTIVE_COLOR

	if _current_color_display:
		cmds.canvas(_current_color_display, edit=True, rgbValue=color_rgb)
  
	# Convert RGB (0-1) to RGB (0-255)
	rgb_255 = tuple(int(c * 255) for c in color_rgb)

	# Convert RGB to HSV
	hsv = colorsys.rgb_to_hsv(color_rgb[0], color_rgb[1], color_rgb[2])
	hsv_rounded = (round(hsv[0] * 360, 2), round(hsv[1] * 100, 2), round(hsv[2] * 100, 2))

	# Update UI elements
	cmds.canvas(_current_color_display, edit=True, rgbValue=color_rgb)
	cmds.text(
		_current_color_text, edit=True,
		label=f"RGB (0-1): {tuple(round(c, 2) for c in color_rgb)}\n"
			  f"RGB (0-255): {rgb_255}\n"
			  f"HSV: {hsv_rounded}"
	)


def set_fill_color_to_target(*args):
	global _fill_color, _target_color, _color_picker

	if _target_color:
		_fill_color = _target_color  # Set fill color to target color

		# Update the color picker UI to reflect the new fill color
		if _color_picker and cmds.colorSliderGrp(_color_picker, query=True, exists=True):
			cmds.colorSliderGrp(_color_picker, edit=True, rgbValue=_fill_color, useDisplaySpace=True)


def show(*args):
	"""Runs the command when clicked in the Maya menu."""
	open_gui()
	select_similar_colored_faces(_last_threshold_value)


def open_gui():
	"""Creates the GUI for selecting similar faces with a threshold slider."""
	global _threshold_slider
	global _last_threshold_value
	global _color_picker
	global _fill_frame
	global _continuous_checkbox
	global _current_color_display
	global _current_color_text

	if cmds.window("MagicWandForVertexColors", exists=True):
		cmds.deleteUI("MagicWandForVertexColors")

	window = cmds.window(
		"MagicWandForVertexColors",
		title=MENU_ENTRY_LABEL,
		widthHeight=(1, 1),
		resizeToFitChildren=True,
	)
	cmds.columnLayout(adjustableColumn=True)

	_threshold_slider = cmds.floatSliderGrp(
		label="Color Tolerance (%)",
		field=True,
		minValue=0,
		maxValue=100,
		fieldMinValue=0,
		fieldMaxValue=100,
		value=_last_threshold_value,
		dragCommand=lambda x: slider_changed_callback(),
		columnWidth=(1, 100)
	)

	cmds.separator(style="in")

	cmds.rowLayout(numberOfColumns=2, columnWidth2=(100, 100), adjustableColumn=1)
	_current_color_display = cmds.canvas(rgbValue=DEFAULT_INACTIVE_COLOR, width=100, height=75)
	cmds.columnLayout(numberOfChildren=2, columnWidth=150, adjustableColumn=1)
	_current_color_text = cmds.text(label="RGB (0-1): (1.0, 1.0, 1.0)\nRGB (0-255): (255, 255, 255)\nHSV: (0, 0, 1)", align='left')
	cmds.button(label="Set Vertex Color", width=150, height=25, command=set_fill_color_to_target)
	cmds.setParent('..')
	cmds.setParent('..')

	cmds.separator(style="in")
 
	cmds.rowLayout(numberOfColumns=2, columnWidth2=(100, 50), adjustableColumn=1)
	_color_picker = cmds.colorSliderGrp(
		rgb=_fill_color, changeCommand=fill_color_changed_callback, columnWidth2=(100, 25), useDisplaySpace=True
	)
	cmds.button(label="Apply Vertex Color", command=apply_fill_color, width=150)
	cmds.setParent("..")

	cmds.separator(style="in")
 
	_continuous_checkbox = cmds.checkBox(
		label="Contiguous Selection", value=True, align='middle', changeCommand=lambda x: selection_changed_callback()
	)

	cmds.separator(style="in")

	cmds.button(label="Clear Vertex Data", command=clear_vertex_colors)

	cmds.showWindow(window)
	cmds.scriptJob(
		event=["SelectionChanged", selection_changed_callback], parent=window
	)


def loadMenu():
	"""Setup the Maya menu, runs on plugin enable"""
	global __menu_entry_name

	# Ensure the menu parent exists
	mel.eval("evalDeferred buildFileMenu")

	if not cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
		cmds.menu(MENU_NAME, label=MENU_LABEL, parent=MENU_PARENT)

	__menu_entry_name = cmds.menuItem(
		label=MENU_ENTRY_LABEL, command=show, parent=MENU_NAME, image=IMAGE_ICON_NAME
	)


def unloadMenuItem():
	"""Remove the created Maya menu entry, runs on plugin disable"""
	if cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
		menu_long_name = f"{MENU_PARENT}|{MENU_NAME}"

		if cmds.menuItem(__menu_entry_name, exists=True):
			cmds.deleteUI(__menu_entry_name, menuItem=True)

		if not cmds.menu(menu_long_name, query=True, itemArray=True):
			cmds.deleteUI(menu_long_name, menu=True)
   
	global _target_color, _initial_face, _current_color_text, _stored_selected_faces

	_target_color = None
	_initial_face = None
	_current_color_text = None
	_stored_selected_faces.clear()


def initializePlugin(plugin):
	"""Code to run when the Maya plugin is enabled."""
	loadMenu()
	om.MGlobal.displayInfo(f"{PLUGIN_NAME} plugin loaded.")


def uninitializePlugin(plugin):
	"""Code to run when the Maya plugin is disabled."""
	unloadMenuItem()
	om.MGlobal.displayInfo(f"{PLUGIN_NAME} plugin unloaded.")
