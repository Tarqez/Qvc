Qvc
===

New quantity & price manager


Linee Guida
-----------

1. Nel db carico tutti i ga_code (senza filtrare) e marko le righe (prodotti) che non voglio online (:PERCHE?)
2. Qvc permette solo 2 operazioni sulle quantità e sui prezzi:
	1. aggiornamento quantità e prezzi
	2. agganciamento e controllo (agganciamento ebay-db, controllo quantità e prezzi)
3. Qvc cancella da solo le righe obsolete (con qty=0 per 3+ mesi) tramite il meccanismo del timestamp
4. Colonne db: ga_code, itemid, qty, extra_qty, prc, extra_prc, notes, qty_changed, prc_changed, timestamp



                {>= 0 ... ho pezzi in più
    extra_qty = {
                {< 0  ... righe che non voglio online


    ebay_qty = f(qty, extra_qty)

    f = SUM(q-1) + extra_qty | 0 if extra_qty <0

    extra_prc = 0 ignore | > 0 consider this in place of prc 