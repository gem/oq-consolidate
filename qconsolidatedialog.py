# -*- coding: utf-8 -*-

# *****************************************************************************
#
# QConsolidate
# ---------------------------------------------------------
# Consolidates all layers from current QGIS project into one directory and
# creates copy of current project using this consolidated layers.
#
# Copyright (C) 2012-2013 Alexander Bruy (alexander.bruy@gmail.com)
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/licenses/>. You can also obtain it by writing
# to the Free Software Foundation, 51 Franklin Street, Suite 500 Boston,
# MA 02110-1335 USA.
#
# *****************************************************************************

import os
import re

from qgis.PyQt.QtCore import (
                              QDir,
                              QFile,
                              QFileInfo,
                              Qt,
                              )
from qgis.PyQt.QtGui import (
                             QApplication,
                             QCheckBox,
                             QCursor,
                             QDialog,
                             QDialogButtonBox,
                             QFileDialog,
                             QHBoxLayout,
                             QLabel,
                             QLineEdit,
                             QMessageBox,
                             QProgressBar,
                             QPushButton,
                             QVBoxLayout,
                             )

from qgis.core import QgsProject

from consolidatethread import ConsolidateThread


class QConsolidateDialog(QDialog):
    def __init__(self, iface):
        QDialog.__init__(self)
        self.initGui()

        self.iface = iface

        self.workThread = None

        self.btnOk = self.buttonBox.button(QDialogButtonBox.Ok)
        self.btnOk.setEnabled(False)
        self.btnOk.clicked.connect(self.accept)
        self.btnCancel = self.buttonBox.button(QDialogButtonBox.Cancel)
        self.btnCancel.clicked.connect(self.reject)
        self.btnAbort = self.buttonBox.button(QDialogButtonBox.Abort)
        self.btnAbort.setEnabled(False)
        self.btnAbort.clicked.connect(self.stopProcessing)

        self.project_name_le.editingFinished.connect(
            self.on_project_name_editing_finished)
        self.leOutputDir.textChanged.connect(
            self.set_ok_button)

        project_name = self.get_project_name()
        if project_name:
            self.project_name_le.setText(project_name)

        self.btnBrowse.clicked.connect(self.setOutDirectory)

    def initGui(self):
        self.setWindowTitle('OQ-Consolidate')
        self.project_name_lbl = QLabel('Project name')
        self.project_name_le = QLineEdit()
        self.checkBoxZip = QCheckBox('Consolidate in a Zip file')

        self.label = QLabel("Output directory")
        self.leOutputDir = QLineEdit()
        self.btnBrowse = QPushButton("Browse...")
        self.progressBar = QProgressBar()
        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel |
            QDialogButtonBox.Abort)

        self.v_layout = QVBoxLayout()
        self.setLayout(self.v_layout)

        self.proj_name_hlayout = QHBoxLayout()
        self.proj_name_hlayout.addWidget(self.project_name_lbl)
        self.proj_name_hlayout.addWidget(self.project_name_le)
        self.v_layout.addLayout(self.proj_name_hlayout)

        self.h_layout = QHBoxLayout()
        self.h_layout.addWidget(self.label)
        self.h_layout.addWidget(self.leOutputDir)
        self.h_layout.addWidget(self.btnBrowse)
        self.v_layout.addLayout(self.h_layout)

        self.v_layout.addWidget(self.checkBoxZip)
        self.v_layout.addWidget(self.progressBar)
        self.v_layout.addWidget(self.buttonBox)

    def on_project_name_editing_finished(self):
        try:
            valid_filename = get_valid_filename(self.project_name_le.text())
        except UnicodeEncodeError:
            self.project_name_le.undo()
        else:
            self.project_name_le.setText(valid_filename)
        self.set_ok_button()

    def get_project_name(self):
        prjfi = QFileInfo(QgsProject.instance().fileName())
        return prjfi.baseName()

    def set_ok_button(self):
        self.btnOk.setEnabled(bool(self.project_name_le.text()) and
                              bool(self.leOutputDir.text()))

    def setOutDirectory(self):
        outDir = QFileDialog.getExistingDirectory(
            self, self.tr("Select output directory"), ".")
        if not outDir:
            return

        self.leOutputDir.setText(outDir)

    def accept(self):
        self.btnAbort.setEnabled(True)
        project_name = self.project_name_le.text()
        if project_name.endswith('.qgs'):
            project_name = project_name[:-4]
        if not project_name:
            QMessageBox.critical(
                self, self.tr("OQ-Consolidate: Error"),
                self.tr("Please specify the project name"))
            self.restoreGui()
            return

        outputDir = self.leOutputDir.text()
        if not outputDir:
            QMessageBox.critical(
                self, self.tr("OQ-Consolidate: Error"),
                self.tr("Please specify the output directory."))
            self.restoreGui()
            return
        outputDir = os.path.join(outputDir,
                                 get_valid_filename(project_name))

        # create main directory if not exists
        d = QDir(outputDir)
        if not d.exists():
            if not d.mkpath("."):
                QMessageBox.critical(
                    self, self.tr("OQ-Consolidate: Error"),
                    self.tr("Can't create directory to store the project."))
                self.restoreGui()
                return

        # create directory for layers if not exists
        if d.exists("layers"):
            res = QMessageBox.question(
                self, self.tr("Directory exists"),
                self.tr("Output directory already contains 'layers'"
                        " subdirectory. Maybe this directory was used to"
                        " consolidate another project. Continue?"),
                QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.No:
                self.restoreGui()
                return
        else:
            if not d.mkdir("layers"):
                QMessageBox.critical(
                    self, self.tr("OQ-Consolidate: Error"),
                    self.tr("Can't create directory for layers."))
                self.restoreGui()
                return

        # copy project file
        projectFile = QgsProject.instance().fileName()
        try:
            if projectFile:
                f = QFile(projectFile)
                newProjectFile = os.path.join(outputDir,
                                              '%s.qgs' % project_name)
                f.copy(newProjectFile)
            else:
                newProjectFile = os.path.join(
                    outputDir, '%s.qgs' % project_name)
                f = QFileInfo(newProjectFile)
                p = QgsProject.instance()
                p.write(f)
        except Exception:
            self.restoreGui()
            raise
            return

        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))

        # start consolidate thread that does all real work
        self.workThread = ConsolidateThread(
            self.iface, outputDir, newProjectFile,
            self.checkBoxZip.isChecked())
        self.workThread.rangeChanged.connect(self.on_rangeChanged)
        self.workThread.updateProgress.connect(self.on_updateProgress)
        self.workThread.processFinished.connect(self.on_processFinished)
        self.workThread.processInterrupted.connect(self.on_processInterrupted)
        self.workThread.processError.connect(self.on_processError)
        self.workThread.exceptionOccurred.connect(self.on_exceptionOccurred)

        self.btnOk.setEnabled(False)

        self.workThread.start()

    def on_rangeChanged(self, maxValue):
        self.progressBar.setRange(0, maxValue)
        self.progressBar.setValue(0)

    def on_updateProgress(self):
        self.progressBar.setValue(self.progressBar.value() + 1)

    def on_processFinished(self):
        self.stopProcessing()
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self,
                                self.tr("OQ-Consolidate: Info"),
                                'Consolidation complete.'
                                )
        super(QConsolidateDialog, self).accept()

    def on_processInterrupted(self):
        self.stopProcessing()
        self.restoreGui()

    def on_processError(self, message):
        self.restoreGui()
        QMessageBox.critical(self,
                             self.tr("OQ-Consolidate: Error"),
                             message
                             )
        self.stopProcessing()

    def on_exceptionOccurred(self, message):
        self.restoreGui()
        QMessageBox.critical(self, self.tr("OQ-Consolidate: Error"), message)
        self.stopProcessing()

    def stopProcessing(self):
        if self.workThread is not None:
            self.workThread.stop()
            self.workThread = None

    def restoreGui(self):
        self.progressBar.setRange(0, 1)
        self.progressBar.setValue(0)

        QApplication.restoreOverrideCursor()
        self.btnAbort.setEnabled(False)
        self.set_ok_button()


# from https://github.com/django/django/blob/master/django/utils/text.py#L223
def get_valid_filename(s):
    """
    Return the given string converted to a string that can be used for a clean
    filename. Remove leading and trailing spaces; convert other spaces to
    underscores; and remove anything that is not an alphanumeric, dash,
    underscore, or dot.
    >>> get_valid_filename("john's portrait in 2004.jpg")
    'johns_portrait_in_2004.jpg'
    """
    s = str(s).strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)
