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

from qgis.PyQt.QtCore import (QFileInfo,
                              QDir,
                              QFile,
                              )
from qgis.PyQt.QtGui import (QDialog,
                             QDialogButtonBox,
                             QFileDialog,
                             QMessageBox,
                             QApplication,
                             # FIXME: needed if you can't compile the UI
                             # QLabel,
                             # QLineEdit,
                             # QCheckBox,
                             )

from qgis.core import QgsProject

import consolidatethread
from ui.ui_qconsolidatedialogbase import Ui_QConsolidateDialog


class QConsolidateDialog(QDialog, Ui_QConsolidateDialog):
    def __init__(self, iface):
        QDialog.__init__(self)
        self.setupUi(self)
        self.iface = iface

        self.workThread = None

        self.btnOk = self.buttonBox.button(QDialogButtonBox.Ok)
        self.btnOk.setEnabled(False)
        self.btnClose = self.buttonBox.button(QDialogButtonBox.Close)

        # FIXME: this is needed if you can't compile the UI
        # self.project_name_lbl = QLabel('Project name')
        # self.project_name_le = QLineEdit()
        # self.checkBoxZip = QCheckBox('Consolidate in a Zip file')
        # self.layout().addWidget(self.project_name_lbl)
        # self.layout().addWidget(self.project_name_le)
        # self.layout().addWidget(self.checkBoxZip)

        self.project_name_le.textChanged.connect(
            self.on_project_name_changed)
        self.leOutputDir.textChanged.connect(
            self.set_ok_button)

        project_name = self.get_project_name()
        if project_name:
            self.project_name_le.setText(project_name)

        self.btnBrowse.clicked.connect(self.setOutDirectory)

    def on_project_name_changed(self):
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
        project_name = self.project_name_le.text()
        if project_name.endswith('.qgs'):
            project_name = project_name[:-4]
        if not project_name:
            QMessageBox.critical(
                self, self.tr("OQ-Consolidate: Error"),
                self.tr("Please specify the project name"))
            return

        outputDir = self.leOutputDir.text()
        if not outputDir:
            QMessageBox.critical(
                self, self.tr("OQ-Consolidate: Error"),
                self.tr("Please specify the output directory."))
            return
        outputDir = os.path.join(outputDir, project_name)

        # create main directory if not exists
        d = QDir(outputDir)
        if not d.exists():
            d.mkpath(".")

        # create directory for layers if not exists
        if d.exists("layers"):
            res = QMessageBox.question(
                self, self.tr("Directory exists"),
                self.tr("Output directory already contains 'layers'"
                        " subdirectory. Maybe this directory was used to"
                        " consolidate another project. Continue?"),
                QMessageBox.Yes | QMessageBox.No)
            if res == QMessageBox.No:
                return
        else:
            if not d.mkdir("layers"):
                QMessageBox.critical(
                    self, self.tr("OQ-Consolidate: Error"),
                    self.tr("Can't create directory for layers."))
                return

        # copy project file
        projectFile = QgsProject.instance().fileName()
        if projectFile:
            f = QFile(projectFile)
            newProjectFile = os.path.join(outputDir,
                                          '%s.qgs' % project_name)
            f.copy(newProjectFile)
        else:
            newProjectFile = os.path.join(outputDir, '%s.qgs' % project_name)
            f = QFileInfo(newProjectFile)
            p = QgsProject.instance()
            p.write(f)

        # start consolidate thread that does all real work
        self.workThread = consolidatethread.ConsolidateThread(
            self.iface, outputDir, newProjectFile,
            self.checkBoxZip.isChecked())
        self.workThread.rangeChanged.connect(self.setProgressRange)
        self.workThread.updateProgress.connect(self.updateProgress)
        self.workThread.processFinished.connect(self.processFinished)
        self.workThread.processInterrupted.connect(self.processInterrupted)
        self.workThread.processError.connect(self.processError)
        self.workThread.exceptionOccurred.connect(self.exceptionOccurred)

        self.btnClose.setText(self.tr("Cancel"))
        self.btnOk.setEnabled(False)
        self.buttonBox.rejected.disconnect(self.reject)
        self.btnClose.clicked.connect(self.stopProcessing)

        self.workThread.start()

    def reject(self):
        QDialog.reject(self)

    def setProgressRange(self, maxValue):
        self.progressBar.setRange(0, maxValue)
        self.progressBar.setValue(0)

    def updateProgress(self):
        self.progressBar.setValue(self.progressBar.value() + 1)

    def processFinished(self):
        self.stopProcessing()
        QMessageBox.information(self,
                                self.tr("OQ-Consolidate: Info"),
                                'Consolidation complete.'
                                )
        self.restoreGui()

    def processInterrupted(self):
        self.restoreGui()

    def processError(self, message):
        QMessageBox.critical(self,
                             self.tr("OQ-Consolidate: Error"),
                             message
                             )
        self.stopProcessing()
        self.restoreGui()
        return

    def exceptionOccurred(self, message):
        QMessageBox.critical(self, self.tr("OQ-Consolidate: Error"), message)
        self.stopProcessing()
        self.restoreGui()
        return

    def stopProcessing(self):
        if self.workThread is not None:
            self.workThread.stop()
            self.workThread = None

    def restoreGui(self):
        self.progressBar.setRange(0, 1)
        self.progressBar.setValue(0)

        QApplication.restoreOverrideCursor()
        self.buttonBox.rejected.connect(self.reject)
        self.btnClose.setText(self.tr("Close"))
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
