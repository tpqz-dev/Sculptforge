# SPDX-FileCopyrightText: 2026 
# SPDX-License-Identifier: CC0-1.0
#
# Written in 2026. To the extent possible under law, the author(s) have dedicated 
# all copyright and related and neighboring rights to this software to the public 
# domain worldwide. This software is distributed without any warranty.
# You should have received a copy of the CC0 Public Domain Dedication along with this software. 
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.

import sculptforge as sf
import sys

from PySide6 import QtWidgets

DIALOG = None
TIMER_ID = None

class PartsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SculptForge Parts")
        self.resize(300, 400)

        self.ticks = 0

        self.part_list = QtWidgets.QListWidget()
        refresh_btn = QtWidgets.QPushButton("Refresh")
        subdivide_btn = QtWidgets.QPushButton("Subdivide selected")

        refresh_btn.clicked.connect(self.refresh)
        subdivide_btn.clicked.connect(self.subdivide)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.part_list)
        layout.addWidget(refresh_btn)
        layout.addWidget(subdivide_btn)

        self.refresh()

    def refresh(self):
        self.part_list.clear()
        for part in sf.document().parts:
            self.part_list.addItem(part["name"])

    def subdivide(self):
        row = self.part_list.currentRow()
        if row < 0:
            return

        sf.run("part_select", index=row)
        sf.run("subdivide")

def stop_pump():
    global TIMER_ID
    if TIMER_ID is not None:
        sf.ui.cancel_timer(TIMER_ID)
        TIMER_ID = None

def fn(*args, **kwargs):
    global DIALOG, TIMER_ID

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

    stop_pump()
    if DIALOG is not None:
        DIALOG.close()
        DIALOG = None

    DIALOG = PartsDialog()
    DIALOG.finished.connect(lambda _result: stop_pump())
    DIALOG.show()

    def pump():
        app.processEvents()

    TIMER_ID = sf.ui.timer(pump, 30)

if __name__ == '__main__':
    sf.ui.action("pyside_test", 'Pyside Test', fn, help="test pyside integration")
