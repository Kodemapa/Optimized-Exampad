# Script to add 'Biological Classification' and 'Plant Kingdom' as top-level topics for Class XI Biology
# Run this with: python scripts/add_xi_bio_super_topics.py

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from app.models import db, Subject, Topic

BIOLOGY_XI_SUBJECT_ID = 5
NEW_TOPICS = [
    "Biological Classification",
    "Plant Kingdom"
]

app = create_app()

with app.app_context():
    subject = Subject.query.get(BIOLOGY_XI_SUBJECT_ID)
    if not subject:
        print(f"Biology subject with id {BIOLOGY_XI_SUBJECT_ID} not found.")
        sys.exit(1)
    for topic_name in NEW_TOPICS:
        topic = Topic.query.filter_by(subject_id=BIOLOGY_XI_SUBJECT_ID, name=topic_name).first()
        if topic:
            print(f"Topic '{topic_name}' already exists (id={topic.id})")
        else:
            topic = Topic(name=topic_name, subject_id=BIOLOGY_XI_SUBJECT_ID)
            db.session.add(topic)
            print(f"Added topic '{topic_name}' as top-level topic.")
    db.session.commit()
    print("Done.")
