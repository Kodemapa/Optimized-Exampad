import sqlite3

# Connect to the database
conn = sqlite3.connect('exampad.db')
cursor = conn.cursor()

# Update correct_answer values
cursor.execute("UPDATE question SET correct_answer = 'A' WHERE correct_answer = '1';")
cursor.execute("UPDATE question SET correct_answer = 'B' WHERE correct_answer = '2';")
cursor.execute("UPDATE question SET correct_answer = 'C' WHERE correct_answer = '3';")
cursor.execute("UPDATE question SET correct_answer = 'D' WHERE correct_answer = '4';")

# Commit changes and close connection
conn.commit()
conn.close()

print("Correct answers updated successfully.")
