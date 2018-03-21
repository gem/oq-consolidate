# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2017-2018 GEM Foundation
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake. If not, see <http://www.gnu.org/licenses/>.

# This plugin was forked from https://github.com/alexbruy/qconsolidate
# by Alexander Bruy (alexander.bruy@gmail.com),
# starting from commit 6f27b0b14b925a25c75ea79aea62a0e3d51e30e3.


from builtins import str
from shutil import copyfile
from osgeo import gdal
import os
import re
import zipfile
from qgis.PyQt.QtCore import (
                              QDir,
                              QFile,
                              QIODevice,
                              QTextStream,
                              QFileInfo,
                              pyqtSignal,
                              pyqtSlot,
                              QMutex,
                              )
from qgis.PyQt.QtXml import QDomDocument
from qgis.PyQt.QtWidgets import (
                                 QCheckBox,
                                 QDialog,
                                 QDialogButtonBox,
                                 QFileDialog,
                                 QLabel,
                                 QLineEdit,
                                 QMessageBox,
                                 QPushButton,
                                 QHBoxLayout,
                                 QVBoxLayout,
                                 )
from qgis.core import (
                       QgsMapLayer,
                       QgsVectorFileWriter,
                       QgsProject,
                       QgsTask,
                       QgsApplication,
                       )
from qgis.utils import iface
from .utils import log_msg, tr


