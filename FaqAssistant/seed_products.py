"""Run once to populate products and purchases collections in Firestore.

Usage:
    python seed_products.py
"""
from dotenv import load_dotenv
load_dotenv()

from firebase_db import db

PRODUCTS = {
    "prod_001": {
        "name": "SmartBudget Pro",
        "category": "Personal Finance App",
        "price": "$9.99/month",
        "description": "AI-powered budgeting tool with automatic expense categorization.",
        "features": "Expense tracking, budget goals, monthly reports, bank sync",
        "support_email": "support-pro@smartbudget.com",
    },
    "prod_002": {
        "name": "SmartBudget Basic",
        "category": "Personal Finance App",
        "price": "Free",
        "description": "Simple manual expense tracker for individuals.",
        "features": "Manual expense entry, basic charts, up to 3 budget categories",
        "support_email": "support@smartbudget.com",
    },
    "prod_003": {
        "name": "SmartBudget Family",
        "category": "Personal Finance App",
        "price": "$14.99/month",
        "description": "Shared budgeting for households — up to 5 members.",
        "features": "Shared wallets, per-member spending limits, family goals, bank sync",
        "support_email": "support-family@smartbudget.com",
    },
    "prod_004": {
        "name": "SmartBudget Business",
        "category": "Business Finance App",
        "price": "$29.99/month",
        "description": "Expense management and invoicing for small businesses.",
        "features": "Invoice generation, VAT tracking, team accounts, accounting export",
        "support_email": "support-biz@smartbudget.com",
    },
    "prod_005": {
        "name": "SmartBudget Student",
        "category": "Personal Finance App",
        "price": "$2.99/month",
        "description": "Lightweight budgeting designed for students on a tight budget.",
        "features": "Spending alerts, semester budget planner, scholarship tracker",
        "support_email": "support-student@smartbudget.com",
    },
}


# Sample purchase records keyed by client_id.
# Each client has a list of product_ids they have purchased.
PURCHASES = {
    "client_001": {"product_ids": ["prod_001", "prod_003"]},
    "client_002": {"product_ids": ["prod_002"]},
    "client_003": {"product_ids": ["prod_004"]},
    "client_004": {"product_ids": ["prod_002", "prod_005"]},
    "client_005": {"product_ids": ["prod_001", "prod_002", "prod_004"]},
}


def seed():
    print("Seeding products...")
    for product_id, data in PRODUCTS.items():
        db.collection("products").document(product_id).set(data)
        print(f"  {product_id}: {data['name']}")

    print("Seeding purchases...")
    for client_id, data in PURCHASES.items():
        db.collection("purchases").document(client_id).set(data)
        names = ", ".join(data["product_ids"])
        print(f"  {client_id}: {names}")

    print("Done.")


if __name__ == "__main__":
    seed()
