# UCI Online Retail

Second real dataset used to confirm BIFlow is not hardcoded to Olist.

## Source

UCI Machine Learning Repository, Online Retail (IID 352)

https://archive.ics.uci.edu/dataset/352/online+retail

```bash
python scripts/download_demo_data.py
```

Files extract to `data/raw/uci_online_retail/`. Upload the spreadsheet through the UI.

## Notes

- Invoice-level retail transactions
- Different column names (`InvoiceNo`, `StockCode`, `Quantity`, `UnitPrice`)
- The same profiler, quality engine, semantic inference and KPI compiler must handle it
