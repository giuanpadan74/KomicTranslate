from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import Qt
import zipfile
import json
from pathlib import Path

class JoinCtprDialog(QtWidgets.QDialog):
    def __init__(self, ctpr_files, parent=None):
        super().__init__(parent)
        self.ctpr_files = ctpr_files
        self.file_mappings = {}  # {original_name: new_name}
        self.setupUI()
        self.loadFileList()
        
    def setupUI(self):
        self.setWindowTitle("Unisci file CTPR - Gestione nomi file")
        self.setModal(True)
        self.resize(600, 400)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Etichetta informativa
        info_label = QtWidgets.QLabel(
            "I seguenti file immagine verranno importati. Puoi rinominarli prima dell'unione:"
        )
        layout.addWidget(info_label)
        
        # Tabella per mostrare e modificare i nomi dei file
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["File CTPR", "Nome originale", "Nuovo nome"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        
        # Pulsanti
        button_layout = QtWidgets.QHBoxLayout()
        
        self.reset_button = QtWidgets.QPushButton("Ripristina nomi originali")
        self.reset_button.clicked.connect(self.resetNames)
        button_layout.addWidget(self.reset_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QtWidgets.QPushButton("Annulla")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.merge_button = QtWidgets.QPushButton("Unisci")
        self.merge_button.clicked.connect(self.accept)
        self.merge_button.setDefault(True)
        button_layout.addWidget(self.merge_button)
        
        layout.addLayout(button_layout)
        
    def loadFileList(self):
        """Carica la lista dei file immagine da tutti i file CTPR"""
        row = 0
        
        for ctpr_file in self.ctpr_files:
            try:
                with zipfile.ZipFile(ctpr_file, 'r') as zip_ref:
                    # Leggi project_data.json per determinare il tipo di progetto
                    project_data = json.loads(zip_ref.read('project_data.json'))
                    save_type = project_data.get('save_type', 'single_image')
                    
                    ctpr_name = Path(ctpr_file).stem
                    
                    if save_type == 'single_image':
                        # Cerca immagini nella cartella images/ o nella root
                        image_files = []
                        for file_name in zip_ref.namelist():
                            if ((file_name.startswith('images/') or '/' not in file_name) and 
                                file_name.endswith(('.jpg', '.jpeg', '.png')) and 
                                'cleaned' not in file_name.lower()):
                                image_files.append(file_name)
                        
                        for img_file in image_files:
                            original_name = Path(img_file).name
                            self.addFileRow(row, ctpr_name, original_name, original_name)
                            row += 1
                    else:
                        # Progetto multi-immagine
                        image_files = []
                        for file_name in zip_ref.namelist():
                            if (file_name.startswith('images/') and 
                                file_name.endswith(('.jpg', '.jpeg', '.png')) and 
                                'cleaned' not in file_name.lower()):
                                image_files.append(file_name)
                        
                        for img_file in sorted(image_files):
                            original_name = Path(img_file).name
                            self.addFileRow(row, ctpr_name, original_name, original_name)
                            row += 1
                            
            except Exception as e:
                print(f"Errore nel leggere {ctpr_file}: {e}")
                
    def addFileRow(self, row, ctpr_name, original_name, new_name):
        """Aggiunge una riga alla tabella"""
        self.table.setRowCount(row + 1)
        
        # Colonna 1: Nome file CTPR (non modificabile)
        ctpr_item = QtWidgets.QTableWidgetItem(ctpr_name)
        ctpr_item.setFlags(ctpr_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, ctpr_item)
        
        # Colonna 2: Nome originale (non modificabile)
        original_item = QtWidgets.QTableWidgetItem(original_name)
        original_item.setFlags(original_item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 1, original_item)
        
        # Colonna 3: Nuovo nome (modificabile)
        new_item = QtWidgets.QTableWidgetItem(new_name)
        self.table.setItem(row, 2, new_item)
        
        # Salva il mapping
        self.file_mappings[original_name] = new_name
        
        # Connetti il segnale di modifica.
        # itemChanged e' un SEGnale: assegnandogli un attributo Python il
        # segnale non veniva mai collegato (era silenziosamente inefficace).
        new_item.itemChanged.connect(lambda _item=None, r=row: self.updateMapping(r))
        
    def updateMapping(self, row):
        """Aggiorna il mapping quando l'utente modifica un nome"""
        original_name = self.table.item(row, 1).text()
        new_name = self.table.item(row, 2).text()
        self.file_mappings[original_name] = new_name
        
    def resetNames(self):
        """Ripristina tutti i nomi originali"""
        for row in range(self.table.rowCount()):
            original_name = self.table.item(row, 1).text()
            self.table.item(row, 2).setText(original_name)
            self.file_mappings[original_name] = original_name
            
    def getFileMappings(self):
        """Restituisce il dizionario dei mapping dei nomi file"""
        # Aggiorna i mapping con i valori correnti della tabella
        for row in range(self.table.rowCount()):
            original_name = self.table.item(row, 1).text()
            new_name = self.table.item(row, 2).text()
            self.file_mappings[original_name] = new_name
        return self.file_mappings
    def accept(self):
        """Esegue l'unione dei file CTPR"""
        try:
            from app.projects.project_state import join_ctpr_files
            
            # Ottieni i mapping dei nomi file
            file_mappings = self.getFileMappings()
            
            # Chiedi all'utente dove salvare il file unito
            output_file, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Salva file CTPR unito",
                "",
                "File CTPR (*.ctpr)"
            )
            
            if output_file:
                if not output_file.endswith('.ctpr'):
                    output_file += '.ctpr'
                
                # Esegui l'unione
                success = join_ctpr_files(self.ctpr_files, output_file, file_mappings)
                
                if success:
                    QtWidgets.QMessageBox.information(
                        self,
                        "Successo",
                        f"File CTPR unito salvato con successo:\n{output_file}"
                    )
                    super().accept()
                else:
                    QtWidgets.QMessageBox.critical(
                        self,
                        "Errore",
                        "Errore durante l'unione dei file CTPR"
                    )
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Errore",
                f"Errore durante l'unione: {str(e)}"
            )