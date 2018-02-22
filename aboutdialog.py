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
import ConfigParser

from qgis.PyQt.QtCore import (
                              QUrl,
                              )
from qgis.PyQt.QtGui import (
                             QDesktopServices,
                             QDialog,
                             QDialogButtonBox,
                             QHBoxLayout,
                             QLabel,
                             QPixmap,
                             QTextBrowser,
                             QTextDocument,
                             QVBoxLayout,
                             )

import resources_rc  # NOQA


class AboutDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self)
        self.initGui()

        self.btnHelp = self.buttonBox.button(QDialogButtonBox.Help)

        self.lblLogo.setPixmap(QPixmap(":/icons/qconsolidate.png"))

        cfg = ConfigParser.SafeConfigParser()
        cfg.read(os.path.join(os.path.dirname(__file__), "metadata.txt"))
        version = cfg.get("general", "version")

        self.lblVersion.setText(self.tr("Version: %s") % (version))
        doc = QTextDocument()
        doc.setHtml(self.getAboutText())
        self.textBrowser.setDocument(doc)
        self.textBrowser.setOpenExternalLinks(True)

        self.buttonBox.helpRequested.connect(self.openHelp)

        self.btnClose = self.buttonBox.button(QDialogButtonBox.Close)
        self.btnClose.clicked.connect(self.reject)

    def initGui(self):
        self.setWindowTitle('OQ-Consolidate')
        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.Close | QDialogButtonBox.Help)
        self.label = QLabel("OQ-Consolidate")
        self.label.setStyleSheet("font-weight: bold")
        self.lblLogo = QLabel()
        self.lblVersion = QLabel()
        self.textBrowser = QTextBrowser()
        self.h_layout = QHBoxLayout()
        self.h_layout.addWidget(self.lblLogo)
        self.h_layout.addWidget(self.label)
        self.v_layout = QVBoxLayout()
        self.v_layout.addLayout(self.h_layout)
        self.v_layout.addWidget(self.lblVersion)
        self.v_layout.addWidget(self.textBrowser)
        self.v_layout.addWidget(self.buttonBox)
        self.setLayout(self.v_layout)

    def openHelp(self):
        QDesktopServices.openUrl(QUrl(
            "https://github.com/gem/oq-consolidate"))

    def getAboutText(self):
        return self.tr(
            """
            <p>Consolidates all layers from current QGIS project into
            one directory (optionally zipping the whole project in a
            single file).</p>
            <p><strong>Developed by</strong>: GEM Foundation</p>
            <p>Fork of the q-consolidate plugin by Alexander Bruy</p>
            <p><strong>Homepage</strong>:
            <a href="https://github.com/gem/oq-consolidate/">
            homepage</a></p>
            <p>Please report bugs at
            <a href="https://github.com/gem/oq-consolidate/issues">
            bugtracker</a>.</p>
            """)
