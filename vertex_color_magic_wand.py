import maya.api.OpenMaya as om
import maya.cmds as cmds
import maya.mel as mel
import math
import colorsys

# Plugin constants
PLUGIN_NAME = "Magic Wand for Vertex Colors"
MENU_NAME = "ToolsMenu"
MENU_LABEL = "Tools"
MENU_ENTRY_LABEL = "Magic Wand for Vertex Colors"
MENU_PARENT = "MayaWindow"
IMAGE_ICON_NAME = "magic_wand_icon.png"
DEFAULT_THRESHOLD = 1
MAX_RGB_DISTANCE = math.sqrt(3)
DEFAULT_INACTIVE_COLOR = [0.0, 0.0, 0.0]


def maya_useNewAPI():
    pass


class MagicWandPlugin:
    def __init__(self):
        self.menu_entry_name = ""
        self.last_message = None
        self.threshold_slider = None
        self.last_threshold_value = DEFAULT_THRESHOLD
        self.color_picker = None
        self.fill_color = DEFAULT_INACTIVE_COLOR
        self.fill_frame = None
        self.continuous_checkbox = None
        self.target_color = None
        self.initial_face = None
        self.current_color_display = None
        self.current_color_text = None
        self.stored_selected_faces = set()

    def display_message(self, message, level="info"):
        """Displays messages only if they are different from the last one."""
        if message != self.last_message:
            self.last_message = message
            if level == "info":
                om.MGlobal.displayInfo(message)
            elif level == "warning":
                om.MGlobal.displayWarning(message)
            elif level == "error":
                om.MGlobal.displayError(message)

    def selection_changed(self, *args):
        """Callback for selection changes."""
        try:
            current_selection = cmds.ls(selection=True, flatten=True)

            if not current_selection:
                self.initial_face = None
                self.target_color = None
                self.stored_selected_faces.clear()
                self.update_current_color_display(None)
                return

            new_faces = set(current_selection) - self.stored_selected_faces
            shift_pressed = cmds.getModifiers() & 1

            if new_faces:
                selected_face = list(new_faces)[0]

                if shift_pressed:
                    self.stored_selected_faces.update(current_selection)
                self.initial_face = selected_face
                self.target_color = self.get_face_color(self.initial_face)
                self.update_current_color_display(self.target_color)

            if self.threshold_slider and cmds.floatSliderGrp(
                self.threshold_slider, exists=True
            ):
                self.last_threshold_value = cmds.floatSliderGrp(
                    self.threshold_slider, query=True, value=True
                )

            self.select_similar_colored_faces(self.last_threshold_value, shift_pressed)
        except Exception as e:
            return

    def slider_changed(self, *args):
        """Callback for slider changes."""
        if self.threshold_slider and cmds.floatSliderGrp(
            self.threshold_slider, exists=True
        ):
            self.last_threshold_value = cmds.floatSliderGrp(
                self.threshold_slider, query=True, value=True
            )
        self.select_similar_colored_faces(
            self.last_threshold_value, len(self.stored_selected_faces) > 0
        )

    def apply_fill_color(self, *args):
        """Applies the selected fill color to all selected vertices."""
        selection = cmds.ls(selection=True, flatten=True)
        if not selection:
            self.display_message("Please select vertices to apply the color.", "info")
            return
        try:
            for vertex in selection:
                cmds.polyColorPerVertex(
                    vertex, colorRGB=self.fill_color, colorDisplayOption=True
                )
            if self.initial_face:
                self.target_color = self.get_face_color(self.initial_face)
                self.update_current_color_display(self.target_color)
        except Exception as e:
            self.display_message(f"Error applying vertex colors: {e}", "error")

    def fill_color_changed(self, *args):
        """Updates fill color from UI."""
        if self.color_picker:
            self.fill_color = cmds.colorSliderGrp(
                self.color_picker, query=True, rgbValue=True
            )

    def clear_vertex_colors(self, *args):
        """Removes vertex colors from selected faces."""
        selection = cmds.ls(selection=True, flatten=True)
        if not selection:
            self.display_message(
                "Please, select faces or vertices to clear vertex colors.", "info"
            )
            return
        for face in selection:
            try:
                cmds.polyColorPerVertex(face, remove=True)
            except Exception as e:
                continue

    def select_similar_colored_faces(
        self, threshold=DEFAULT_THRESHOLD, shift_pressed=False
    ):
        """Selects faces with similar vertex colors."""
        try:
            selection = cmds.ls(selection=True, flatten=True)
            if not selection or not self.target_color:
                self.display_message("Please, select a face.", "info")
                return

            mesh = self.initial_face.split(".")[0]
            threshold_distance = (threshold / 100.0) * MAX_RGB_DISTANCE
            continuous = cmds.checkBox(self.continuous_checkbox, query=True, value=True)

            matching_faces = (
                self.continuous_selection(
                    mesh, self.initial_face, self.target_color, threshold_distance
                )
                if continuous
                else self.non_continuous_selection(
                    mesh, self.target_color, threshold_distance
                )
            )

            if shift_pressed:
                self.stored_selected_faces.update(selection)
                new_selection = set(matching_faces).union(
                    self.stored_selected_faces
                    - set(cmds.ls(f"{mesh}.f[*]", flatten=True))
                )
            else:
                self.stored_selected_faces.clear()
                new_selection = set(matching_faces)

            self.stored_selected_faces.update(new_selection)
            if new_selection:
                current_selection = set(cmds.ls(selection=True, flatten=True))
                if current_selection != new_selection:
                    cmds.select(list(new_selection), replace=True)
            else:
                self.display_message("No matching faces found.", "info")

        except Exception as e:
            self.display_message(f"Error updating selection: {e}", "error")

    @staticmethod
    def color_distance(color_a, color_b):
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(color_a, color_b)))

    def get_face_color(self, face):
        face_colors = cmds.polyColorPerVertex(face, query=True, colorRGB=True)
        if face_colors:
            return [
                sum(face_colors[0::3]) / len(face_colors[0::3]),
                sum(face_colors[1::3]) / len(face_colors[1::3]),
                sum(face_colors[2::3]) / len(face_colors[2::3]),
            ]
        return None

    def continuous_selection(self, mesh, start_face, target_color, threshold_distance):
        visited = set()
        matching_faces = set()
        face_queue = [start_face]

        while face_queue:
            current_face = face_queue.pop(0)
            if current_face in visited:
                continue
            visited.add(current_face)
            current_face_color = self.get_face_color(current_face)
            if (
                current_face_color
                and self.color_distance(current_face_color, target_color)
                <= threshold_distance
            ):
                matching_faces.add(current_face)
                edges = cmds.polyListComponentConversion(current_face, toEdge=True)
                edges = cmds.ls(edges, flatten=True)
                adjacent_faces = cmds.polyListComponentConversion(edges, toFace=True)
                adjacent_faces = cmds.ls(adjacent_faces, flatten=True)
                for adj_face in adjacent_faces:
                    if adj_face not in visited:
                        face_queue.append(adj_face)
        return list(matching_faces)

    def non_continuous_selection(self, mesh, target_color, threshold_distance):
        matching_faces = []
        all_faces = cmds.ls(f"{mesh}.f[*]", flatten=True)
        for face in all_faces:
            face_color = self.get_face_color(face)
            if (
                face_color
                and self.color_distance(face_color, target_color) <= threshold_distance
            ):
                matching_faces.append(face)
        return matching_faces

    def update_current_color_display(self, color_rgb):
        if color_rgb is None:
            color_rgb = DEFAULT_INACTIVE_COLOR

        if self.current_color_display:
            cmds.canvas(self.current_color_display, edit=True, rgbValue=color_rgb)
            rgb_255 = tuple(int(c * 255) for c in color_rgb)
            hsv = colorsys.rgb_to_hsv(color_rgb[0], color_rgb[1], color_rgb[2])
            hsv_rounded = (
                round(hsv[0] * 360, 2),
                round(hsv[1] * 100, 2),
                round(hsv[2] * 100, 2),
            )
            cmds.text(
                self.current_color_text,
                edit=True,
                label=f"RGB (0-1): {tuple(round(c, 2) for c in color_rgb)}\n"
                f"RGB (0-255): {rgb_255}\n"
                f"HSV: {hsv_rounded}",
            )

    def set_fill_color_to_target(self, *args):
        if self.target_color:
            self.fill_color = self.target_color
            if self.color_picker and cmds.colorSliderGrp(
                self.color_picker, query=True, exists=True
            ):
                cmds.colorSliderGrp(
                    self.color_picker,
                    edit=True,
                    rgbValue=self.fill_color,
                    useDisplaySpace=True,
                )

    def show(self, *args):
        self.open_gui()
        self.select_similar_colored_faces(self.last_threshold_value)

    def open_gui(self):
        if cmds.window("MagicWandForVertexColors", exists=True):
            cmds.deleteUI("MagicWandForVertexColors")

        window = cmds.window(
            "MagicWandForVertexColors",
            title=MENU_ENTRY_LABEL,
            widthHeight=(1, 1),
            resizeToFitChildren=True,
        )
        cmds.columnLayout(adjustableColumn=True)

        self.threshold_slider = cmds.floatSliderGrp(
            label="Color Tolerance (%)",
            field=True,
            minValue=0,
            maxValue=100,
            fieldMinValue=0,
            fieldMaxValue=100,
            value=self.last_threshold_value,
            dragCommand=lambda x: self.slider_changed(),
            columnWidth=(1, 100),
        )

        cmds.separator(style="in")
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(100, 100), adjustableColumn=1)
        self.current_color_display = cmds.canvas(
            rgbValue=DEFAULT_INACTIVE_COLOR, width=100, height=75
        )
        cmds.columnLayout(numberOfChildren=2, columnWidth=150, adjustableColumn=1)
        self.current_color_text = cmds.text(
            label="RGB (0-1): (1.0, 1.0, 1.0)\nRGB (0-255): (255, 255, 255)\nHSV: (0, 0, 1)",
            align="left",
        )
        cmds.button(
            label="Set Vertex Color",
            width=150,
            height=25,
            command=self.set_fill_color_to_target,
        )
        cmds.setParent("..")
        cmds.setParent("..")

        cmds.separator(style="in")
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(100, 50), adjustableColumn=1)
        self.color_picker = cmds.colorSliderGrp(
            rgb=self.fill_color,
            changeCommand=self.fill_color_changed,
            columnWidth2=(100, 25),
            useDisplaySpace=True,
        )
        cmds.button(
            label="Apply Vertex Color", command=self.apply_fill_color, width=150
        )
        cmds.setParent("..")

        cmds.separator(style="in")
        self.continuous_checkbox = cmds.checkBox(
            label="Contiguous Selection",
            value=True,
            align="middle",
            changeCommand=lambda x: self.selection_changed(),
        )

        cmds.separator(style="in")
        cmds.button(label="Clear Vertex Data", command=self.clear_vertex_colors)

        cmds.showWindow(window)
        cmds.scriptJob(
            event=["SelectionChanged", self.selection_changed], parent=window
        )

    def load_menu(self):
        mel.eval("evalDeferred buildFileMenu")
        if not cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
            cmds.menu(MENU_NAME, label=MENU_LABEL, parent=MENU_PARENT)
        self.menu_entry_name = cmds.menuItem(
            label=MENU_ENTRY_LABEL,
            command=self.show,
            parent=MENU_NAME,
            image=IMAGE_ICON_NAME,
        )

    def unload_menu(self):
        if cmds.menu(f"{MENU_PARENT}|{MENU_NAME}", exists=True):
            menu_long_name = f"{MENU_PARENT}|{MENU_NAME}"
            if cmds.menuItem(self.menu_entry_name, exists=True):
                cmds.deleteUI(self.menu_entry_name, menuItem=True)
            if not cmds.menu(menu_long_name, query=True, itemArray=True):
                cmds.deleteUI(menu_long_name, menu=True)
        self.target_color = None
        self.initial_face = None
        self.current_color_text = None
        self.stored_selected_faces.clear()


# Global instance
plugin_instance = MagicWandPlugin()


def initializePlugin(plugin):
    plugin_instance.load_menu()
    om.MGlobal.displayInfo(f"{PLUGIN_NAME} plugin loaded.")


def uninitializePlugin(plugin):
    plugin_instance.unload_menu()
    om.MGlobal.displayInfo(f"{PLUGIN_NAME} plugin unloaded.")
