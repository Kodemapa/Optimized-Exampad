import os
import sys
import json
# Ensure project root is in sys.path so 'app' can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import db, create_app
from app.models import Subject, Topic, Question

app = create_app()
with app.app_context():
    # Load new questions
    with open(os.path.join('New folder', 'solutions.json'), 'r', encoding='utf-8') as f:
        data = json.load(f)
    new_questions = data['result']['data']['sec_questions']

    # Find Class XI Chemistry subject
    subject = Subject.query.filter_by(name='Chemistry', class_level='XI').first()
    if not subject:
        raise Exception("Class XI Chemistry subject not found.")

    # Find Thermodynamics topic
    topic = Topic.query.filter_by(name='Thermodynamics', subject_id=subject.id).first()
    if not topic:
        raise Exception("Thermodynamics topic not found.")

    # Delete existing questions for this topic
    old_questions = Question.query.filter_by(topic_id=topic.id).all()
    for q in old_questions:
        db.session.delete(q)
    db.session.commit()

    # Insert or update new questions
    for q in new_questions:
        qid = q[12] if len(q) > 12 else None
        question_text = q[2]
        options = q[3]
        # Store correct_answer as letter (A/B/C/D) instead of number
        correct_answer = ['A', 'B', 'C', 'D'][q[4][0]] if q[4] else None
        explanation = q[6]
        difficulty_level = 'moderate'
        max_marks = 1

        # Check if question with same qid exists (shouldn't, but safe)
        existing = Question.query.filter_by(qid=qid).first()
        if existing:
            # Update existing question
            existing.question_text = question_text
            existing.options = json.dumps(options)
            existing.correct_answer = correct_answer
            existing.explanation = explanation
            existing.difficulty_level = difficulty_level
            existing.max_marks = max_marks
            existing.topic_id = topic.id
        else:
            # Insert new question
            question = Question(
                qid=qid,
                question_text=question_text,
                options=json.dumps(options),
                correct_answer=correct_answer,
                explanation=explanation,
                difficulty_level=difficulty_level,
                max_marks=max_marks,
                topic_id=topic.id
            )
            db.session.add(question)

    db.session.commit()
    print("Thermodynamics questions replaced successfully.")