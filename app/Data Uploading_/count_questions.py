import sqlite3

DB_PATH = 'exampad.db'

def count_questions_in_topic(topic_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM question WHERE topic_id = ?', (topic_id,))
        count = cursor.fetchone()[0]
        print(f"Number of questions in topic ID {topic_id}: {count}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    topic_id = input("Enter the topic ID: ")
    count_questions_in_topic(topic_id)
