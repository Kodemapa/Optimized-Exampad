from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import json
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DB_PATH = 'exampad.db'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    return sqlite3.connect(DB_PATH)

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db()
    subjects = conn.execute('SELECT id, name FROM subject').fetchall()
    # Fixed Class XI subjects
    xi_names = ['mathematics', 'physics', 'chemistry', 'biology']
    xi_subjects = []
    xii_subjects = []
    xi_ids = set()
    # Place Class XI subjects in fixed order
    for name in xi_names:
        for subject in subjects:
            if subject[1].strip().lower() == name:
                xi_subjects.append(subject)
                xi_ids.add(subject[0])
                break
    # All other subjects go to Class XII
    for subject in subjects:
        if subject[0] not in xi_ids:
            xii_subjects.append(subject)
    # Get topics for each subject
    subject_topics = {}
    for subject in subjects:
        topic_list = conn.execute('SELECT id, name FROM topic WHERE subject_id=?', (subject[0],)).fetchall()
        subject_topics[subject[0]] = topic_list
    conn.close()
    return render_template('index.html', subjects=subjects, subject_topics=subject_topics, xi_subjects=xi_subjects, xii_subjects=xii_subjects)

@app.route('/topics/<int:subject_id>')
def topics(subject_id):
    conn = get_db()
    topics = conn.execute('SELECT id, name FROM topic WHERE subject_id=?', (subject_id,)).fetchall()
    conn.close()
    return jsonify({'topics': topics})

@app.route('/upload', methods=['POST'])
def upload():
    try:
        files = request.files.getlist('jsonfile')  # Get list of files
        subject_id = request.form['subject']
        topic_id = request.form.get('topic')
        new_topic = request.form.get('new_topic')

        if not files or all(file.filename == '' for file in files):
            flash('No files selected!')
            return redirect(url_for('index'))

        # Add new topic if provided
        if new_topic:
            conn = get_db()
            conn.execute('INSERT INTO topic (name, subject_id) VALUES (?, ?)', (new_topic, subject_id))
            topic_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
            conn.close()

        # Get topic and subject names for the success message
        conn = get_db()
        topic_subject_result = conn.execute(
            'SELECT t.name, s.name FROM topic t JOIN subject s ON t.subject_id = s.id WHERE t.id = ?', 
            (topic_id,)
        ).fetchone()
        if topic_subject_result:
            topic_name, subject_name = topic_subject_result
        else:
            topic_name, subject_name = "Unknown Topic", "Unknown Subject"
        conn.close()

        total_questions_added = 0
        processed_files = 0
        failed_files = []

        # Process each file
        for file in files:
            if file.filename == '':
                continue
                
            try:
                # Save and parse JSON
                filepath = os.path.join(UPLOAD_FOLDER, file.filename)
                file.save(filepath)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Debug: Print JSON structure
                print(f"Processing {file.filename}")
                print(f"JSON keys: {list(data.keys())}")
                
                # Try different JSON structures
                questions = None
                if 'result' in data and 'data' in data['result'] and 'sec_questions' in data['result']['data']:
                    questions = data['result']['data']['sec_questions']
                    print(f"Found questions in result.data.sec_questions: {len(questions)} items")
                elif 'sec_questions' in data:
                    questions = data['sec_questions']
                    print(f"Found questions in sec_questions: {len(questions)} items")
                elif 'questions' in data:
                    questions = data['questions']
                    print(f"Found questions in questions: {len(questions)} items")
                elif isinstance(data, list):
                    questions = data
                    print(f"JSON is a list with {len(questions)} items")
                else:
                    print(f"Unable to find questions in JSON structure: {data.keys() if isinstance(data, dict) else type(data)}")
                    questions = []

                # Safety check
                if questions is None:
                    questions = []

                # Insert questions
                conn = get_db()
                questions_added = 0
                
                print(f"Starting to process {len(questions)} questions from {file.filename}")
                
                for i, q in enumerate(questions):
                    if not q or len(q) < 3 or not q[2]: 
                        print(f"Skipping question {i+1}: Invalid structure or empty question text")
                        print(f"Question data: {q}")
                        continue
                    
                    question_text = q[2]
                    options = json.dumps(q[3]) if len(q) > 3 and q[3] else None
                    
                    # Handle correct_answer safely - check if it's an integer before adding 1
                    correct_answer = None
                    if len(q) > 4 and q[4] and len(q[4]) > 0:
                        try:
                            # Try to convert to integer first, then add 1
                            answer_index = int(q[4][0])
                            correct_answer = str(answer_index + 1)
                        except (ValueError, TypeError):
                            # If conversion fails, use the value as is
                            correct_answer = str(q[4][0])
                    
                    explanation = q[6] if len(q) > 6 and q[6] else None
                    
                    # Generate a more unique qid with timestamp
                    import time
                    timestamp = str(int(time.time() * 1000))  # milliseconds timestamp
                    base_filename = os.path.splitext(file.filename)[0]  # remove .json extension
                    qid = f"{base_filename}_{i+1}_{timestamp}"
                    
                    # Check if qid already exists and make it unique
                    original_qid = qid
                    counter = 1
                    while True:
                        existing = conn.execute('SELECT COUNT(*) FROM question WHERE qid = ?', (qid,)).fetchone()[0]
                        if existing == 0:
                            break
                        qid = f"{original_qid}_{counter}"
                        counter += 1
                    
                    try:
                        conn.execute(
                            'INSERT INTO question (qid, question_text, options, correct_answer, explanation, topic_id, created_at) VALUES (?, ?, ?, ?, ?, ?, datetime("now"))',
                            (qid, question_text, options, correct_answer, explanation, topic_id)
                        )
                        questions_added += 1
                        print(f"Successfully inserted question {i+1} from {file.filename} with qid: {qid}")
                    except sqlite3.IntegrityError as e:
                        print(f"Error inserting question {i+1} from {file.filename}: {e}")
                        print(f"Question text preview: {question_text[:100]}...")
                        continue
                
                conn.commit()
                conn.close()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                total_questions_added += questions_added
                processed_files += 1
                print(f"Processed {file.filename}: {questions_added} questions added")
                
            except Exception as e:
                failed_files.append(f"{file.filename}: {str(e)}")
                print(f"Error processing {file.filename}: {str(e)}")
                # Clean up file if it exists
                if os.path.exists(filepath):
                    os.remove(filepath)

        # Create success/error message
        if processed_files > 0:
            message = f'Successfully processed {processed_files} file(s) and added {total_questions_added} questions to "{topic_name}" under "{subject_name}" subject!'
            if failed_files:
                message += f' Failed files: {", ".join(failed_files)}'
            flash(message)
        else:
            flash(f'Failed to process any files. Errors: {", ".join(failed_files)}')
        
    except Exception as e:
        flash(f'Error processing files: {str(e)}')
    
    return redirect(url_for('index'))


