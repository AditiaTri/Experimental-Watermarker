import os, sys, io
import random
import datetime
import logging

from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
from PIL import ImageOps
from PIL import ImageEnhance
from PIL.ImageQt import ImageQt

from PySide6 import QtCore, QtWidgets, QtGui, QtSql, QtQml

import math

class WaveDeformer:
    def __init__(self):
        self.intensity = 5
    def transform(self, x, y):
        x, y = self.transform_intensity(x, y)
        return x, y

    def transform_intensity(self, x, y):
        y = y + self.intensity*math.sin(x/40)
        return x, y

    def transform_rectangle(self, x0, y0, x1, y1):
        return (*self.transform(x0, y0),
                *self.transform(x0, y1),
                *self.transform(x1, y1),
                *self.transform(x1, y0),
                )

    def getmesh(self, img):
        self.w, self.h = img.size
        gridspace = 20

        target_grid = []
        for x in range(0, self.w, gridspace):
            for y in range(0, self.h, gridspace):
                target_grid.append((x, y, x + gridspace, y + gridspace))

        source_grid = [self.transform_rectangle(*rect) for rect in target_grid]

        return [t for t in zip(target_grid, source_grid)]

class Logger():
    def __init__(self):
        self.log = io.StringIO()
        self.output = []
    def write(self, str):
        self.log.write(str+"\n")
        for i in self.output:
            i.setText(self.log.getvalue())
    def add_output(self, wx):
        self.output.append(wx)
        self.write("New log output added")


