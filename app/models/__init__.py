"""
Database Models for KODEMAPA-EXAMPAD
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json

# Initialize db here to avoid circular imports
db = SQLAlchemy()

class User(UserMixin, db.Model):
    """User model for authentication"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), default='student')  # student, teacher, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    exam_sessions = db.relationship('ExamSession', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Subject(db.Model):
    """Subject model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    class_level = db.Column(db.String(10), nullable=False)  # XI, XII
    description = db.Column(db.Text)
    
    # Relationships
    topics = db.relationship('Topic', backref='subject', lazy='dynamic')
    
    def __repr__(self):
        return f'<Subject {self.name}>'

class Topic(db.Model):
    """Topic model"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    description = db.Column(db.Text)
    question_count = db.Column(db.Integer, default=0)
    
    # Relationships
    questions = db.relationship('Question', backref='topic', lazy='dynamic')
    
    def __repr__(self):
        return f'<Topic {self.name}>'

class Question(db.Model):
    """Question model"""
    id = db.Column(db.Integer, primary_key=True)
    qid = db.Column(db.String(100), unique=True, nullable=False)  # From JSON data
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text)  # JSON string of options
    correct_answer = db.Column(db.String(10))
    explanation = db.Column(db.Text)  # Solution explanation
    difficulty_level = db.Column(db.String(20), default='moderate')
    max_marks = db.Column(db.Integer, default=1)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_options(self):
        """Get options as list"""
        return json.loads(self.options) if self.options else []
    
    def set_options(self, options_list):
        """Set options from list"""
        self.options = json.dumps(options_list)
    
    def __repr__(self):
        return f'<Question {self.qid}>'

class Exam(db.Model):
    """Exam configuration model"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'))  # Optional, for topic-specific exams
    question_count = db.Column(db.Integer, default=15)
    duration_minutes = db.Column(db.Integer, default=30)
    difficulty_mix = db.Column(db.Text)  # JSON: {"easy": 40, "moderate": 40, "difficult": 20}
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    subject = db.relationship('Subject', backref='exams')
    topic = db.relationship('Topic', backref='exams')
    creator = db.relationship('User', backref='created_exams')
    sessions = db.relationship('ExamSession', backref='exam', lazy='dynamic')
    
    def get_difficulty_mix(self):
        """Get difficulty mix as dict"""
        return json.loads(self.difficulty_mix) if self.difficulty_mix else {"easy": 33, "moderate": 34, "difficult": 33}
    
    def set_difficulty_mix(self, mix_dict):
        """Set difficulty mix from dict"""
        self.difficulty_mix = json.dumps(mix_dict)
    
    def __repr__(self):
        return f'<Exam {self.title}>'

class ExamSession(db.Model):
    """Exam session model - tracks individual exam attempts"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=True)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)
    score = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=0.0)
    percentage = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed, timeout
    questions_data = db.Column(db.Text)  # JSON of questions and answers
    
    def get_questions_data(self):
        """Get questions data as dict"""
        if not self.questions_data:
            return {}
            
        try:
            return json.loads(self.questions_data)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for session {self.id}: {str(e)}")
            return {}
    
    def set_questions_data(self, data):
        """Set questions data from dict"""
        self.questions_data = json.dumps(data)
    
    def calculate_score(self):
        """Calculate and update score based on answers, using positive/negative marks if available"""
        data = self.get_questions_data()
        questions = data.get('questions', [])
        # Default marking scheme
        positive = 1
        negative = 0
        # Try to get from custom test if available
        if self.exam and hasattr(self.exam, 'custom_test') and self.exam.custom_test:
            if hasattr(self.exam.custom_test, 'positive_marks'):
                positive = self.exam.custom_test.positive_marks or 1
            if hasattr(self.exam.custom_test, 'negative_marks'):
                negative = self.exam.custom_test.negative_marks or 0
        # Calculate score
        score = 0
        for q in questions:
            if q.get('is_correct', False):
                score += positive
            elif q.get('user_answer'):
                score -= negative
        max_score = len(questions) * positive
        self.score = score
        self.max_score = max_score
        self.percentage = (score / max_score * 100) if max_score > 0 else 0
        return self.percentage
    
    def __repr__(self):
        exam_title = self.exam.title if self.exam else "Practice Test"
        return f'<ExamSession {self.id}: {self.user.username} - {exam_title}>'
    
class StudentClass(db.Model):
    """Table to store class (XI or XII) for each student"""
    student_class_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    class_level = db.Column(db.String(10), nullable=False)  # Values: XI or XII

    # Relationship
    user = db.relationship('User', backref=db.backref('student_class', uselist=False))

    def __repr__(self):
        return f"<StudentClass {self.user.username} - {self.class_level}>"

    

class CustomTest(db.Model):
    """Custom test lifecycle and metadata table"""
    __tablename__ = 'customTests'

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_by_username = db.Column(db.String(80), nullable=False)
    started_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='active')  # scheduled, active, closed
    number_of_students_taken = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    positive_marks = db.Column(db.Integer, default=1)
    negative_marks = db.Column(db.Integer, default=0)
    # Stores configuration details including ordered_question_ids, class/subject, duration, etc.
    details_json = db.Column(db.Text)

    # Relationships
    creator = db.relationship('User', backref=db.backref('custom_tests', lazy='dynamic'), foreign_keys=[created_by_user_id])
    exam = db.relationship('Exam', backref=db.backref('custom_test', uselist=False))

    def __repr__(self):
        return f"<CustomTest {self.id} status={self.status}>"


class SuperAdmin(db.Model):
    """Optional table to store additional metadata for super admin users."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    privileges = db.Column(db.Text)  # JSON or comma-separated privileges (optional)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship
    user = db.relationship('User', backref=db.backref('superadmin_profile', uselist=False))

    def __repr__(self):
        return f"<SuperAdmin user_id={self.user_id}>"


class SiteSetting(db.Model):
    """Simple key/value store for site-wide settings (e.g., ui_theme)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)

    @classmethod
    def get(cls, name, default=None):
        s = cls.query.filter_by(name=name).first()
        return s.value if s else default

    @classmethod
    def set(cls, name, value):
        s = cls.query.filter_by(name=name).first()
        if s:
            s.value = value
        else:
            s = cls(name=name, value=value)
            db.session.add(s)
        db.session.commit()

    def __repr__(self):
        return f"<SiteSetting {self.name}={self.value}>"

