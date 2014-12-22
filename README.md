Qpm
===

__Quantity & Price Manager for eBay ads__
_Updating eBay price and quantity of ads from Sales Management Software (as of now SMS) export_

### Technologies
Python, SqLite, SQLAlchemy

### Defs

__DB__ - local database in SqLite
__Datasource__ - an export from SMS
__ga_code__ (or gacode) - represents SMS product primary key



Linee Guida
-----------

1. Nel db carico tutti i ga_code (senza filtrare) e marko manualmente le righe (prodotti) che non voglio online perchè non voglio venderli (presentano un problema, p.es. sono neon, hanno la batteria scarica, sono ingombranti)
2. Qpm permette solo 2 operazioni sulle quantità e sui prezzi:
	1. aggiornamento quantità e prezzi
	2. agganciamento e controllo (agganciamento ebay-db, controllo quantità e prezzi)
3. Qpm cancella da solo le righe obsolete (con qty=0 per 3+ mesi) tramite il meccanismo del timestamp
4. Colonne del db: 
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