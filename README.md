Qvc
===

New quantity manager


Linee Guida
-----------

1 - Nel db carico tutti i ga_code (senza filtrare) e marko le righe (prodotti) che non voglio online:PERCHE?
2 - Qvc permette solo 2 operazioni:
	1) aggiornamento quantità
	2) allineamento/agganciamento (agganciamento ebay-db, allineamento quantità)
3 - Qvc cancella da solo le righe obsolete (con qty=0 per 3+ mesi) tramite il meccanismo del timestamp
4 - Colonne db: ga_code, itemid, qty, extra_qty, notes, changed, timestamp

				{>= 0 ... ho pezzi in più
	extra_qty = {
				{< 0  ... righe che non voglio online


	ebay_qty = f(qty, extra_qty)

	f = SUM q-1 ) + extra_qty | 0 if extra_qty <0