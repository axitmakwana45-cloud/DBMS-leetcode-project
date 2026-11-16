
from sqlalchemy import text
from database import engine, refresh_metadata


def test_database_connection():
    try:
        print("\nTesting PostgreSQL Connection...")

        # Test 1: Database connection
        with engine.connect() as connection:
            print("[PASS] Database connection successful")

            # Test 2: PostgreSQL version
            result = connection.execute(
                text("SELECT version();")
            )

            version = result.fetchone()[0]

            print("\nPostgreSQL Version:")
            print(version)

        # Test 3: Metadata reflection
        print("\nTesting Metadata Reflection...")

        metadata = refresh_metadata()

        print("[PASS] Metadata reflection successful")

        # Test 4: Display available tables
        print("\nAvailable Database Tables:")

        if metadata.tables:
            for table_name in metadata.tables.keys():
                print(f"- {table_name}")
        else:
            print("No tables found in database.")

        # Test 5: Metadata cache
        print("\nTesting Metadata Cache...")

        first_metadata = refresh_metadata()
        second_metadata = refresh_metadata()

        if first_metadata is second_metadata:
            print("[PASS] Metadata cache is working")
        else:
            print("[FAIL] Metadata cache test failed")

        print("\nAll database tests completed.")

    except Exception as error:
        print("\n[FAIL] Database test failed")
        print("Error:", error)

    finally:
        engine.dispose()


if __name__ == "__main__":
    test_database_connection()
