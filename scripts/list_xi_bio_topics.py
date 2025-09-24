import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app
from app.models import Subject, Topic, Question

def main():
    app = create_app()
    with app.app_context():
        subject = Subject.query.filter_by(name='Biology', class_level='XI').first()
        if not subject:
            print('Class XI Biology subject not found.')
            return
        print(f"Class XI Biology subject_id: {subject.id}")
        topics = Topic.query.filter_by(subject_id=subject.id).all()
        print(f"Topics for Class XI Biology:")
        for t in topics:
            q_count = Question.query.filter_by(topic_id=t.id).count()
            print(f"- {t.name} (id={t.id}) | Questions: {q_count}")

if __name__ == "__main__":
    main()
