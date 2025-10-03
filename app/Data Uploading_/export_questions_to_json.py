import sqlite3
import json

conn = sqlite3.connect('exampad.db')
cursor = conn.cursor()

cursor.execute("SELECT question_text, options, correct_answer, explanation FROM question")
rows = cursor.fetchall()

questions = []
for row in rows:
    questions.append({
        "question_text": row[0],
        "options": row[1],
        "correct_answer": row[2],
        "explanation": row[3]
    })

with open("questions_export.json", "w", encoding="utf-8") as f:
    json.dump(questions, f, ensure_ascii=False, indent=2)

conn.close()
print("Exported questions to questions_export.json")
