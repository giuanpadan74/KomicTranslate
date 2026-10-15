# Modalità Semi-Automatica (Intermedia) - KomicTranslate

## 📋 Descrizione

La **modalità semi-automatica** è una nuova funzionalità che combina il controllo manuale delle caselle di testo con la velocità del processo automatico batch.

## 🎯 Come Funziona

### Workflow Utente:

1. **Carica un'immagine** in KomicTranslate
2. **Seleziona "Manual"** nella scelta radio Manual/Automatic
3. **Premi "Detect Text Boxes"** (pulsante 0) per rilevare automaticamente le caselle
4. **Modifica le caselle** (opzionale):
   - Elimina caselle indesiderate con il pulsante "Delete"
   - Aggiungi nuove caselle manualmente con "Box Tool"
   - Ridimensiona caselle esistenti
5. **Premi "Translate"** → Il sistema rileva automaticamente che sei in modalità Manual con caselle già rilevate
6. **Processo Automatico** su SOLO l'immagine corrente:
   - ✅ Salta il rilevamento (usa le caselle filtrate)
   - ✅ Esegue OCR automatico
   - ✅ Traduce automaticamente
   - ✅ Inpainting automatico
   - ✅ Rendering automatico
   - ✅ Salvataggio

## 🔧 Implementazione Tecnica

### File Modificati:
- `controller.py`: Funzione `start_batch_process()` modificata
- `controller.py`: Aggiunta funzione `on_semi_auto_batch_finished()`

### Logica di Rilevamento:

```python
is_manual_mode = self.manual_radio.isChecked()
has_current_blocks = (self.curr_img_idx >= 0 and 
                     self.blk_list and 
                     len(self.blk_list) > 0)

if is_manual_mode and has_current_blocks:
    # MODALITÀ SEMI-AUTOMATICA attivata!
```

### Flusso Tecnico:

1. `start_batch_process()` rileva modalità Manual + blocchi esistenti
2. Salva `self.blk_list` (caselle filtrate) in `image_states[current_image]['blk_list']`
3. Salva temporaneamente `image_files` completo in `_original_image_files`
4. Imposta `image_files = [current_image_path]` (solo immagine corrente)
5. Chiama `batch_process(skip_detection=True)` che:
   - Salta il rilevamento per l'immagine corrente
   - Recupera blocchi da `image_states[current_image]['blk_list']`
   - Processa con OCR → Translate → Inpaint → Render
6. Callback `on_semi_auto_batch_finished()`:
   - Ripristina `image_files` originale
   - Mostra messaggio personalizzato
   - Cleanup UI

## ✨ Vantaggi

### Rispetto a Modalità Manual Completa:
- ⚡ **Più veloce**: Non serve premere ogni pulsante manualmente
- 🎯 **Automatico dopo detection**: OCR, traduzione e rendering automatici
- 💾 **Salvataggio automatico**: Immagine salvata senza intervento

### Rispetto a Modalità Automatic Completa:
- 🎨 **Controllo sulle caselle**: Puoi eliminare/modificare caselle prima di tradurre
- ✂️ **Filtro preciso**: Traduci SOLO le caselle che vuoi
- 🖼️ **Singola immagine**: Non processa tutte le immagini, solo quella corrente

## 📊 Confronto Modalità

| Caratteristica | Manual | Semi-Automatica | Automatic |
|---|:---:|:---:|:---:|
| Rilevamento caselle | Manuale | Manuale + Filtro | Automatico |
| Modifica caselle | ✅ | ✅ | ❌ |
| OCR | Manuale (pulsante) | Automatico | Automatico |
| Traduzione | Manuale (pulsante) | Automatico | Automatico |
| Inpainting | Manuale (pulsante) | Automatico | Automatico |
| Rendering | Manuale (pulsante) | Automatico | Automatico |
| Salvataggio | Manuale | Automatico | Automatico |
| Numero immagini | Singola | Singola | Tutte |
| Velocità | ⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Controllo | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ |

## 🎬 Esempi d'Uso

### Caso 1: Tradurre solo alcuni fumetti
```
1. Carica manga con 15 fumetti
2. Detect Text Boxes → rileva 15 caselle
3. Elimina 5 caselle (fumetti da non tradurre)
4. Translate → traduce automaticamente solo i 10 fumetti rimanenti
```

### Caso 2: Correggere detection errato
```
1. Carica immagine
2. Detect Text Boxes → rileva 8 caselle (ma 2 sono sbagliate)
3. Elimina le 2 caselle sbagliate
4. Disegna manualmente 2 nuove caselle corrette
5. Translate → traduce automaticamente con le caselle corrette
```

### Caso 3: Aggiungere caselle mancanti
```
1. Carica immagine
2. Detect Text Boxes → rileva 5 caselle (ma mancano 2 fumetti piccoli)
3. Aggiungi manualmente le 2 caselle mancanti
4. Translate → traduce tutte e 7 le caselle automaticamente
```

## 🚨 Note Importanti

### Requisiti:
- ✅ Devi essere in modalità **Manual** (radio button)
- ✅ Devi avere **almeno 1 casella** rilevata/disegnata
- ✅ L'immagine deve essere **caricata** (`curr_img_idx >= 0`)

### Comportamento:
- 📌 Processa **SOLO** l'immagine corrente
- 📌 Usa **SOLO** le caselle presenti in `self.blk_list`
- 📌 Salta **SEMPRE** il rilevamento automatico
- 📌 Ripristina la lista completa delle immagini dopo il completamento

### Log Console:
```
[SEMI_AUTO_MODE] ═══════════════════════════════════════════════════
[SEMI_AUTO_MODE] Modalità Semi-Automatica Attivata!
[SEMI_AUTO_MODE] Immagine corrente: 0
[SEMI_AUTO_MODE] Caselle filtrate dall'utente: 7
[SEMI_AUTO_MODE] ═══════════════════════════════════════════════════
[SEMI_AUTO_MODE] Stato salvato con 7 caselle
[SEMI_AUTO_MODE] Processo Semi-Automatico avviato
[SEMI_AUTO_MODE] Batch process per 1 immagine (modalità intermedia)
[SEMI_AUTO_MODE] Avvio batch_process con skip_detection=True
...
[SEMI_AUTO_MODE] Lista immagini ripristinata: 10 immagini totali
[SEMI_AUTO_MODE] ═══════════════════════════════════════════════════
[SEMI_AUTO_MODE] Processo Semi-Automatico Completato!
[SEMI_AUTO_MODE] ═══════════════════════════════════════════════════
```

## 🔍 Debug

### Se la modalità non si attiva:
1. Verifica che il radio "Manual" sia selezionato
2. Verifica che `self.blk_list` non sia vuoto (premi Detect Text Boxes prima)
3. Controlla i log console per `[SEMI_AUTO_MODE]`

### Se processa tutte le immagini invece di una sola:
- Verifica che il log mostri `[SEMI_AUTO_MODE]` e non `[BATCH_AUTO_MODE]`
- La modalità automatica tradizionale è attiva se vedi `[BATCH_AUTO_MODE]`

## 🎉 Risultato

Dopo il completamento, vedrai:
- ✅ Immagine tradotta con SOLO le caselle selezionate
- ✅ Messaggio: "L'immagine corrente è stata tradotta con successo utilizzando le caselle selezionate."
- ✅ File salvato automaticamente in cartella timestampata
- ✅ Lista immagini ripristinata (puoi passare alla prossima immagine)

---

**Implementato da**: Assistant AI  
**Data**: 2025-11-25  
**Versione**: 1.0
