"""Small CSV-backed sushi inventory and sales application."""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd


INVENTORY_COLUMNS = ["Name", "Price", "Calories", "Quantity"]
SALES_COLUMNS = ["Timestamp", "Name", "Unit Price", "Quantity", "Line Total"]


class InventoryError(ValueError):
    """Raised when an inventory or sales operation cannot be completed."""


class PersistenceError(RuntimeError):
    """Raised when a CSV cannot be safely persisted."""


def _clean_name(name: object) -> str:
    if not isinstance(name, str) or not name.strip():
        raise InventoryError("Sushi name must be a nonempty string.")
    return name.strip()


def _nonnegative_price(price: object) -> float:
    try:
        value = float(price)
    except (TypeError, ValueError) as exc:
        raise InventoryError("Price must be a finite, nonnegative number.") from exc
    if not math.isfinite(value) or value < 0:
        raise InventoryError("Price must be a finite, nonnegative number.")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise InventoryError(f"{field} must be a nonnegative integer.")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise InventoryError(f"{field} must be a nonnegative integer.") from exc
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        raise InventoryError(f"{field} must be a nonnegative integer.")
    return int(numeric)


@dataclass
class SushiPlate:
    name: str
    price: float
    calories: int
    quantity: int

    def __post_init__(self) -> None:
        self.name = _clean_name(self.name)
        self.price = _nonnegative_price(self.price)
        self.calories = _nonnegative_int(self.calories, "Calories")
        self.quantity = _nonnegative_int(self.quantity, "Quantity")

    def __str__(self) -> str:
        return (
            f"SushiPlate(Name: {self.name}, Price: ${self.price:.2f}, "
            f"Calories: {self.calories}, Quantity: {self.quantity})"
        )


