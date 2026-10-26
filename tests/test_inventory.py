import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from inventory import InventoryError, InventoryManager, PersistenceError


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.inventory_path = self.data_dir / "inventory.csv"
        self.sales_path = self.data_dir / "sales.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def manager_with_data(self):
        pd.DataFrame([{
            "Name": "Salmon Roll", "Price": 8.5, "Calories": 320, "Quantity": 3
        }]).to_csv(self.inventory_path, index=False)
        return InventoryManager(self.inventory_path, self.sales_path)

    def test_valid_loading_and_missing_file(self):
        manager = InventoryManager(self.inventory_path, self.sales_path)
        self.assertEqual(manager.inventory, [])
        manager = self.manager_with_data()
        self.assertEqual(manager.find_sushi(" salmon roll ").quantity, 3)

    def test_empty_csv_files_are_treated_as_empty(self):
        self.inventory_path.touch()
        self.sales_path.touch()
        manager = InventoryManager(self.inventory_path, self.sales_path)
        self.assertEqual(manager.inventory, [])
        self.assertTrue(manager.revenue_by_item().empty)

    def test_malformed_and_invalid_inventory_are_rejected(self):
        self.inventory_path.write_text("Name,Price\nRoll,8\n", encoding="utf-8")
        with self.assertRaises(InventoryError):
            InventoryManager(self.inventory_path, self.sales_path)
        manager = InventoryManager(self.data_dir / "other.csv", self.sales_path)
        for values in [("Roll", -1, 100, 1), ("Roll", 1, -1, 1), ("Roll", 1, 100, -1)]:
            with self.assertRaises(InventoryError):
                manager.add_sushi(*values)

    def test_duplicate_names_add_and_load_are_rejected(self):
        manager = InventoryManager(self.inventory_path, self.sales_path)
        manager.add_sushi("Roll", 1, 100, 1)
        with self.assertRaises(InventoryError):
            manager.add_sushi(" roll ", 2, 200, 1)
        pd.DataFrame([
            {"Name": "Roll", "Price": 1, "Calories": 100, "Quantity": 1},
            {"Name": "roll", "Price": 2, "Calories": 200, "Quantity": 1},
        ]).to_csv(self.inventory_path, index=False)
        with self.assertRaises(InventoryError):
            InventoryManager(self.inventory_path, self.sales_path)

    def test_add_remove_restock_and_availability(self):
        manager = InventoryManager(self.inventory_path, self.sales_path)
        manager.add_sushi("Tuna", 7, 250, 1)
        self.assertTrue(manager.is_available("tuna"))
        manager.restock("Tuna", 4)
        self.assertEqual(manager.find_sushi("Tuna").quantity, 5)
        manager.remove_sushi("Tuna")
        with self.assertRaises(InventoryError):
            manager.find_sushi("Tuna")

    def test_purchase_persists_inventory_and_sale(self):
        manager = self.manager_with_data()
        self.assertEqual(manager.purchase("salmon roll"), 8.5)
        self.assertEqual(InventoryManager(self.inventory_path, self.sales_path).find_sushi("Salmon Roll").quantity, 2)
        sales = pd.read_csv(self.sales_path)
        self.assertEqual(list(sales.columns), ["Timestamp", "Name", "Unit Price", "Quantity", "Line Total"])
        self.assertEqual(float(sales.iloc[0]["Line Total"]), 8.5)

    def test_insufficient_stock_does_not_create_sale(self):
        manager = self.manager_with_data()
        with self.assertRaises(InventoryError):
            manager.purchase("Salmon Roll", 4)
        self.assertFalse(self.sales_path.exists())
        self.assertEqual(manager.find_sushi("Salmon Roll").quantity, 3)

    def test_sale_persistence_failure_rolls_back_inventory(self):
        manager = self.manager_with_data()
        with patch.object(manager, "_write_atomic", side_effect=[None, PersistenceError("disk full")]):
            with self.assertRaises(PersistenceError):
                manager.purchase("Salmon Roll")
        self.assertEqual(manager.find_sushi("Salmon Roll").quantity, 3)
        self.assertFalse(self.sales_path.exists())
        self.assertEqual(InventoryManager(self.inventory_path, self.sales_path).find_sushi("Salmon Roll").quantity, 3)

    def test_inventory_persistence_failure_rolls_back(self):
        manager = self.manager_with_data()
        with patch.object(manager, "_write_atomic", side_effect=PersistenceError("read-only")):
            with self.assertRaises(PersistenceError):
                manager.purchase("Salmon Roll")
        self.assertEqual(manager.find_sushi("Salmon Roll").quantity, 3)
        self.assertFalse(self.sales_path.exists())

    def test_save_does_not_overwrite_corrupted_existing_inventory(self):
        manager = InventoryManager(self.inventory_path, self.sales_path)
        manager.add_sushi("Roll", 1, 100, 1)
        self.inventory_path.write_text("not,a,valid,schema\n", encoding="utf-8")
        with self.assertRaises(InventoryError):
            manager.save_inventory()
        self.assertEqual(self.inventory_path.read_text(encoding="utf-8"), "not,a,valid,schema\n")

    def test_reports_use_line_totals_and_quantities(self):
        manager = self.manager_with_data()
        manager.record_sale("Salmon Roll", 8.5, 2)
        self.assertEqual(float(manager.revenue_by_item()["Salmon Roll"]), 17.0)
        self.assertEqual(int(manager.quantity_by_item()["Salmon Roll"]), 2)


if __name__ == "__main__":
    unittest.main()
