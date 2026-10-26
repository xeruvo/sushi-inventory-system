# Sushi Inventory System

A compact educational Python command-line application for managing sushi inventory and recording customer purchases. It preserves the original Chef Mode and Customer Mode workflow while adding validation, safer CSV persistence, manual restocking, and automated tests.

## Features

- Add, remove, find, and update sushi inventory items.
- Validate names, prices, calories, quantities, and duplicate names.
- Purchase available sushi and record timestamped sales.
- Persist inventory and sales as UTF-8 CSV files.
- Roll back a purchase when either CSV update fails.
- Manually restock an existing item from Chef Mode.
- Report revenue and quantity sold by sushi item.

This is not a production point-of-sale system. It does not process payments, track ingredients, or provide user authentication.

## Requirements and setup (Windows CMD)

Python 3.10 or newer is recommended.

```cmd
cd path\to\sushi-inventory-system
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Run the automated tests:

```cmd
python -m unittest discover -s tests -v
```

## Starting the application

The application uses a predictable data directory. Pass one explicitly with `--data-dir`:

```cmd
python inventory.py --data-dir data
```

The directory is created when a successful write is needed. Runtime `inventory.csv` and `sales.csv` files are ignored by Git.

To start with the fictional sample inventory:

```cmd
mkdir data
copy inventory.example.csv data\inventory.csv
python inventory.py --data-dir data
```

The sample values are illustrative only and are not business records.

## Using the application

### Chef Mode

Chef Mode can:

1. Add a validated sushi item.
2. Remove an existing item.
3. Display inventory.
4. Manually restock an item by a positive integer quantity.
5. Save inventory and exit Chef Mode.
6. Display and plot revenue by sushi item.
7. Display and plot quantity sold by sushi item.

Adding or removing an item and manual restocking save the inventory immediately.

### Customer Mode

Enter an item name to purchase one available plate at a time, or enter `done`. Each successful purchase validates stock, writes the sale, updates inventory, and reports the current bill.

There is **no automatic timed restocking**. The previous background timer was removed because it was not started by the normal application and could race with inventory and sales updates.

## CSV schemas

### Inventory

`inventory.csv` must contain exactly:

| Name | Price | Calories | Quantity |
|---|---:|---:|---:|
| Salmon Roll | 8.50 | 320 | 12 |

Names must be nonempty and unique case-insensitively. Prices are finite and nonnegative. Calories and quantities are nonnegative integers.

### Sales

`sales.csv` is created automatically with exactly:

```text
Timestamp,Name,Unit Price,Quantity,Line Total
```

Revenue reports use the recorded `Line Total`, not a recomputed or ambiguous price sum. Legacy sales files with the former `Name,Price,Quantity` schema are rejected rather than silently reinterpreted.

## Persistence and limitations

Inventory and sales are separate CSV files. A purchase writes temporary files and atomically replaces the target files, retaining the original bytes so the operation can restore them if the second write fails. This is a practical single-process recovery approach, not a database transaction or an ACID guarantee. Interruption, disk failure, or external edits during a multi-file update can still require manual recovery.

Malformed files, missing columns, invalid values, and write errors are reported rather than silently overwritten. A missing inventory file starts an empty inventory; a missing sales file starts an empty sales history.

The application has no real payment processing, no ingredient-level inventory, no authentication, and no automatic timed restocking. It is intended for learning and portfolio demonstration, not production deployment.
