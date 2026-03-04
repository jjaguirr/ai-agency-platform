#!/usr/bin/env python3
"""Seed development database with sample data."""
import json
import psycopg2
from psycopg2.extras import Json


SAMPLE_CUSTOMERS = [
    {
        "customer_id": "demo_jewelry",
        "business_context": {
            "business_name": "Sparkle & Shine Jewelry",
            "business_type": "e-commerce",
            "industry": "jewelry",
            "pain_points": ["manual social media", "invoice creation"],
        },
    },
    {
        "customer_id": "demo_consulting",
        "business_context": {
            "business_name": "Strategic Solutions Consulting",
            "business_type": "professional services",
            "industry": "consulting",
            "pain_points": ["manual reports", "client follow-up"],
        },
    },
]


def seed_database(conn_string: str = "postgresql://mcphub:mcphub_password@localhost:5432/mcphub"):
    """Insert sample customer data."""
    conn = psycopg2.connect(conn_string)
    try:
        with conn.cursor() as cur:
            for customer in SAMPLE_CUSTOMERS:
                cur.execute(
                    """INSERT INTO customer_business_context (customer_id, business_context)
                       VALUES (%s, %s)
                       ON CONFLICT (customer_id) DO UPDATE SET business_context = EXCLUDED.business_context""",
                    (customer["customer_id"], Json(customer["business_context"])),
                )
        conn.commit()
        print(f"Seeded {len(SAMPLE_CUSTOMERS)} customers.")
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()
