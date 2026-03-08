"""
Controller State GUI Window

A tkinter window that visualizes the real-time state of the Taito
TCPP-20011 Shinkansen controller: lever positions, buttons, d-pad,
horn pedal, and raw bytes.

Can be launched standalone or embedded into interactive.py / bridge.py
via the --gui flag.
"""

import tkinter as tk
import threading
from typing import Optional

from controller import (
    ControllerInput, BrakeNotch, PowerNotch, DPad,
)

# ─── Layout Constants ────────────────────────────────────────────────────────

WINDOW_W = 680
WINDOW_H = 480
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
GREEN = "#a6e3a1"
RED = "#f38ba8"
YELLOW = "#f9e2af"
DIM = "#45475a"
SURFACE = "#313244"
FONT = ("Consolas", 11)
FONT_BIG = ("Consolas", 14, "bold")
FONT_SMALL = ("Consolas", 9)
FONT_TINY = ("Consolas", 8)
FONT_TITLE = ("Consolas", 13, "bold")

# Ordered notch lists for lever visualisation
BRAKE_NOTCHES = [
    BrakeNotch.RELEASED, BrakeNotch.B1, BrakeNotch.B2, BrakeNotch.B3,
    BrakeNotch.B4, BrakeNotch.B5, BrakeNotch.B6, BrakeNotch.B7,
    BrakeNotch.EMERGENCY,
]
BRAKE_LABELS = ["R", "1", "2", "3", "4", "5", "6", "7", "EB"]

POWER_NOTCHES = [
    PowerNotch.N, PowerNotch.P1, PowerNotch.P2, PowerNotch.P3,
    PowerNotch.P4, PowerNotch.P5, PowerNotch.P6, PowerNotch.P7,
    PowerNotch.P8, PowerNotch.P9, PowerNotch.P10, PowerNotch.P11,
    PowerNotch.P12, PowerNotch.P13,
]
POWER_LABELS = ["N", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]


# ─── GUI Class ───────────────────────────────────────────────────────────────