class QConsolidateDialog(QDialog):

    outfileCreated = pyqtSignal(str)

    def __init__(self):
        QDialog.__init__(self)
        self.initGui()

        self.consolidateTask = None

        self.btnOk = self.buttonBox.button(QDialogButtonBox.Ok)
        self.btnOk.setEnabled(False)
        self.btnOk.clicked.connect(self.accept)
        self.btnCancel = self.buttonBox.button(QDialogButtonBox.Cancel)
        self.btnCancel.setEnabled(True)
        self.btnCancel.clicked.connect(self.reject)

        self.project_name_le.editingFinished.connect(
            self.on_project_name_editing_finished)
        self.leOutputDir.textChanged.connect(
            self.set_ok_button)

        project_name = self.get_project_name()
        if project_name:
            self.project_name_le.setText(project_name)

        self.btnBrowse.clicked.connect(self.setOutDirectory)
        self.outfileCreated.connect(self.on_outfileCreated)
        self.mutex = QMutex()

    def initGui(self):
        self.setWindowTitle('OQ-Consolidate')
        self.project_name_lbl = QLabel('Project name')
        self.project_name_le = QLineEdit()
        self.checkBoxZip = QCheckBox('Consolidate in a Zip file')

        self.label = QLabel("Output directory")
        self.leOutputDir = QLineEdit()
        self.btnBrowse = QPushButton("Browse...")
        self.buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

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
        self.btnOk.setEnabled(False)
        self.btnCancel.setEnabled(False)
        project_name = self.project_name_le.text()
        if project_name.endswith('.qgs'):
            project_name = project_name[:-4]
        if not project_name:
            msg = tr("Please specify the project name")
            log_msg(msg, level='C', message_bar=iface.messageBar())
            self.restoreGui()
            return

        outputDir = self.leOutputDir.text()
        if not outputDir:
            msg = tr("Please specify the output directory.")
            log_msg(msg, level='C', message_bar=iface.messageBar())
            self.restoreGui()
            return
        outputDir = os.path.join(outputDir,
                                 get_valid_filename(project_name))

        # create main directory if not exists
        d = QDir(outputDir)
        if not d.exists():
            if not d.mkpath("."):
                msg = tr("Can't create directory to store the project.")
                log_msg(msg, level='C', message_bar=iface.messageBar())
                self.restoreGui()
                return
        self.layersDir = outputDir + "/layers"
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
                msg = tr("Can't create directory for layers.")
                log_msg(msg, level='C', message_bar=iface.messageBar())
                self.restoreGui()
                return

        # copy project file
        self.projectFile = QgsProject.instance().fileName()
        try:
            if self.projectFile:
                f = QFile(self.projectFile)
                newProjectFile = os.path.join(outputDir,
                                              '%s.qgs' % project_name)
                f.copy(newProjectFile)
            else:
                newProjectFile = os.path.join(
                    outputDir, '%s.qgs' % project_name)
                p = QgsProject.instance()
                p.write(newProjectFile)
        except Exception as exc:
            self.restoreGui()
            log_msg(str(exc), level='C',
                    message_bar=iface.messageBar(),
                    exception=exc)
            return

        self.consolidate()
        super().accept()

    def restoreGui(self):
        self.btnCancel.setEnabled(True)
        self.set_ok_button()

    def consolidate(self):
        log_msg("Consolidation started.", level='I', duration=4,
                message_bar=iface.messageBar())
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
        layers = QgsProject.instance().mapLayers()
        # log_msg("Layers: %s" % layers, level='I',
        #         message_bar=iface.messageBar())

        # keep full paths of exported layer files (used to zip files)
        self.outfiles = [self.projectFile]
        convertable_layers = [
            layer for layer in layers.values()
            if (layer.type() == QgsMapLayer.VectorLayer
                or (layer.type() == QgsMapLayer.RasterLayer
                and layer.providerType() == 'gdal'))]
        # msg = 'Convertable layers: %s' % convertable_layers
        # log_msg(msg, level='I', message_bar=iface.messageBar())
        self.totExpectedOutFiles = 1 + len(convertable_layers)
        for i, layer in enumerate(layers.values()):
            if not layer.isValid():
                raise TypeError("Layer %s is invalid" % layer.name())
            lType = layer.type()
            lProviderType = layer.providerType()
            lName = layer.name()
            lUri = layer.dataProvider().dataSourceUri()
            if lType == QgsMapLayer.VectorLayer:
                # Always convert to GeoPackage
                convert_layer_task = QgsTask.fromFunction(
                    'Converting layer: %s' % layer.name(),
                    self.convertGenericVectorLayer, e, layer, lName)
                QgsApplication.taskManager().addTask(convert_layer_task)
            elif lType == QgsMapLayer.RasterLayer:
                # FIXME: should we convert also this to GeoPackage?
                if lProviderType == 'gdal':
                    if self.checkGdalWms(lUri):
                        copy_raster_layer_task = QgsTask.fromFunction(
                            'Copying raster layer: %s' % layer.name(),
                            self.copyXmlRasterLayer, e, layer, lName)
                        QgsApplication.taskManager().addTask(
                            copy_raster_layer_task)
            else:
                raise TypeError('Layer %s (type %s) is not supported'
                                % (lName, lType))

        # save updated project
        self.saveProject(doc)

        return True

    @pyqtSlot(str)
    def on_outfileCreated(self, outFile):
        if not self.checkBoxZip.isChecked():
            return
        self.mutex.lock()
        self.outfiles.append(outFile)
        self.mutex.unlock()
        # msg = "%s vs %s" % (len(self.outfiles), self.totExpectedOutFiles)
        # log_msg(msg, level='I', message_bar=iface.messageBar())
        if len(self.outfiles) == self.totExpectedOutFiles:
            # strip .qgs from the project name
            zip_files_task = QgsTask.fromFunction(
                'Zipping files', self.zipfiles,
                self.outfiles, self.projectFile[:-4])
            QgsApplication.taskManager().addTask(
                zip_files_task)

    def loadProject(self):
        f = QFile(self.projectFile)
        if not f.open(QIODevice.ReadOnly | QIODevice.Text):
            msg = self.tr("Cannot read file %s:\n%s.") % (self.projectFile,
                                                          f.errorString())
            raise IOError(msg)

        doc = QDomDocument()
        setOk, errorString, errorLine, errorColumn = doc.setContent(f, True)
        if not setOk:
            msg = (self.tr("Parse error at line %d, column %d:\n%s")
                   % (errorLine, errorColumn, errorString))
            raise SyntaxError(msg)

        f.close()
        return doc

    def saveProject(self, doc):
        f = QFile(self.projectFile)
        if not f.open(QIODevice.WriteOnly | QIODevice.Text):
            msg = self.tr("Cannot write file %s:\n%s.") % (self.projectFile,
                                                           f.errorString())
            raise IOError(msg)

        out = QTextStream(f)
        doc.save(out, 4)
        f.close()

    def zipfiles(self, task, file_paths, archive):
        """
        Build a zip archive from the given file names.
        :param file_paths: list of path names
        :param archive: path of the archive
        """
        archive = "%s.zip" % archive
        prefix = len(
            os.path.commonprefix([os.path.dirname(f) for f in file_paths]))
        task.setProgress(1.0)
        with zipfile.ZipFile(
                archive, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as z:
            for i, f in enumerate(file_paths):
                task.setProgress(i)
                z.write(f, f[prefix:])

    def copyXmlRasterLayer(self, task,  layerElement, vLayer, layerName):
        outFile = "%s/%s.xml" % (self.layersDir, layerName)
        try:
            copyfile(vLayer.dataProvider().dataSourceUri(), outFile)
        except IOError:
            msg = self.tr("Cannot copy layer %s") % layerName
            raise IOError(msg)

        # update project
        layerNode = self.findLayerInProject(layerElement, layerName)
        tmpNode = layerNode.firstChildElement("datasource")
        p = "./layers/%s.xml" % layerName
        tmpNode.firstChild().setNodeValue(p)
        tmpNode = layerNode.firstChildElement("provider")
        tmpNode.firstChild().setNodeValue("gdal")
        self.outfileCreated.emit(outFile)

    def convertGenericVectorLayer(self, task, layerElement, vLayer, layerName):
        crs = vLayer.crs()
        enc = vLayer.dataProvider().encoding()
        outFile = "%s/%s.gpkg" % (self.layersDir, layerName)

        # TODO: If it's already a geopackage, we chould just copy it instead of
        #       converting it
        #       (if vLayer.dataProvider().storageType() == 'GPKG':)

        error, error_msg = QgsVectorFileWriter.writeAsVectorFormat(
            vLayer, outFile, enc, crs, 'GPKG')
        if error != QgsVectorFileWriter.NoError:
            msg = self.tr("Cannot copy layer %s: %s") % (layerName, error_msg)
            raise IOError(msg)

        # update project
        layerNode = self.findLayerInProject(layerElement, layerName)
        tmpNode = layerNode.firstChildElement("datasource")
        p = "./layers/%s.gpkg" % layerName
        tmpNode.firstChild().setNodeValue(p)
        tmpNode = layerNode.firstChildElement("provider")
        tmpNode.setAttribute("encoding", enc)
        tmpNode.firstChild().setNodeValue("ogr")
        self.outfileCreated.emit(outFile)

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
    s = str(s).strip().replace(' ', '_')  # FIXME: str
    return re.sub(r'(?u)[^-\w.]', '', s)