class InventoryManager:
    def __init__(self, file_path: str | Path | None = None,
                 sales_path: str | Path | None = None):
        data_dir = Path(__file__).resolve().parent / "data"
        self.file_path = Path(file_path) if file_path else data_dir / "inventory.csv"
        self.sales_path = Path(sales_path) if sales_path else self.file_path.parent / "sales.csv"
        self.inventory = self.load_inventory()

    @staticmethod
    def _inventory_frame(items: Iterable[SushiPlate]) -> pd.DataFrame:
        return pd.DataFrame(
            [{"Name": item.name, "Price": item.price, "Calories": item.calories,
              "Quantity": item.quantity} for item in items],
            columns=INVENTORY_COLUMNS,
        )

    @staticmethod
    def _validate_unique(items: Iterable[SushiPlate]) -> None:
        seen: set[str] = set()
        for item in items:
            key = item.name.casefold()
            if key in seen:
                raise InventoryError(f"Duplicate sushi name: {item.name!r}.")
            seen.add(key)

    def load_inventory(self) -> list[SushiPlate]:
        if not self.file_path.exists():
            return []
        try:
            frame = pd.read_csv(self.file_path, encoding="utf-8")
        except pd.errors.EmptyDataError:
            return []
        except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise PersistenceError(f"Could not read inventory file {self.file_path}: {exc}") from exc
        if list(frame.columns) != INVENTORY_COLUMNS:
            raise InventoryError(
                f"Inventory CSV must have exactly these columns: {', '.join(INVENTORY_COLUMNS)}."
            )
        try:
            items = [
                SushiPlate(row["Name"], row["Price"], row["Calories"], row["Quantity"])
                for _, row in frame.iterrows()
            ]
            self._validate_unique(items)
        except (InventoryError, KeyError) as exc:
            raise InventoryError(f"Invalid inventory data in {self.file_path}: {exc}") from exc
        return items

    def find_sushi(self, name: str) -> SushiPlate:
        clean_name = _clean_name(name)
        matches = [item for item in self.inventory if item.name.casefold() == clean_name.casefold()]
        if not matches:
            raise InventoryError(f"Sushi named {clean_name!r} was not found.")
        if len(matches) > 1:
            raise InventoryError(f"Inventory contains duplicate name {clean_name!r}.")
        return matches[0]

    def add_sushi(self, name: str, price: object, calories: object, quantity: object) -> SushiPlate:
        item = SushiPlate(name, price, calories, quantity)
        if any(existing.name.casefold() == item.name.casefold() for existing in self.inventory):
            raise InventoryError(f"Sushi named {item.name!r} already exists.")
        self.inventory.append(item)
        return item

    def remove_sushi(self, name: str) -> SushiPlate:
        item = self.find_sushi(name)
        self.inventory.remove(item)
        return item

    def update_quantity(self, name: str, quantity: object) -> SushiPlate:
        item = self.find_sushi(name)
        item.quantity = _nonnegative_int(quantity, "Quantity")
        return item

    def restock(self, name: str, quantity: object) -> SushiPlate:
        amount = _nonnegative_int(quantity, "Restock quantity")
        if amount == 0:
            raise InventoryError("Restock quantity must be greater than zero.")
        item = self.find_sushi(name)
        item.quantity += amount
        return item

    def is_available(self, name: str, quantity: object = 1) -> bool:
        requested = _nonnegative_int(quantity, "Quantity")
        return self.find_sushi(name).quantity >= requested

    def display_inventory(self) -> None:
        if not self.inventory:
            print("The inventory is empty.")
            return
        print("\nCurrent Inventory:")
        for item in self.inventory:
            print(item)

    def _write_atomic(self, path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", suffix=".tmp",
                dir=path.parent, delete=False
            ) as handle:
                temporary_name = handle.name
                frame.to_csv(handle, index=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        except (OSError, PermissionError, ValueError) as exc:
            if temporary_name:
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
            raise PersistenceError(f"Could not write {path}: {exc}") from exc

    def save_inventory(self) -> None:
        self._validate_unique(self.inventory)
        if self.file_path.exists():
            existing = InventoryManager(self.file_path, self.sales_path).inventory
            self._validate_unique(existing)
        self._write_atomic(self.file_path, self._inventory_frame(self.inventory))

    def _read_sales(self) -> pd.DataFrame:
        if not self.sales_path.exists():
            return pd.DataFrame(columns=SALES_COLUMNS)
        try:
            frame = pd.read_csv(self.sales_path, encoding="utf-8")
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=SALES_COLUMNS)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
            raise PersistenceError(f"Could not read sales file {self.sales_path}: {exc}") from exc
        if list(frame.columns) != SALES_COLUMNS:
            raise InventoryError(
                f"Sales CSV must have exactly these columns: {', '.join(SALES_COLUMNS)}. "
                "Legacy sales files are not imported automatically."
            )
        for column in ["Unit Price", "Quantity", "Line Total"]:
            if frame[column].isna().any():
                raise InventoryError(f"Sales column {column!r} contains missing values.")
        return frame

    def record_sale(self, name: str, price: object, quantity: object) -> None:
        clean_name = _clean_name(name)
        unit_price = _nonnegative_price(price)
        amount = _nonnegative_int(quantity, "Sale quantity")
        if amount == 0:
            raise InventoryError("Sale quantity must be greater than zero.")
        sales = self._read_sales()
        sale = pd.DataFrame([{
            "Timestamp": datetime.now(timezone.utc).isoformat(),
            "Name": clean_name,
            "Unit Price": unit_price,
            "Quantity": amount,
            "Line Total": unit_price * amount,
        }], columns=SALES_COLUMNS)
        self._write_atomic(self.sales_path, pd.concat([sales, sale], ignore_index=True))

    def _commit_purchase(self, item: SushiPlate, quantity: int) -> float:
        sales = self._read_sales()
        new_quantity = item.quantity - quantity
        if new_quantity < 0:
            raise InventoryError(f"Not enough stock for {item.name!r}.")
        item.quantity = new_quantity
        inventory_frame = self._inventory_frame(self.inventory)
        sales_frame = pd.concat([sales, pd.DataFrame([{
            "Timestamp": datetime.now(timezone.utc).isoformat(),
            "Name": item.name,
            "Unit Price": item.price,
            "Quantity": quantity,
            "Line Total": item.price * quantity,
        }], columns=SALES_COLUMNS)], ignore_index=True)

        old_inventory = self.file_path.read_bytes() if self.file_path.exists() else None
        old_sales = self.sales_path.read_bytes() if self.sales_path.exists() else None
        try:
            self._write_atomic(self.file_path, inventory_frame)
            self._write_atomic(self.sales_path, sales_frame)
        except Exception as exc:
            item.quantity += quantity
            try:
                if old_inventory is None:
                    self.file_path.unlink(missing_ok=True)
                else:
                    self.file_path.write_bytes(old_inventory)
                if old_sales is None:
                    self.sales_path.unlink(missing_ok=True)
                else:
                    self.sales_path.write_bytes(old_sales)
            except OSError as rollback_exc:
                raise PersistenceError(
                    f"Purchase failed and rollback also failed: {rollback_exc}"
                ) from exc
            if isinstance(exc, PersistenceError):
                raise
            raise PersistenceError(f"Purchase failed; changes were rolled back: {exc}") from exc
        return item.price * quantity

    def purchase(self, name: str, quantity: object = 1) -> float:
        amount = _nonnegative_int(quantity, "Purchase quantity")
        if amount == 0:
            raise InventoryError("Purchase quantity must be greater than zero.")
        item = self.find_sushi(name)
        return self._commit_purchase(item, amount)

    def revenue_by_item(self) -> pd.Series:
        sales = self._read_sales()
        if sales.empty:
            return pd.Series(dtype=float, name="Line Total")
        return sales.groupby("Name")["Line Total"].sum()

    def quantity_by_item(self) -> pd.Series:
        sales = self._read_sales()
        if sales.empty:
            return pd.Series(dtype=float, name="Quantity")
        return sales.groupby("Name")["Quantity"].sum()

    def visualize_total_revenue(self) -> None:
        revenue = self.revenue_by_item()
        if revenue.empty:
            print("No sales data found to visualize.")
            return
        revenue.plot(kind="bar", title="Total Revenue by Sushi Type", ylabel="Revenue ($)")
        plt.tight_layout()
        plt.show()

    def visualize_sales(self) -> None:
        sales = self.quantity_by_item()
        if sales.empty:
            print("No sales data found to visualize.")
            return
        sales.plot(kind="bar", title="Total Sales by Sushi Type", ylabel="Quantity Sold")
        plt.tight_layout()
        plt.show()


