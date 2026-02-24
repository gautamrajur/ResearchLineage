"""Create airflow database in GCP."""
import psycopg2

# Connect to default database
conn = psycopg2.connect(
    host="127.0.0.1",
    port=5432,
    database="researchlineage",
    user="shivram",
    password="shivram",
)

# Must set autocommit for CREATE DATABASE
conn.autocommit = True

cursor = conn.cursor()

try:
    cursor.execute("CREATE DATABASE airflow")
    print("Airflow database created successfully!")
except Exception as e:
    print(f"Error: {e}")
    print("(Database might already exist)")
finally:
    cursor.close()
    conn.close()
