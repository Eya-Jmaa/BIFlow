# Olist Brazilian E-Commerce

Primary demonstration dataset for BIFlow.

## Source

Kaggle: [olistbr/brazilian-ecommerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)

Published by Olist. Follow the dataset’s license and usage conditions on Kaggle. Do **not** modify the original files. BIFlow stores uploads in `data/raw/` and writes processed parquet under `data/processed/{run_id}/` through the ETL engine.

## Import

```bash
kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw/olist --unzip
```

Then create a project in the UI and upload the CSV files (orders, customers, order items, payments, products are a good starting set).

## Typical tables

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_geolocation_dataset.csv`
- `product_category_name_translation.csv`

## Relationships the profiler should validate statistically

- orders.customer_id ↔ customers.customer_id
- orders.order_id ↔ payments.order_id
- orders.order_id ↔ order_items.order_id
- order_items.product_id ↔ products.product_id

BIFlow must not hardcode these joins. Overlap and uniqueness are measured at runtime.

## Limitations

- Some orders lack matching payment or item rows
- Geolocation is keyed by zip code prefix, not a perfect address grain
- Product category names may require the translation table
- Reviews and geolocation are large; start with the core commerce tables if memory is limited