class ControllerGUI:
    """
    Tkinter window displaying live controller state.

    Thread-safe: call update_state() from any thread.
    The GUI runs its own mainloop on the thread that calls run(),
    or can be started in a daemon thread via start().
    """

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._state: Optional[ControllerInput] = None
        self._closing = False

        # Widget refs (set during _build)
        self._brake_cells = []
        self._power_cells = []
        self._brake_label = None
        self._power_label = None
        self._dpad_arrows = {}
        self._btn_widgets = {}
        self._pedal_widget = None
        self._raw_label = None

    # ─── Lifecycle ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the GUI in a background daemon thread."""
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def run(self) -> None:
        """Build and run the GUI (blocks until window is closed)."""
        self._root = tk.Tk()
        self._root.title("Shinkansen Controller Bridge")
        self._root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self._root.configure(bg=BG)
        self._root.resizable(False, False)
        self._build()
        self._ready.set()
        self._root.mainloop()

    def close(self) -> None:
        """Close the window from any thread."""
        self._closing = True
        if self._root is not None:
            try:
                self._root.after(0, self._safe_destroy)
            except Exception:
                pass

    def _safe_destroy(self):
        """Destroy from the tk thread to avoid Tcl_AsyncDelete errors."""
        try:
            self._root.quit()
            self._root.destroy()
        except Exception:
            pass

    def is_alive(self) -> bool:
        if self._thread is not None:
            return self._thread.is_alive()
        return False

    # ─── State Update ────────────────────────────────────────────────────

    def update_state(self, state: ControllerInput) -> None:
        """Thread-safe: schedule a UI refresh with new state."""
        self._state = state
        if self._root is not None:
            try:
                self._root.after_idle(self._refresh)
            except Exception:
                pass

    # ─── Build UI ────────────────────────────────────────────────────────

    def _build(self):
        root = self._root

        # Title
        tk.Label(root, text="TAITO TCPP-20011 SHINKANSEN", font=FONT_TITLE,
                 bg=BG, fg=ACCENT).pack(pady=(10, 2))

        # ── Main frame ──
        main = tk.Frame(root, bg=BG)
        main.pack(fill="both", expand=True, padx=15, pady=5)

        # Row 0: Levers
        lever_frame = tk.Frame(main, bg=BG)
        lever_frame.pack(fill="x", pady=(0, 8))

        self._build_lever(lever_frame, "BRAKE", BRAKE_LABELS, self._brake_cells, side="left",
                          label_var_setter=self._set_brake_label)
        self._build_lever(lever_frame, "POWER", POWER_LABELS, self._power_cells, side="right",
                          label_var_setter=self._set_power_label)

        # Row 1: Buttons + D-pad + Pedal
        mid_frame = tk.Frame(main, bg=BG)
        mid_frame.pack(fill="x", pady=(0, 8))

        self._build_dpad(mid_frame)
        self._build_buttons(mid_frame)
        self._build_pedal(mid_frame)

        # Row 2: Raw bytes
        raw_frame = tk.Frame(main, bg=SURFACE, highlightbackground=DIM,
                             highlightthickness=1)
        raw_frame.pack(fill="x", pady=(4, 0))
        tk.Label(raw_frame, text="RAW", font=FONT_SMALL, bg=SURFACE, fg=DIM,
                 width=4).pack(side="left", padx=(6, 0))
        self._raw_label = tk.Label(raw_frame, text="-- -- -- -- -- --",
                                   font=FONT, bg=SURFACE, fg=FG)
        self._raw_label.pack(side="left", padx=6, pady=4)

    def _set_brake_label(self, widget):
        self._brake_label = widget

    def _set_power_label(self, widget):
        self._power_label = widget

    def _build_lever(self, parent, title, labels, cell_list, side, label_var_setter):
        """Build a horizontal notch bar for a lever."""
        frame = tk.LabelFrame(parent, text=f"  {title}  ", font=FONT,
                              bg=BG, fg=FG, labelanchor="n",
                              highlightbackground=DIM, highlightthickness=1)
        frame.pack(side=side, fill="x", expand=True, padx=(0 if side == "left" else 6, 6 if side == "left" else 0))

        # Current position label
        pos_label = tk.Label(frame, text="---", font=FONT_BIG, bg=BG, fg=ACCENT, width=12)
        pos_label.pack(pady=(2, 4))
        label_var_setter(pos_label)

        # Use narrower cells when there are many notches (power lever has 14)
        many = len(labels) > 10
        cell_font = FONT_TINY if many else FONT_SMALL
        cell_w = 2 if many else 3

        # Notch cells row
        row = tk.Frame(frame, bg=BG)
        row.pack(pady=(0, 6))
        for lbl in labels:
            cell = tk.Label(row, text=lbl, font=cell_font, width=cell_w,
                            bg=DIM, fg=FG, relief="flat", padx=1, pady=2)
            cell.pack(side="left", padx=1)
            cell_list.append(cell)

    def _build_dpad(self, parent):
        """Build a 3x3 grid D-Pad indicator."""
        frame = tk.LabelFrame(parent, text="  D-PAD  ", font=FONT,
                              bg=BG, fg=FG, labelanchor="n",
                              highlightbackground=DIM, highlightthickness=1)
        frame.pack(side="left", padx=(0, 10))

        grid = tk.Frame(frame, bg=BG)
        grid.pack(padx=8, pady=(2, 8))

        # Positions in the 3x3 grid: (row, col) -> direction key
        layout = {
            (0, 0): "NW", (0, 1): "N",  (0, 2): "NE",
            (1, 0): "W",  (1, 1): None, (1, 2): "E",
            (2, 0): "SW", (2, 1): "S",  (2, 2): "SE",
        }
        arrow_chars = {
            "N": "\u25B2", "S": "\u25BC", "E": "\u25B6", "W": "\u25C0",
            "NE": "\u25E5", "NW": "\u25E4", "SE": "\u25E2", "SW": "\u25E3",
        }

        for (r, c), direction in layout.items():
            if direction is None:
                # Center dot
                lbl = tk.Label(grid, text="\u25CF", font=FONT_SMALL, width=3,
                               bg=BG, fg=DIM)
                lbl.grid(row=r, column=c, padx=1, pady=1)
                self._dpad_arrows["CENTER"] = lbl
            else:
                char = arrow_chars.get(direction, "?")
                lbl = tk.Label(grid, text=char, font=FONT_SMALL, width=3,
                               bg=DIM, fg=FG, relief="flat")
                lbl.grid(row=r, column=c, padx=1, pady=1)
                self._dpad_arrows[direction] = lbl

    def _build_buttons(self, parent):
        """Build face buttons + Select/Start indicators."""
        frame = tk.LabelFrame(parent, text="  BUTTONS  ", font=FONT,
                              bg=BG, fg=FG, labelanchor="n",
                              highlightbackground=DIM, highlightthickness=1)
        frame.pack(side="left", fill="both", expand=True, padx=(0, 10))

        inner = tk.Frame(frame, bg=BG)
        inner.pack(pady=(4, 8))

        # Face buttons in a diamond: top=A, left=D, right=B, bottom=C
        diamond = tk.Frame(inner, bg=BG)
        diamond.pack()

        # Row 0: A (top)
        r0 = tk.Frame(diamond, bg=BG)
        r0.pack()
        self._btn_widgets["A"] = self._make_btn(r0, "A")

        # Row 1: D (left), B (right)
        r1 = tk.Frame(diamond, bg=BG)
        r1.pack()
        self._btn_widgets["D"] = self._make_btn(r1, "D")
        tk.Label(r1, text="  ", bg=BG).pack(side="left")
        self._btn_widgets["B"] = self._make_btn(r1, "B")

        # Row 2: C (bottom)
        r2 = tk.Frame(diamond, bg=BG)
        r2.pack()
        self._btn_widgets["C"] = self._make_btn(r2, "C")

        # Select / Start below
        sys_row = tk.Frame(inner, bg=BG)
        sys_row.pack(pady=(6, 0))
        self._btn_widgets["SELECT"] = self._make_btn(sys_row, "Se", width=4)
        tk.Label(sys_row, text=" ", bg=BG).pack(side="left")
        self._btn_widgets["START"] = self._make_btn(sys_row, "St", width=4)

    def _make_btn(self, parent, text, width=3) -> tk.Label:
        lbl = tk.Label(parent, text=text, font=FONT_SMALL, width=width,
                       bg=DIM, fg=FG, relief="flat", padx=2, pady=2)
        lbl.pack(side="left", padx=1)
        return lbl

    def _build_pedal(self, parent):
        """Build horn pedal indicator."""
        frame = tk.LabelFrame(parent, text="  HORN  ", font=FONT,
                              bg=BG, fg=FG, labelanchor="n",
                              highlightbackground=DIM, highlightthickness=1)
        frame.pack(side="left", padx=(0, 0))

        self._pedal_widget = tk.Label(frame, text="\u25A0\n\u25A0\n\u25A0", font=FONT_BIG,
                                      bg=DIM, fg=FG, width=4, height=3, relief="flat")
        self._pedal_widget.pack(padx=8, pady=(4, 8))

    # ─── Refresh ─────────────────────────────────────────────────────────

    def _refresh(self):
        """Update all widgets from the current state. Called on the tk thread."""
        state = self._state
        if state is None:
            return

        # Brake lever
        brake_idx = -1
        try:
            brake_idx = BRAKE_NOTCHES.index(state.brake)
        except ValueError:
            pass
        for i, cell in enumerate(self._brake_cells):
            if i == brake_idx:
                cell.configure(bg=RED if state.brake == BrakeNotch.EMERGENCY else YELLOW, fg=BG)
            else:
                cell.configure(bg=DIM, fg=FG)
        if self._brake_label:
            name = state.brake_name
            self._brake_label.configure(text=name,
                                        fg=RED if state.brake == BrakeNotch.EMERGENCY else ACCENT)

        # Power lever
        power_idx = -1
        try:
            power_idx = POWER_NOTCHES.index(state.power)
        except ValueError:
            pass
        for i, cell in enumerate(self._power_cells):
            if i <= power_idx and power_idx >= 0:
                cell.configure(bg=GREEN, fg=BG)
            else:
                cell.configure(bg=DIM, fg=FG)
        if self._power_label:
            self._power_label.configure(text=state.power_name, fg=GREEN if power_idx > 0 else ACCENT)

        # D-pad
        active_dir = state.dpad_name
        for direction, lbl in self._dpad_arrows.items():
            if direction == active_dir:
                lbl.configure(bg=ACCENT, fg=BG)
            elif direction == "CENTER" and active_dir == "CENTER":
                lbl.configure(fg=ACCENT)
            else:
                lbl.configure(bg=DIM if direction != "CENTER" else BG,
                              fg=FG if direction != "CENTER" else DIM)

        # Buttons
        btn_map = {
            "A": state.button_a,
            "B": state.button_b,
            "C": state.button_c,
            "D": state.button_d,
            "SELECT": state.button_select,
            "START": state.button_start,
        }
        for key, pressed in btn_map.items():
            widget = self._btn_widgets.get(key)
            if widget:
                if pressed:
                    widget.configure(bg=ACCENT, fg=BG)
                else:
                    widget.configure(bg=DIM, fg=FG)

        # Pedal
        if self._pedal_widget:
            if state.pedal_pressed:
                self._pedal_widget.configure(bg=YELLOW, fg=BG)
            else:
                self._pedal_widget.configure(bg=DIM, fg=FG)

        # Raw bytes
        if self._raw_label:
            hex_str = " ".join(f"{b:02X}" for b in state.raw_bytes)
            self._raw_label.configure(text=hex_str)


# ─── Standalone Test ─────────────────────────────────────────────────────────

def main():
    """Run the GUI standalone, reading directly from the controller."""
    from controller import ShinkansenController

    gui = ControllerGUI()
    gui.start()

    try:
        with ShinkansenController() as ctrl:
            print("GUI open. Reading controller... (close window or Ctrl+C to stop)")
            while gui.is_alive():
                state = ctrl.read_input(timeout_ms=50)
                if state is not None:
                    gui.update_state(state)
    except RuntimeError as e:
        print(f"ERROR: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        gui.close()
        print("Done.")


if __name__ == "__main__":
    main()