class MyWidget(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('Watermark Tool v1.0 by Aditia Trihadian')
        self.setAcceptDrops(True)

        self.logger = Logger()
        self.logger.write("Initializing application") 

        self.im_before=None
        self.im_after=None
        self.im_filename=None
        self.con=None
        self.im_watermarkColor=QtGui.QColor.fromRgb(255,255,84)
        self.im_index = None
        self.save_location = None

        if not self.app_init_sql():
            sys.exit(1)

        menu = self.menuBar()
        menu_file = menu.addMenu("&File")
        
        wx_button_info = QtGui.QAction(QtGui.QIcon("help.png"), "&About", self)
        wx_button_info.setStatusTip("Show information about the application")
        wx_button_info.triggered.connect(self.app_info)
        menu_file.addAction(wx_button_info)

        menu_file.addSeparator()

        wx_button_exit = QtGui.QAction(QtGui.QIcon("close.png"), "&Exit", self)
        wx_button_exit.setStatusTip("Exit the application")
        wx_button_exit.triggered.connect(self.app_exit)
        menu_file.addAction(wx_button_exit)
        
        ### MAIN WINDOW CONTENT
        self.ly = QtWidgets.QVBoxLayout()
        self.setlayout = self.ly
        self.ly_main = QtWidgets.QGridLayout()
        self.ly.addLayout(self.ly_main)
        
        # IMAGE PREVIEW CHECKBOX
        self.ly_is_preview_before = QtWidgets.QFormLayout()
        self.ly_main.addLayout(self.ly_is_preview_before,1,0,1,6)
        self.in_is_preview_before = QtWidgets.QCheckBox()
        self.in_is_preview_before.setCheckState(QtGui.Qt.Checked)
        self.in_is_preview_before.stateChanged.connect(self.app_update_state)
        self.ly_is_preview_before.addRow(r"Auto preview pre-processed image", self.in_is_preview_before)
        #
        self.ly_is_preview_after = QtWidgets.QFormLayout()
        self.ly_main.addLayout(self.ly_is_preview_after,1,6,1,6)
        self.in_is_preview_after = QtWidgets.QCheckBox()
        self.in_is_preview_after.setCheckState(QtGui.Qt.Unchecked)
        self.in_is_preview_after.stateChanged.connect(self.app_update_state)
        self.ly_is_preview_after.addRow(r"Auto preview post-processed image", self.in_is_preview_after)
        
        # IMAGE PREVIEW
        self.wx_image_preview_before = QtWidgets.QGraphicsScene()
        self.wx_image_preview_before_view = QtWidgets.QGraphicsView(self.wx_image_preview_before)
        self.wx_image_preview_before_view.setStyleSheet("background-color: grey")
        self.wx_image_preview_before_view.setMinimumWidth(360)
        self.wx_image_preview_before_view.setMinimumHeight(360)
        self.ly_main.addWidget(self.wx_image_preview_before_view,2,0,1,6)
        #
        self.wx_image_preview_after = QtWidgets.QGraphicsScene()
        self.wx_image_preview_after_view = QtWidgets.QGraphicsView(self.wx_image_preview_after)
        self.wx_image_preview_after_view.setStyleSheet("background-color: grey")
        self.wx_image_preview_after_view.setMinimumWidth(360)
        self.wx_image_preview_after_view.setMinimumHeight(360)
        self.ly_main.addWidget(self.wx_image_preview_after_view,2,6,1,6)

        # SLIDER        
        self.wx_input_zoom_scale = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.ly_main.addWidget(self.wx_input_zoom_scale,3,0,1,12)
        self.wx_input_zoom_scale.valueChanged.connect(self.app_update_zoom)

        # FORMS WATERMARK SETTING
        self.wx_form_watermark = QtWidgets.QGroupBox()
        self.wx_form_watermark.setTitle("Watermark Settings")
        self.ly_form_watermark = QtWidgets.QFormLayout(self.wx_form_watermark)
        self.ly_main.addWidget(self.wx_form_watermark,4,0,1,6)
        # WATERMARK TEXT 
        self.in_watermarkText = QtWidgets.QLineEdit()
        self.in_watermarkText.setText("This is the watermark text (min. 30 characters)")
        self.ly_form_watermark.addRow(r"Watermark text", self.in_watermarkText)
        # WATERMARK FONT SIZE
        self.in_watermarkSize = QtWidgets.QSpinBox()
        self.in_watermarkSize.setRange(25, 75)
        self.in_watermarkSize.setValue(50)
        self.ly_form_watermark.addRow(r"Watermark font size", self.in_watermarkSize)
        # WATERMARK TEXT COLOR SELECTOR
        self.ly_color_selector = QtWidgets.QHBoxLayout()
        self.ly_form_watermark.addRow(self.ly_color_selector)
        # WATERMARK TEXT COLOR BUTTON
        self.wx_button_color_set = QtWidgets.QPushButton("Select color")
        self.wx_button_color_set.clicked.connect(self.app_select_color)
        self.ly_color_selector.addWidget(self.wx_button_color_set)
        # WATERMARK TEXT COLOR PALETTE
        self.wx_color_palette = QtWidgets.QLabel()
        self.wx_color_palette.setAutoFillBackground(True)
        self.wx_color_palette.setFixedSize(40, 20)
        palette = self.wx_color_palette.palette()
        palette.setColor(QtGui.QPalette.Window, self.im_watermarkColor)
        self.wx_color_palette.setPalette(palette)
        self.ly_color_selector.addWidget(self.wx_color_palette)
        # WATERMARK OPACITY
        self.wx_input_opacity = QtWidgets.QSpinBox()
        self.wx_input_opacity.setRange(5, 100)
        self.wx_input_opacity.setValue(5)
        self.wx_input_opacity.setSingleStep(5)
        self.wx_input_opacity.setSuffix("%")
        self.ly_form_watermark.addRow(r"Watermark opacity", self.wx_input_opacity)
        # WATERMARK DISTORTION
        self.wx_input_distortion = QtWidgets.QSpinBox()
        self.wx_input_distortion.setRange(0, 10)
        self.wx_input_distortion.setValue(5)
        self.ly_form_watermark.addRow(r"Watermark distortion", self.wx_input_distortion)

        # FORMS SAVING
        self.wx_form_save = QtWidgets.QGroupBox()
        self.wx_form_save.setTitle("Saving Preferences")
        self.ly_form_save = QtWidgets.QFormLayout(self.wx_form_save)
        self.ly_main.addWidget(self.wx_form_save,4,6,1,6)
        # SAVING FOLDER FLAG
        self.wx_is_save_at_source = QtWidgets.QCheckBox()
        self.wx_is_save_at_source.setCheckState(QtGui.Qt.Checked)
        self.wx_is_save_at_source.stateChanged.connect(self.app_update_state)
        self.ly_form_save.addRow(r"Save to images source folder",self.wx_is_save_at_source)
        # SAVING FILE SUFFIX
        self.wx_input_suffix  = QtWidgets.QLineEdit()
        self.wx_input_suffix.setText("_watermark")
        self.ly_form_save.addRow(r"Output filename suffix", self.wx_input_suffix)
        # SAVING OVERWRITE FLAG
        self.in_is_save_overwrite = QtWidgets.QCheckBox()
        self.in_is_save_overwrite.setCheckState(QtGui.Qt.Unchecked)
        self.in_is_save_overwrite.stateChanged.connect(self.app_update_state)
        self.ly_form_save.addRow(r"Auto overwrite existing files",self.in_is_save_overwrite)

        ### Save Dialog
        self.ly_group_save = QtWidgets.QHBoxLayout()
        self.ly_main.addLayout(self.ly_group_save, 5,0,1,12)
        #
        self.wx_save_location  = QtWidgets.QLineEdit()
        self.wx_save_location.setText("Using each image source folder as save folder")
        self.wx_save_location.setEnabled(False)
        self.ly_group_save.addWidget(self.wx_save_location)
        #
        self.wx_set_save_location = QtWidgets.QPushButton("Set Save Location")
        self.wx_set_save_location.setEnabled(False)
        self.wx_set_save_location.clicked.connect(self.app_set_save_location)
        self.ly_group_save.addWidget(self.wx_set_save_location)
        #
        self.wx_save = QtWidgets.QPushButton("Save")
        self.wx_save.clicked.connect(self.app_save_image)
        self.ly_group_save.addWidget(self.wx_save)

        self.wx_main = QtWidgets.QWidget()
        self.wx_main.setLayout(self.ly)
        self.setCentralWidget(self.wx_main)

        self.wx_statusbar = QtWidgets.QStatusBar()
        self.setStatusBar(self.wx_statusbar)
        self.wx_statusbar.setSizeGripEnabled(False)
        self.wx_statusbar.showMessage("Ready")

        self.wx_image_preview_before_view.horizontalScrollBar().valueChanged.connect(lambda: self.app_change_scroll(0))
        self.wx_image_preview_before_view.verticalScrollBar().valueChanged.connect(lambda: self.app_change_scroll(0))
        self.wx_image_preview_after_view.horizontalScrollBar().valueChanged.connect(lambda: self.app_change_scroll(1))
        self.wx_image_preview_after_view.verticalScrollBar().valueChanged.connect(lambda: self.app_change_scroll(1))

        ### SIDEBAR
        self.wd_leftSideBar = QtWidgets.QDockWidget('Batch File List', self)
        self.wd_leftSideBar.setFeatures(QtWidgets.QDockWidget.DockWidgetMovable)
        self.addDockWidget(QtGui.Qt.LeftDockWidgetArea, self.wd_leftSideBar)
        self.wx_leftSideBar = QtWidgets.QWidget()
        self.ly_left_sidebar = QtWidgets.QGridLayout()
        self.wx_leftSideBar.setLayout(self.ly_left_sidebar)
        self.wd_leftSideBar.setWidget(self.wx_leftSideBar)

        # Set up the model
        self.model = QtSql.QSqlTableModel(self)
        self.model.setTable("files")
        self.model.setEditStrategy(QtSql.QSqlTableModel.OnFieldChange)
        self.model.setHeaderData(0, QtGui.Qt.Horizontal, "File URL")
        self.model.setHeaderData(1, QtGui.Qt.Horizontal, "File Name")
        self.model.setHeaderData(2, QtGui.Qt.Horizontal, "Width")
        self.model.setHeaderData(3, QtGui.Qt.Horizontal, "Height")
        
        # Set up the view
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.model.select()
        self.view.resizeColumnsToContents()
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.view.clicked.connect(self.view_click)

        self.header = self.view.horizontalHeader()       
        self.header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)

        self.ly_left_sidebar.addWidget(self.view,0,0,1,3)

        # + Button
        self.wxOpenImageButton = QtWidgets.QPushButton("+")
        self.ly_left_sidebar.addWidget(self.wxOpenImageButton, 1,0,1,1)
        self.wxOpenImageButton.clicked.connect(self.app_open_image)
        # - Button
        self.wxRemoveImageButton = QtWidgets.QPushButton("-")
        self.ly_left_sidebar.addWidget(self.wxRemoveImageButton, 1,1,1,1)
        self.wxRemoveImageButton.clicked.connect(self.app_remove_image)
        # Reset Button
        self.wxResetButton = QtWidgets.QPushButton("Reset")
        self.ly_left_sidebar.addWidget(self.wxResetButton, 1,2,1,1)
        self.wxResetButton.clicked.connect(self.app_reset)
        
        # Log
        self.wx_log = QtWidgets.QTextEdit()
        self.logger.add_output(self.wx_log)
        self.ly_left_sidebar.addWidget(self.wx_log, 3,0,1,3)

        self.app_update_state()

    @QtCore.Slot()
    def app_exit(self):
        app.quit()

    @QtCore.Slot()
    def app_info(self):
        app_info = QtWidgets.QMessageBox()
        app_info.setText("Copyright ©2021 Aditia Trihadian")
        app_info.exec()

    def image_setOpacity(self, im):
        """Returns an image with reduced opacity."""
        if im.mode != 'RGBA':
            im = im.convert('RGBA')
        else:
            im = im.copy()
        alpha = im.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(self.wx_input_opacity.value()/100)
        im.putalpha(alpha)
        return im

    @QtCore.Slot()
    def view_click(self):
        self.im_index = self.view.selectedIndexes()[0].data()
        self.app_update_state()
    
    def app_update_state(self):
        sc=self.wx_input_zoom_scale.value()/100*3+1

        if self.wx_is_save_at_source.isChecked() == True:
            self.wx_set_save_location.setEnabled(False)
            self.wx_save_location.setText("Using each image source folder as save folder")
        else:
            self.wx_set_save_location.setEnabled(True)
            self.wx_save_location.setText(self.save_location)

        self.wx_image_preview_before.clear()
        if self.in_is_preview_before.isChecked() == True:
            if self.view.selectedIndexes():
                self.im_before = Image.open(self.im_index).convert("RGBA")
                self.im_before = ImageOps.exif_transpose(self.im_before)
            if self.im_before is None:
                self.wx_input_zoom_scale.setEnabled(False)
                self.wx_image_preview_before_view.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)
                self.wx_image_preview_before_view.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)
            else:
                self.wx_image_preview_before.addPixmap(QtGui.QPixmap.fromImage(ImageQt(self.im_before)))
                self.wx_input_zoom_scale.setEnabled(True)
                self.wx_image_preview_before_view.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOn)
                self.wx_image_preview_before_view.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOn)

        self.wx_image_preview_after.clear()
        if self.in_is_preview_after.isChecked() == True:
            self.in_is_preview_before.setCheckState(QtGui.Qt.Checked)
            if self.im_before is not None:
                self.app_preview_watermark()
            if self.im_after is None:
                self.wx_save.setEnabled(False)
                self.wx_image_preview_after_view.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)
                self.wx_image_preview_after_view.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOff)
            else:
                self.wx_image_preview_after.addPixmap(QtGui.QPixmap.fromImage(ImageQt(self.im_after)))
                self.wx_save.setEnabled(True)
                self.wx_image_preview_after_view.setVerticalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOn)
                self.wx_image_preview_after_view.setHorizontalScrollBarPolicy(QtGui.Qt.ScrollBarAlwaysOn)

        if self.view.selectedIndexes():
            self.wxRemoveImageButton.setEnabled(True)
        else:
            self.wxRemoveImageButton.setEnabled(False)
        self.app_update_zoom()

    @QtCore.Slot()
    def app_update_zoom(self):
        sc=self.wx_input_zoom_scale.value()/100*2+1
        if len(self.wx_image_preview_before.items()) > 0:
            self.wx_image_preview_before_view.fitInView(self.wx_image_preview_before.items()[0], QtCore.Qt.KeepAspectRatio)
            self.wx_image_preview_before_view.scale(sc, sc)
            self.wx_image_preview_before_view.centerOn(self.wx_image_preview_before.items()[0])
        if len(self.wx_image_preview_after.items()) > 0:
            self.wx_image_preview_after_view.fitInView(self.wx_image_preview_after.items()[0], QtCore.Qt.KeepAspectRatio)
            self.wx_image_preview_after_view.scale(sc, sc)
            self.wx_image_preview_after_view.centerOn(self.wx_image_preview_after.items()[0])

    @QtCore.Slot()
    def app_change_scroll(self, trigger):
        if len(self.wx_image_preview_before.items()) > 0 and len(self.wx_image_preview_after.items()) > 0 and trigger==0:
            self.wx_image_preview_after_view.horizontalScrollBar().setValue( self.wx_image_preview_before_view.horizontalScrollBar().value() )
            self.wx_image_preview_after_view.verticalScrollBar().setValue( self.wx_image_preview_before_view.verticalScrollBar().value() )

        if len(self.wx_image_preview_before.items()) > 0 and len(self.wx_image_preview_after.items()) > 0  and trigger==1:
            self.wx_image_preview_before_view.horizontalScrollBar().setValue( self.wx_image_preview_after_view.horizontalScrollBar().value() )
            self.wx_image_preview_before_view.verticalScrollBar().setValue( self.wx_image_preview_after_view.verticalScrollBar().value() )

    @QtCore.Slot()
    def app_select_color(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            palette = self.wx_color_palette.palette()
            palette.setColor(QtGui.QPalette.Window, color)
            self.wx_color_palette.setPalette(palette)
            self.im_watermarkColor=color

    @QtCore.Slot()
    def app_reset(self):
        self.im_before=None
        self.im_after=None
        self.app_init_sql()
        self.model.select()
        self.app_update_state()
        self.logger.write("Cleared all changes!")


    def app_add_watermark(self, im):
        width, height = im.size
        line_height = math.floor(height / 15 * (self.in_watermarkSize.value()/75)  )

        im_txt=Image.new("L", (width*1,height*1))
        im_txt_draw = ImageDraw.Draw(im_txt)
        font = ImageFont.truetype("arial.ttf", line_height)
        i=0
        while i < height*2:
            im_txt_draw.text( (-i, i), (self.in_watermarkText.text()+" ")*5,  font=font, fill=255)
            i=i+line_height
        wd = WaveDeformer()
        wd.intensity=self.wx_input_distortion.value()
        im_txt = ImageOps.deform(im_txt, wd)

        im_txt_2 = im_txt.copy()
        im_txt = ImageOps.colorize(im_txt, black=(0,0,0), white=(self.im_watermarkColor.red(), self.im_watermarkColor.green(), self.im_watermarkColor.blue()))
        im_txt_2 = self.image_setOpacity(im_txt_2)

        im.paste(im_txt, (0, 0),  im_txt_2)
        return im.copy()

    def app_preview_watermark(self):
        self.wx_statusbar.showMessage("Working...")
        im_before=self.im_before.copy()
        im_after=self.app_add_watermark(im_before)
        self.im_after = im_after

        self.wx_statusbar.showMessage("Ready")

    def app_insert_image(self, file_urls):
        for file_url in file_urls:
            im = Image.open(file_url)
            width, height = im.size
            file_name = os.path.basename(file_url)
            record = self.model.record()
            record.setValue("file_url", file_url)
            record.setValue("file_name", file_name)
            record.setValue("width", width)
            record.setValue("height", height)
            self.model.insertRecord(-1, record)
            self.model.submitAll()
            self.logger.write("Added image: "+file_name)

        self.model.select()
        self.app_update_state()
    
    @QtCore.Slot()
    def app_open_image(self, event):
        file_urls = QtWidgets.QFileDialog.getOpenFileNames(self, r"Open Image", "", r"Image Files (*.png *.jpg *.jpeg *.bmp)")[0]
        self.app_insert_image(file_urls)

    def dropEvent(self, event):
        file_urls = event.mimeData().urls()
        self.app_insert_image([file_url.toLocalFile() for file_url in file_urls])

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    @QtCore.Slot()
    def app_remove_image(self, event):
        index = self.view.currentIndex()
        
        self.logger.write("Removed image: " + self.view.selectedIndexes()[1].data())

        self.model.removeRow(index.row())
        self.model.submitAll()
        self.model.select()
        self.app_update_state()

    def app_init_sql(self):
        if self.con is None:
            self.con = QtSql.QSqlDatabase.addDatabase("QSQLITE")
            self.con.setDatabaseName("files.sqlite")
            self.con.open()
        createTableQuery = QtSql.QSqlQuery()
        createTableQuery.exec(
            r"""
            DROP TABLE files
            """
        )
        createTableQuery.exec(
            r"""
            CREATE TABLE files (
                file_url TEXT NOT NULL,
                file_name TEXT NOT NULL,
                width INTEGER,
                height INTEGER
            )
            """
        )
        return True

    @QtCore.Slot()
    def app_set_save_location(self, event):
        save_location = QtWidgets.QFileDialog.getExistingDirectory(self, r"Set Save Directory", "")
        if os.path.isdir(save_location):
            self.save_location = save_location
        self.app_update_state()

    @QtCore.Slot()
    def app_save_image(self):
        for row in range(self.model.rowCount()):
            filepath = self.model.data(self.model.index(row, 0))
            
            filedir, filename_full = os.path.split(filepath)
            filename, filename_ext = os.path.splitext(os.path.basename(filepath))

            im_before = Image.open(filepath)
            im_before = ImageOps.exif_transpose(im_before)

            im_after = self.app_add_watermark(im_before)

            if self.wx_is_save_at_source.isChecked() == True:
                save_filepath = os.path.join(filedir, filename + self.wx_input_suffix.text() + filename_ext)
            else:
                save_filepath = os.path.join(self.wx_save_location.text(), filename + self.wx_input_suffix.text() + filename_ext)

            save_filedir = os.path.split(save_filepath)[0]
            save_filename, save_filename_ext = os.path.splitext(os.path.basename(save_filepath))
            
            if os.path.isdir(save_filedir):
                if os.path.isfile(save_filepath) == True and self.in_is_save_overwrite.isChecked() == True:
                    im_after.save(save_filepath)
                    self.logger.write("Overwritten:" + save_filepath)
                elif os.path.isfile(save_filepath) == True and self.in_is_save_overwrite.isChecked() == False:
                    self.logger.write("File exists (Overwriting disallowed):" + save_filepath)
                elif os.path.isfile(save_filepath) == False:
                    im_after.save(save_filepath)
                    self.logger.write("Saved:" + save_filepath)

if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    window = MyWidget()

    screen = app.primaryScreen()
    size = screen.size()

    window.resize(1320, 600)

    window.show()

    app.setStyle("Fusion")

    # STYLE DARK MODE
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window,             QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.WindowText,         QtGui.QColor("white"))
    palette.setColor(QtGui.QPalette.Base,               QtGui.QColor(25, 25, 25))
    palette.setColor(QtGui.QPalette.AlternateBase,      QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.ToolTipBase,        QtGui.QColor("black"))
    palette.setColor(QtGui.QPalette.ToolTipText,        QtGui.QColor("white"))
    palette.setColor(QtGui.QPalette.Text,               QtGui.QColor("white"))
    palette.setColor(QtGui.QPalette.Button,             QtGui.QColor(53, 53, 53))
    palette.setColor(QtGui.QPalette.ButtonText,         QtGui.QColor("white"))
    palette.setColor(QtGui.QPalette.BrightText,         QtGui.QColor("red"))
    palette.setColor(QtGui.QPalette.Link,               QtGui.QColor(42, 130, 218))
    palette.setColor(QtGui.QPalette.Highlight,          QtGui.QColor(42, 130, 218))
    palette.setColor(QtGui.QPalette.HighlightedText,    QtGui.QColor("black"))
    app.setPalette(palette)

    sys.exit(app.exec())