# Script to migrate questions for 'Biological Classification' and 'Plant Kingdom' to their new top-level topics
# Run this with: python scripts/migrate_xi_bio_super_topic_questions.py

import os
import sys
import json
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from app.models import db, Subject, Topic, Question

BIOLOGY_XI_SUBJECT_ID = 5
TOPIC_FILES = {
    "Biological Classification": [
        "responseBody/Diversity_in_Living_World_Biological_Classification_(Easy).json",
        "responseBody/Diversity_in_Living_World_Biological_Classification_(Moderate).json",
        "responseBody/Diversity_in_Living_World_Biological_Classification_(Difficult).json"
    ],
    "Plant Kingdom": [
        "responseBody/Diversity_in_Living_World_Plant_Kingdom_(Easy).json",
        "responseBody/Diversity_in_Living_World_Plant_Kingdom_(Moderate).json",
        "responseBody/Diversity_in_Living_World_Plant_Kingdom_(Difficult).json"
    ]
}

app = create_app()

def load_questions_from_file(filepath):
    with open(filepath, encoding='utf-8') as f:
        data = json.load(f)
        # Extract questions from the nested structure
        try:
            questions = data["result"]["data"][0]["sec_details"][0]["sec_questions"]
        except (KeyError, IndexError, TypeError):
            print(f"Could not extract questions from {filepath}")
            return []
        return questions

with app.app_context():
    for topic_name, file_list in TOPIC_FILES.items():
        topic = Topic.query.filter_by(subject_id=BIOLOGY_XI_SUBJECT_ID, name=topic_name).first()
        if not topic:
            print(f"Topic '{topic_name}' not found, skipping.")
            continue
        for file_path in file_list:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue
            questions = load_questions_from_file(file_path)
            for q in questions:
                # Extract fields from the nested structure
                qid = q.get('qid')
                que_obj = q.get('que', {})
                # Usually the question text and options are under que['1']
                que_data = que_obj.get('1', {}) if isinstance(que_obj, dict) else {}
                text = que_data.get('q_string', '')
                options = que_data.get('q_option', [])
                # No direct correct_answer in this structure; set to None or handle if available
                correct_answer = None
                existing = Question.query.filter_by(qid=qid).first()
                if existing:
                    if existing.topic_id != topic.id:
                        existing.topic_id = topic.id
                        print(f"Updated topic for question {existing.qid}")
                else:
                    question = Question(
                        qid=qid,
                        text=text,
                        options=options,
                        correct_answer=correct_answer,
                        topic_id=topic.id,
                        subject_id=BIOLOGY_XI_SUBJECT_ID
                    )
                    db.session.add(question)
            print(f"Processed {len(questions)} questions for {topic_name} from {file_path}")
    db.session.commit()
    print("Done.")
