from sqlalchemy import inspect

from database import get_engine


def print_schema():
    inspector = inspect(get_engine())
    tables = inspector.get_table_names()
    print("Tables in database:")
    print(tables)

    for table in tables:
        print(f"\nTable: {table}")
        for column in inspector.get_columns(table):
            print(f"  {column['name']} -> {column['type']}")


if __name__ == "__main__":
    print_schema()
