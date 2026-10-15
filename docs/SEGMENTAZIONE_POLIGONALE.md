# Segmentazione Poligonale Dei Balloon

## Obiettivo

La pipeline di segmentazione ora privilegia una regione poligonale interna al balloon.
Il fallback rettangolare resta attivo quando il poligono non puo` essere costruito in modo affidabile.

## Principi

- `xyxy` resta compatibile con il codice esistente.
- `polygon_points` diventa il vincolo preferito per segmentazione e pulizia.
- `bubble_xyxy` resta come fallback e bounding box derivata.
- Manuale e batch riusano la stessa logica di clipping quando il blocco ha gia` una regione poligonale.

## Flusso Aggiornato

1. `Rileva`
   - associa il testo a un balloon tramite `bubble_xyxy`
   - prova a estrarre un poligono dal balloon con `make_bubble_mask()`
2. `Segmenta`
   - genera i componenti candidati come prima
   - se il poligono esiste, filtra i componenti con overlap minimo sul poligono
   - se il poligono non esiste, usa il clipping rettangolare legacy
3. `Pulisci`
   - la mask finale e` ritagliata sul poligono del balloon se presente
   - altrimenti resta il clipping su `bubble_xyxy`
4. `Persistenza`
   - `polygon_points` e `bubble_xyxy` sono serializzati nei blocchi progetto

## File Coinvolti

- `modules/utils/polygon_region.py`
  - utility per normalizzazione poligoni, conversione a bbox/mask, filtro componenti
- `modules/utils/textblock.py`
  - supporto `polygon_points` dentro `TextBlock`
- `modules/detection.py`
  - estrazione poligono del balloon e filtro segmentazione
- `modules/utils/pipeline_utils.py`
  - clipping della mask finale su poligono
- `modules/utils/textblock_serialization.py`
  - serializzazione e deserializzazione blocchi
- `app/controllers/project_controller.py`
  - save/load progetto con `polygon_points`
- `app/controllers/ui_controller.py`
  - ricalcolo manuale con riuso della regione balloon
- `app/ui/commands/box.py`
  - undo/redo coerente con poligono
- `app/controllers/batch_controller/block_sync.py`
  - sync batch con ereditarieta` della regione balloon

## Compatibilita`

- Nessun contratto storico e` stato rimosso.
- I blocchi senza `polygon_points` continuano a usare il comportamento legacy.
- Il render continua a basarsi su `xyxy`, quindi la compatibilita` visiva esistente e` preservata.

## Overlay Canvas

- Il canvas continua a usare rettangoli ed ellissi come editor principale.
- Se un `TextBlock` possiede `polygon_points`, viene creato un overlay poligonale visibile.
- L’overlay non sostituisce la box: la affianca.
- La selezione continua a passare dal rettangolo/ellisse, quindi l’editor esistente non viene rotto.
- Quando la box e` selezionata, i vertici del poligono diventano trascinabili per la correzione manuale.
- Le modifiche al poligono aggiornano `polygon_points`, `bubble_xyxy` e il filtro degli `inpaint_bboxes`.

## Limiti Attuali

- Il layout del testo dentro forme irregolari non e` ancora `polygon-aware`.
- L’editing UI del poligono e` limitato ai vertici; non esistono ancora strumenti avanzati di smoothing/inserimento/rimozione punti.
- L’estrazione del poligono usa il contorno ricavato dal balloon e non ancora una regione "usable area" ottimizzata per il testo.

## Prossimi Passi Consigliati

- introdurre una UI per correzione manuale del poligono
- rendere il rendering text layout consapevole della forma poligonale
- separare ulteriormente la logica di `TextBlock` in moduli piu` piccoli, dato che il file e` gia` molto esteso