# Route to delete a subject
@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
def delete_subject(subject_id):
    try:
        conn = get_db()
        # Delete all topics and questions under this subject
        topic_ids = [row[0] for row in conn.execute('SELECT id FROM topic WHERE subject_id=?', (subject_id,)).fetchall()]
        for tid in topic_ids:
            conn.execute('DELETE FROM question WHERE topic_id=?', (tid,))
        conn.execute('DELETE FROM topic WHERE subject_id=?', (subject_id,))
        conn.execute('DELETE FROM subject WHERE id=?', (subject_id,))
        conn.commit()
        conn.close()
        flash('Subject deleted successfully!')
    except Exception as e:
        flash(f'Error deleting subject: {str(e)}')
    return redirect(url_for('index'))

# Route to delete a topic
@app.route('/delete_topic/<int:topic_id>', methods=['POST'])
def delete_topic(topic_id):
    try:
        conn = get_db()
        conn.execute('DELETE FROM question WHERE topic_id=?', (topic_id,))
        conn.execute('DELETE FROM topic WHERE id=?', (topic_id,))
        conn.commit()
        conn.close()
        flash('Topic deleted successfully!')
    except Exception as e:
        flash(f'Error deleting topic: {str(e)}')
    return redirect(url_for('index'))

# Route to edit a topic name
@app.route('/edit_topic/<int:topic_id>', methods=['POST'])
def edit_topic(topic_id):
    new_name = request.form.get('new_name')
    if not new_name:
        flash('No new name provided for topic!')
        return redirect(url_for('index'))
    try:
        conn = get_db()
        conn.execute('UPDATE topic SET name=? WHERE id=?', (new_name, topic_id))
        conn.commit()
        conn.close()
        flash('Topic name updated successfully!')
    except Exception as e:
        flash(f'Error editing topic: {str(e)}')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)