def customer_mode(manager: InventoryManager) -> None:
    bill = 0.0
    picked: list[str] = []
    while True:
        manager.display_inventory()
        choice = input("Enter sushi name, or 'done' to finish: ").strip()
        if choice.casefold() == "done":
            break
        try:
            bill += manager.purchase(choice)
            picked.append(manager.find_sushi(choice).name)
            print(f"Purchase recorded. Current bill: ${bill:.2f}")
        except (InventoryError, PersistenceError) as exc:
            print(f"Purchase failed: {exc}")
    print(f"\nFinal bill: ${bill:.2f}")
    print("Sushi selected:", ", ".join(picked) if picked else "None")


def _read_nonnegative(prompt: str, integer: bool) -> float | int:
    while True:
        try:
            value = int(input(prompt)) if integer else float(input(prompt))
            if integer:
                return _nonnegative_int(value, prompt.rstrip(": "))
            return _nonnegative_price(value)
        except (ValueError, InventoryError) as exc:
            print(f"Invalid value: {exc}")


def run_cli(data_dir: Path) -> None:
    manager = InventoryManager(data_dir / "inventory.csv", data_dir / "sales.csv")
    while True:
        print("\nSushi Inventory System")
        print("1. Chef Mode\n2. Customer Mode\n3. Exit")
        choice = input("Choose an option: ").strip()
        if choice == "1":
            while True:
                print("\nChef Mode")
                print("1. Add sushi\n2. Remove sushi\n3. Display inventory")
                print("4. Restock sushi\n5. Save and exit\n6. Revenue report\n7. Sales report")
                chef_choice = input("Choose an option: ").strip()
                try:
                    if chef_choice == "1":
                        name = input("Name: ")
                        price = _read_nonnegative("Price: ", False)
                        calories = _read_nonnegative("Calories: ", True)
                        quantity = _read_nonnegative("Quantity: ", True)
                        manager.add_sushi(name, price, calories, quantity)
                        manager.save_inventory()
                        print("Sushi added and inventory saved.")
                    elif chef_choice == "2":
                        manager.remove_sushi(input("Name to remove: "))
                        manager.save_inventory()
                        print("Sushi removed and inventory saved.")
                    elif chef_choice == "3":
                        manager.display_inventory()
                    elif chef_choice == "4":
                        manager.restock(input("Name to restock: "), _read_nonnegative("Quantity: ", True))
                        manager.save_inventory()
                        print("Restock saved.")
                    elif chef_choice == "5":
                        manager.save_inventory()
                        break
                    elif chef_choice == "6":
                        print(manager.revenue_by_item())
                        manager.visualize_total_revenue()
                    elif chef_choice == "7":
                        print(manager.quantity_by_item())
                        manager.visualize_sales()
                    else:
                        print("Unknown Chef Mode option.")
                except (InventoryError, PersistenceError) as exc:
                    print(f"Operation failed: {exc}")
        elif choice == "2":
            customer_mode(manager)
        elif choice == "3":
            break
        else:
            print("Unknown option.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Sushi Inventory System.")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent / "data")
    run_cli(parser.parse_args().data_dir)
