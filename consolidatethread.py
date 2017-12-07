# -*- coding: utf-8 -*-

# *****************************************************************************
#
# oq-consolidate
# ---------------------------------------------------------
# Consolidates some layers from current QGIS project into one directory and
# creates copy of current project using gpkg and xml consolidated layers.
#
# Copyright (C) 2017 GEM Foundation (devops@openquake.org)
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

import sys
import traceback
import os
import zipfile

from qgis.PyQt.QtCore import (QThread,
                              pyqtSignal,
                              QMutex,
                              QIODevice,
                              QTextStream,
                              QFile,
                              )
from qgis.PyQt.QtXml import QDomDocument

from qgis.core import QgsMapLayer, QgsVectorFileWriter

from osgeo import gdal
from shutil import copyfile


class ConsolidateThread(QThread):
    processError = pyqtSignal(str)
    rangeChanged = pyqtSignal(int)
    updateProgress = pyqtSignal()
    processFinished = pyqtSignal()
    processInterrupted = pyqtSignal()
    exceptionOccurred = pyqtSignal(str)

    def __init__(self, iface, outputDir, projectFile, saveToZip):
        QThread.__init__(self, QThread.currentThread())
        self.mutex = QMutex()
        self.stopMe = 0

        self.iface = iface
        self.outputDir = outputDir
        self.layersDir = outputDir + "/layers"
        self.projectFile = projectFile
        self.saveToZip = saveToZip

    def run(self):
        try:
            self.consolidate()
        except Exception:
            ex_type, ex, tb = sys.exc_info()
            tb_str = ''.join(traceback.format_tb(tb))
            msg = "%s:\n\n%s" % (ex_type.__name__, tb_str)
            self.exceptionOccurred.emit(msg)

    def consolidate(self):
        self.mutex.lock()
        self.stopMe = 0
        self.mutex.unlock()

        interrupted = False

        gdal.AllRegister()

        # read project
        doc = self.loadProject()
        root = doc.documentElement()

        # ensure that relative path used
        e = root.firstChildElement("properties")
        (e.firstChildElement("Paths").firstChild()
            .firstChild().setNodeValue("false"))

        # get layers section in project
        e = root.firstChildElement("projectlayers")

        # process layers
        layers = self.iface.legendInterface().layers()
        self.rangeChanged.emit(len(layers))

        # keep full paths of exported layer files (used to zip files)
        outFiles = [self.projectFile]

        for layer in layers:
            if not layer.isValid():
                self.processError.emit(
                    "Layer %s is invalid" % layer.name())
                return
            else:
                lType = layer.type()
                lProviderType = layer.providerType()
                lName = layer.name()
                lUri = layer.dataProvider().dataSourceUri()
                if lType == QgsMapLayer.VectorLayer:
                    # Always convert to GeoPackage
                    outFile = self.convertGenericVectorLayer(
                        e, layer, lName)
                    outFiles.append(outFile)
                elif lType == QgsMapLayer.RasterLayer:
                    if lProviderType == 'gdal':
                        if self.checkGdalWms(lUri):
                            outFile = self.copyXmlRasterLayer(
                                e, layer, lName)
                            outFiles.append(outFile)
                else:
                    self.processError.emit(
                        'Layer %s (type %s) is not supported'
                        % (lName, lType))
                    return

            self.updateProgress.emit()
            self.mutex.lock()
            s = self.stopMe
            self.mutex.unlock()
            if s == 1:
                interrupted = True
                break

        # save updated project
        self.saveProject(doc)

        if self.saveToZip:
            self.rangeChanged.emit(len(outFiles))
            # strip .qgs from the project name
            self.zipfiles(outFiles, self.projectFile[:-4])

        if not interrupted:
            self.processFinished.emit()
        else:
            self.processInterrupted.emit()

    def stop(self):
        self.mutex.lock()
        self.stopMe = 1
        self.mutex.unlock()

        QThread.wait(self)

    def loadProject(self):
        f = QFile(self.projectFile)
        if not f.open(QIODevice.ReadOnly | QIODevice.Text):
            msg = self.tr("Cannot read file %s:\n%s.") % (self.projectFile,
                                                          f.errorString())
            self.processError.emit(msg)
            return

        doc = QDomDocument()
        setOk, errorString, errorLine, errorColumn = doc.setContent(f, True)
        if not setOk:
            msg = (self.tr("Parse error at line %d, column %d:\n%s")
                   % (errorLine, errorColumn, errorString))
            self.processError.emit(msg)
            return

        f.close()
        return doc

    def saveProject(self, doc):
        f = QFile(self.projectFile)
        if not f.open(QIODevice.WriteOnly | QIODevice.Text):
            msg = self.tr("Cannot write file %s:\n%s.") % (self.projectFile,
                                                           f.errorString())
            self.processError.emit(msg)
            return

        out = QTextStream(f)
        doc.save(out, 4)
        f.close()

    def zipfiles(self, file_paths, archive):
        """
        Build a zip archive from the given file names.
        :param file_paths: list of path names
        :param archive: path of the archive
        """
        archive = "%s.zip" % archive
        prefix = len(
            os.path.commonprefix([os.path.dirname(f) for f in file_paths]))
        with zipfile.ZipFile(
                archive, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for f in file_paths:
                z.write(f, f[prefix:])
                self.updateProgress.emit()

    def copyXmlRasterLayer(self, layerElement, vLayer, layerName):
        outFile = "%s/%s.xml" % (self.layersDir, layerName)
        try:
            copyfile(vLayer.dataProvider().dataSourceUri(), outFile)
        except IOError:
            msg = self.tr("Cannot copy layer %s") % layerName
            self.processError.emit(msg)
            return

        # update project
        layerNode = self.findLayerInProject(layerElement, layerName)
        tmpNode = layerNode.firstChildElement("datasource")
        p = "./layers/%s.xml" % layerName
        tmpNode.firstChild().setNodeValue(p)
        tmpNode = layerNode.firstChildElement("provider")
        tmpNode.firstChild().setNodeValue("gdal")
        return outFile

    def convertGenericVectorLayer(self, layerElement, vLayer, layerName):
        crs = vLayer.crs()
        enc = vLayer.dataProvider().encoding()
        outFile = "%s/%s.gpkg" % (self.layersDir, layerName)
        error = QgsVectorFileWriter.writeAsVectorFormat(vLayer, outFile, enc,
                                                        crs, 'GPKG')
        if error != QgsVectorFileWriter.NoError:
            msg = self.tr("Cannot copy layer %s") % layerName
            self.processError.emit(msg)
            return

        # update project
        layerNode = self.findLayerInProject(layerElement, layerName)
        tmpNode = layerNode.firstChildElement("datasource")
        p = "./layers/%s.gpkg" % layerName
        tmpNode.firstChild().setNodeValue(p)
        tmpNode = layerNode.firstChildElement("provider")
        tmpNode.setAttribute("encoding", enc)
        tmpNode.firstChild().setNodeValue("ogr")
        return outFile

    def findLayerInProject(self, layerElement, layerName):
        child = layerElement.firstChildElement()
        while not child.isNull():
            nm = child.firstChildElement("layername")
            if nm.text() == layerName:
                return child
            child = child.nextSiblingElement()
        return None

    def checkGdalWms(self, layer):
        ds = gdal.Open(layer, gdal.GA_ReadOnly)
        isGdalWms = True if ds.GetDriver().ShortName == "WMS" else False
        del ds

        return isGdalWms
