# -*- coding: utf-8 -*-

#******************************************************************************
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
#******************************************************************************


from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *
from qgis.gui import *

import qconsolidatedialog
import aboutdialog

import resources_rc


class QConsolidatePlugin:
    def __init__(self, iface):
        self.iface = iface

        self.qgsVersion = unicode(QGis.QGIS_VERSION_INT)

        # For i18n support
        userPluginPath = QFileInfo(QgsApplication.qgisUserDbFilePath()).path() + "/python/plugins/qconsolidate"
        systemPluginPath = QgsApplication.prefixPath() + "/python/plugins/qconsolidate"

        overrideLocale = QSettings().value("locale/overrideFlag", False, type=bool)
        if not overrideLocale:
            localeFullName = QLocale.system().name()
        else:
            localeFullName = QSettings().value("locale/userLocale", "")

        if QFileInfo(userPluginPath).exists():
            translationPath = userPluginPath + "/i18n/qconsolidate_" + localeFullName + ".qm"
        else:
            translationPath = systemPluginPath + "/i18n/qconsolidate_" + localeFullName + ".qm"

        self.localePath = translationPath
        if QFileInfo(self.localePath).exists():
            self.translator = QTranslator()
            self.translator.load(self.localePath)
            QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        if int(self.qgsVersion) < 20000:
            qgisVersion = self.qgsVersion[0] + "." + self.qgsVersion[2] + "." + self.qgsVersion[3]
            QMessageBox.warning(self.iface.mainWindow(), "OQ-Consolidate",
                                QCoreApplication.translate("OQ-Consolidate", "QGIS %s detected.\n") % (qgisVersion) +
                                QCoreApplication.translate("OQ-Consolidate", "This version of OQ-Consolidate requires at least QGIS version 2.0.\nPlugin will not be enabled."))
            return None

        self.actionRun = QAction(QIcon(":/icons/qconsolidate.png"), "OQ-Consolidate", self.iface.mainWindow())
        self.actionRun.setStatusTip(QCoreApplication.translate("OQ-Consolidate", "Consolidates all layers from current QGIS project into one directory"))
        self.actionAbout = QAction(QIcon(":/icons/about.png"), "About OQ-Consolidate", self.iface.mainWindow())

        self.actionRun.triggered.connect(self.run)
        self.actionAbout.triggered.connect(self.about)

        self.iface.addPluginToMenu(QCoreApplication.translate("OQ-Consolidate", "OQ-Consolidate"), self.actionRun)
        self.iface.addPluginToMenu(QCoreApplication.translate("OQ-Consolidate", "OQ-Consolidate"), self.actionAbout)
        self.iface.addToolBarIcon(self.actionRun)

    def unload(self):
        self.iface.removePluginMenu(QCoreApplication.translate("OQ-Consolidate", "OQ-Consolidate"), self.actionRun)
        self.iface.removePluginMenu(QCoreApplication.translate("OQ-Consolidate", "OQ-Consolidate"), self.actionAbout)
        self.iface.removeToolBarIcon(self.actionRun)

    def run(self):
        dlg = qconsolidatedialog.QConsolidateDialog(self.iface)
        dlg.exec_()

    def about(self):
        dlg = aboutdialog.AboutDialog()
        dlg.exec_()
