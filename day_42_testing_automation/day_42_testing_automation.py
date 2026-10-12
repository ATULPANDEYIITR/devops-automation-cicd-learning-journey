#!/usr/bin/env python3
"""Practical testing automation laboratory using only the Python standard library.

Demonstrates unit, integration, smoke, and regression testing through a
small order-processing service with deterministic tests, temporary databases,
HTTP health checks, coverage-like test inventories, and JSON reporting.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Callable, Iterable
from uuid import uuid4

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
LOGGER = logging.getLogger("testing_automation")


class ValidationError(ValueError):
    """Raised when incoming business data violates service rules."""


class InsufficientInventory(RuntimeError):
    """Raised when an order requests more units than are available."""


class DuplicateOrder(RuntimeError):
    """Raised when a caller reuses an existing order identifier."""


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    unit_price: Decimal
    stock: int


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    sku: str
    quantity: int
    unit_price: str
    total: str
    status: str


def parse_money(value: object) -> Decimal:
    """Convert monetary input to cents precision without accepting floats."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError("Money must be supplied as a string, integer, or Decimal.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError("Invalid monetary amount.") from exc
    if not amount.is_finite() or amount < 0:
        raise ValidationError("Money must be finite and non-negative.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValidationError("Money cannot have more than two decimal places.")
    return amount


def validate_product(product: Product) -> None:
    if not product.sku.strip():
        raise ValidationError("SKU cannot be empty.")
    if not product.name.strip():
        raise ValidationError("Product name cannot be empty.")
    if product.unit_price < 0 or not product.unit_price.is_finite():
        raise ValidationError("Product price must be finite and non-negative.")
    if product.unit_price != product.unit_price.quantize(Decimal("0.01")):
        raise ValidationError("Product price must have at most two decimal places.")
    if isinstance(product.stock, bool) or product.stock < 0:
        raise ValidationError("Stock must be a non-negative integer.")
    if not isinstance(product.stock, int):
        raise ValidationError("Stock must be an integer.")


class Inventory:
    """In-memory inventory component used for fast isolated unit tests."""

    def __init__(self, products: Iterable[Product]) -> None:
        self._products: dict[str, Product] = {}
        for product in products:
            validate_product(product)
            if product.sku in self._products:
                raise ValidationError(f"Duplicate SKU: {product.sku}")
            self._products[product.sku] = product

    def get(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError as exc:
            raise ValidationError(f"Unknown SKU: {sku}") from exc

    def reserve(self, sku: str, quantity: int) -> Product:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValidationError("Quantity must be a positive integer.")
        product = self.get(sku)
        if product.stock < quantity:
            raise InsufficientInventory(
                f"Requested {quantity}, available {product.stock}."
            )
        updated = Product(
            product.sku,
            product.name,
            product.unit_price,
            product.stock - quantity,
        )
        self._products[sku] = updated
        return updated

    def snapshot(self) -> dict[str, int]:
        return {sku: product.stock for sku, product in self._products.items()}


class OrderService:
    """Business service with an injected inventory dependency."""

    def __init__(self, inventory: Inventory) -> None:
        self.inventory = inventory
        self.orders: dict[str, OrderResult] = {}

    def calculate_total(self, sku: str, quantity: int) -> Decimal:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValidationError("Quantity must be a positive integer.")
        product = self.inventory.get(sku)
        return (product.unit_price * quantity).quantize(Decimal("0.01"))

    def place_order(self, order_id: str, sku: str, quantity: int) -> OrderResult:
        if not order_id.strip():
            raise ValidationError("Order ID cannot be empty.")
        if order_id in self.orders:
            raise DuplicateOrder(order_id)

        product = self.inventory.get(sku)
        total = self.calculate_total(sku, quantity)

        # Reserve stock before recording the order. A database-backed system
        # must perform both operations in one transaction to ensure atomicity.
        self.inventory.reserve(sku, quantity)
        result = OrderResult(
            order_id=order_id,
            sku=sku,
            quantity=quantity,
            unit_price=f"{product.unit_price:.2f}",
            total=f"{total:.2f}",
            status="CONFIRMED",
        )
        self.orders[order_id] = result
        return result


class SQLiteOrderRepository:
    """Database adapter for integration tests."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                sku TEXT PRIMARY KEY,
                name TEXT NOT NULL CHECK (length(trim(name)) > 0),
                unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
                stock INTEGER NOT NULL CHECK (stock >= 0)
            );
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                sku TEXT NOT NULL REFERENCES products(sku),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                total NUMERIC NOT NULL CHECK (total >= 0),
                status TEXT NOT NULL CHECK (
                    status IN ('CONFIRMED', 'CANCELLED')
                )
            );
            """
        )

    def seed_product(self, product: Product) -> None:
        validate_product(product)
        self.connection.execute(
            "INSERT INTO products(sku, name, unit_price, stock) VALUES (?, ?, ?, ?)",
            (product.sku, product.name, str(product.unit_price), product.stock),
        )
        self.connection.commit()

    def place_order(self, order_id: str, sku: str, quantity: int) -> OrderResult:
        if not order_id.strip():
            raise ValidationError("Order ID cannot be empty.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValidationError("Quantity must be a positive integer.")

        try:
            with self.connection:
                product = self.connection.execute(
                    "SELECT name, unit_price, stock FROM products WHERE sku = ?",
                    (sku,),
                ).fetchone()
                if product is None:
                    raise ValidationError(f"Unknown SKU: {sku}")

                unit_price = Decimal(str(product[1])).quantize(Decimal("0.01"))
                if product[2] < quantity:
                    raise InsufficientInventory(
                        f"Requested {quantity}, available {product[2]}."
                    )
                total = (unit_price * quantity).quantize(Decimal("0.01"))

                cursor = self.connection.execute(
                    """
                    UPDATE products
                    SET stock = stock - ?
                    WHERE sku = ? AND stock >= ?
                    """,
                    (quantity, sku, quantity),
                )
                if cursor.rowcount != 1:
                    raise InsufficientInventory("Stock changed during reservation.")

                self.connection.execute(
                    """
                    INSERT INTO orders(order_id, sku, quantity, total, status)
                    VALUES (?, ?, ?, ?, 'CONFIRMED')
                    """,
                    (order_id, sku, quantity, str(total)),
                )
                return OrderResult(
                    order_id, sku, quantity, f"{unit_price:.2f}",
                    f"{total:.2f}", "CONFIRMED"
                )
        except sqlite3.IntegrityError as exc:
            # The context manager rolls back the inventory update if inserting
            # the order fails, including when the order ID is duplicated.
            if "orders.order_id" in str(exc) or "UNIQUE constraint failed" in str(exc):
                raise DuplicateOrder(order_id) from exc
            raise

    def get_stock(self, sku: str) -> int:
        row = self.connection.execute(
            "SELECT stock FROM products WHERE sku = ?", (sku,)
        ).fetchone()
        if row is None:
            raise ValidationError(f"Unknown SKU: {sku}")
        return int(row[0])


def build_inventory() -> Inventory:
    return Inventory(
        [
            Product("SSD-1TB", "1 TB solid-state drive", Decimal("89.99"), 12),
            Product("RAM-16G", "16 GB memory module", Decimal("42.50"), 20),
            Product("DOCK-USB", "USB-C docking station", Decimal("119.00"), 4),
        ]
    )


def run_unit_examples() -> None:
    print("\n=== Unit testing: isolated business rules ===")
    service = OrderService(build_inventory())
    assert service.calculate_total("SSD-1TB", 3) == Decimal("269.97")
    assert service.calculate_total("RAM-16G", 2) == Decimal("85.00")

    try:
        service.calculate_total("SSD-1TB", 0)
    except ValidationError:
        print("PASS: zero quantity rejected")
    else:
        raise AssertionError("Zero quantity should be rejected.")

    try:
        service.calculate_total("MISSING", 1)
    except ValidationError:
        print("PASS: unknown SKU rejected")
    else:
        raise AssertionError("Unknown SKU should be rejected.")

    print("PASS: exact decimal totals and input validation")


def run_integration_examples() -> None:
    print("\n=== Integration testing: service and relational database ===")
    with tempfile.TemporaryDirectory() as directory:
        database_path = Path(directory) / "orders.sqlite3"
        connection = sqlite3.connect(database_path)
        repository = SQLiteOrderRepository(connection)
        repository.seed_product(
            Product("SSD-1TB", "1 TB solid-state drive", Decimal("89.99"), 5)
        )

        order = repository.place_order("ORDER-1001", "SSD-1TB", 2)
        assert order.total == "179.98"
        assert repository.get_stock("SSD-1TB") == 3

        try:
            repository.place_order("ORDER-1002", "SSD-1TB", 9)
        except InsufficientInventory:
            assert repository.get_stock("SSD-1TB") == 3
            print("PASS: insufficient inventory rolls back without stock changes")
        else:
            raise AssertionError("Overselling must fail.")

        try:
            repository.place_order("ORDER-1001", "SSD-1TB", 1)
        except DuplicateOrder:
            assert repository.get_stock("SSD-1TB") == 3
            print("PASS: duplicate order leaves inventory unchanged")
        else:
            raise AssertionError("Duplicate order must fail.")

        connection.close()


def create_health_handler() -> type[BaseHTTPRequestHandler]:
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/health":
                body = json.dumps(
                    {"status": "ok", "service": "order-service"}
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/ready":
                body = b'{"status":"ready"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                body = b'{"error":"not_found"}'
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, format_string: str, *args: object) -> None:
            LOGGER.debug(format_string, *args)

    return HealthHandler


def run_smoke_examples() -> None:
    print("\n=== Smoke testing: deployed-service essentials ===")
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_health_handler())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        for endpoint in ("/health", "/ready"):
            with urllib.request.urlopen(base_url + endpoint, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                assert response.status == 200
                assert payload["status"] in {"ok", "ready"}
                print(f"PASS: GET {endpoint} returned healthy response")

        try:
            urllib.request.urlopen(base_url + "/missing", timeout=2)
        except urllib.error.HTTPError as error:
            assert error.code == 404
            print("PASS: unknown route returns HTTP 404")
        else:
            raise AssertionError("Unknown route should return HTTP 404.")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class OrderRegressionTests(unittest.TestCase):
    """Stable tests for business behavior that must not regress."""

    def setUp(self) -> None:
        self.inventory = build_inventory()
        self.service = OrderService(self.inventory)

    def test_expected_total(self) -> None:
        self.assertEqual(
            self.service.calculate_total("SSD-1TB", 3), Decimal("269.97")
        )

    def test_order_reserves_inventory(self) -> None:
        order = self.service.place_order("REG-1", "RAM-16G", 4)
        self.assertEqual(order.total, "170.00")
        self.assertEqual(self.inventory.get("RAM-16G").stock, 16)

    def test_failed_order_does_not_change_stock(self) -> None:
        before = self.inventory.snapshot()
        with self.assertRaises(InsufficientInventory):
            self.service.place_order("REG-2", "DOCK-USB", 99)
        self.assertEqual(self.inventory.snapshot(), before)

    def test_duplicate_order_does_not_reserve_twice(self) -> None:
        self.service.place_order("REG-3", "RAM-16G", 2)
        before = self.inventory.snapshot()
        with self.assertRaises(DuplicateOrder):
            self.service.place_order("REG-3", "RAM-16G", 2)
        self.assertEqual(self.inventory.snapshot(), before)

    def test_invalid_quantity(self) -> None:
        for quantity in (0, -1, True, 1.5):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValidationError):
                    self.service.calculate_total("SSD-1TB", quantity)  # type: ignore[arg-type]

    def test_unknown_product(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.place_order("REG-4", "UNKNOWN", 1)

    def test_money_precision(self) -> None:
        self.assertEqual(parse_money("19.95"), Decimal("19.95"))
        with self.assertRaises(ValidationError):
            parse_money("19.999")
        with self.assertRaises(ValidationError):
            parse_money(float("nan"))


def run_regression_tests() -> dict[str, object]:
    print("\n=== Regression testing: repeatable behavior checks ===")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OrderRegressionTests)
    result = unittest.TestResult()
    started = time.perf_counter()
    suite.run(result)
    duration = time.perf_counter() - started

    for test, traceback in result.failures:
        print(f"FAIL: {test}\n{traceback}")
    for test, traceback in result.errors:
        print(f"ERROR: {test}\n{traceback}")

    report = {
        "run": result.testsRun,
        "passed": result.testsRun - len(result.failures) - len(result.errors),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "duration_seconds": round(duration, 6),
        "failure_details": [
            {"test": str(test), "traceback": traceback}
            for test, traceback in result.failures
        ],
        "error_details": [
            {"test": str(test), "traceback": traceback}
            for test, traceback in result.errors
        ],
    }
    print(json.dumps(report, indent=2))
    return report


def write_json_report(report: dict[str, object]) -> Path:
    """Write a machine-readable report suitable for a CI artifact."""
    output = Path(os.environ.get("TEST_REPORT_PATH", "test-report.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()
    return output


def main() -> int:
    run_unit_examples()
    run_integration_examples()
    run_smoke_examples()
    report = run_regression_tests()
    report_path = write_json_report(report)
    print(f"\nJSON test report written to: {report_path.resolve()}")
    return 1 if report["failures"] or report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
