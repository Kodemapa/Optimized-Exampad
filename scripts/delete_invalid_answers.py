import sqlite3

# Connect to the database
conn = sqlite3.connect('exampad.db')
cursor = conn.cursor()

# Delete rows where correct_answer is a number greater than 4
cursor.execute("DELETE FROM question WHERE CAST(correct_answer AS INTEGER) > 4;")

# Commit changes and close connection
conn.commit()
conn.close()

print("Rows with correct_answer > 4 deleted successfully.")
