Qpm
===

__Quantity & Price Manager for eBay ads__
_Updating eBay price and quantity of ads from Sales Management Software (as of now SMS) export_

### Technologies
Python, SqLite, SQLAlchemy, eBay FileExchange

### Defs

__DB__ - local database in SqLite
__Datasource__ - an export from SMS
__ga_code__ (or gacode) - represents SMS product primary key


Abstract
--------
Qpm from input files of quantity and price exported from SMS (datasources), outputs a FX csv file for update eBay.


Linee Guida
-----------
Carico nel DB i datasource dei prezzi e delle quantità (ogni riga ha il ga_code), aggiungo i nuovi ga_code e aggiorno quelli esistenti se il nuovo valore di prezzo o quantità differisce dal vecchio (economia delle risorse: scrivo nel DB solo se necessario). Ad ogni caricamento ho un DB aggiornato con il SMS.

Nell'aggiornamento, la riga/prodotto/ga_code viene segnata se il valore (prezzo o quantità) su eBay è da aggiornare (economia delle risorse anche qui: non aggiorno eBay se non è necessario). I valori su ebay sono funzione dei valori del datasource e di quelli manuali, p.es. __ebay_qty(qty, extra_qty)__ con __qty__ valore datasource, __extra_qty__ valore manuale. Valore manuale significa che non proviene da un datasource dunque è "manualmente" inserito nel DB.

Un valore su eBay è da aggiornare allora, se il nuovo valore della funzione (calcolata sul nuovo valore del datasource) differisce dal vecchio; nel calcolo il valore manuale è costante ed è quello attuale nel DB, dunque __il sistema NON rileva le variazioni dei valori manuali__ che pertanto ad ogni cambiamento, bisogna manualmente aggiornare il valore su eBay.

Si possono segnare nel DB le righe/prodotto che non voglio vendere, per cui le quantità su eBay devono andare a zero (indipendentemente dal datasource) e le inserzioni potranno essere chiuse se lo si ritiene opportuno.

Quando su eBay si caricano in qualunque modo nuove inserzioni, avendo cura di indicare nel CustomLabel il ga_code, si rende necessaria l'operzione di agganciamento delle nuove inserzioni al DB. In altre parole bisogna inserire nel DB gli itemID generati da eBay per quelle inserzioni. 

Possiamo reperire tali itemID dal report eBay delle inserzioni attive online, questo report diventa un datasource da caricare nel DB. Contemporaneamente possiamo controllare che le quantità e prezzi su ebay siano corretti, cioè allineati con quelli del DB; quando non lo sono le righe vengono segnate perchè il valore eBay è da aggiornare.

L'operazione di agganciamento, oltre a controllare prezzi e quantità controlla anche gli itemID esistenti, è una vera e propria operzione di reset.

Il DB, dopo il caricamento di un datasource, ha segnate le righe/prodotto per l'aggiornamento dei prezzi e/o quantità, queste info sono consumate dai generatori dei csv FX di eBay che riportano le righe segnate alla condizione di normalità.

 Ogni riga del DB ha un timestamp che riporta il momento dell'ultimo aggiornamento del valore qty, sappiamo allora da quanto tempo non viene movimentato quell'articolo. Questo ci permette di cancellare (e chiudere le relative inserzioni eBay) le righe obsolete, quelle la cui quantità è a zero da molto tempo.


Qpm permette 3 operazioni:
	1. aggiornamento quantità e prezzi su eBay
	2. agganciamento e controllo (agganciamento ebay-db, controllo quantità e prezzi)
	3. eliminazione righe DB e chiusura su eBay ad obsoleti (quelli con qty=0 per 3+ mesi)


Colonne del db: 
	- ga_code
	- itemid
	- qty: _quantità dal datasource_
	- extra_qty: _quantità extra manuale (si somma alla quantità del datasource)_
	- prc: _prezzi dal datasource_
	- extra_prc: _prezzo extra manuale (si sostituisce al prezzo del datasource)_
	- notes: _note sul prodotto (di solito perchè non lo voglio online)_
	- update_qty: _indica che qty online è da aggiornare_
	- update_prc: _indica che prc online è da aggiornare_
	- timestamp: _indica l'ultima volta che ho aggiornato qty nel DB_



                {>= 0 ... ho pezzi in più
    extra_qty = {
                {< 0  ... righe che non voglio online


    ebay_qty = f(qty, extra_qty)

    f = SUM(q-1) + extra_qty | 0 if extra_qty <0

    extra_prc = 0 ignore | > 0 consider this in place of prc 