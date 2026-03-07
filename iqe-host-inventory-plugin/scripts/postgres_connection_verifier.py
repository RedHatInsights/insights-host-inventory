import sys

import psycopg2

try:
    conn = psycopg2.connect(user="insights", host="postgreshost", password="insights")
except psycopg2.Error:
    print("Could not connect to postgres")
    sys.exit(1)

print("Database connection successful")
