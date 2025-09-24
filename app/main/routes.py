"""
Main Blueprint Routes - Dashboard and home pages
"""

from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.main import bp
from app.models import Subject, Topic, Question
from app.main.student_class_utils import get_student_class

@bp.route('/')
def index():
    """Landing page - redirects based on authentication status"""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('auth.login'))


from app.models import StudentClass, db

@bp.route('/dashboard')
@login_required
def dashboard():
    # Get some statistics
    total_subjects = Subject.query.count()
    total_topics = Topic.query.count()
    total_questions = Question.query.count()

    class_xi_subjects = Subject.query.filter_by(class_level='XI').limit(6).all()
    class_xii_subjects = Subject.query.filter_by(class_level='XII').limit(6).all()

    # Check if current user is student and has not chosen a class yet
    show_class_popup = False
    if getattr(current_user, 'role', None) == 'student':
        existing = StudentClass.query.filter_by(user_id=current_user.id).first()
        if not existing:
            show_class_popup = True

    student_class = None
    if getattr(current_user, 'role', None) == 'student':
        student_class = get_student_class(current_user.id)
    # If teacher, include recent custom tests created by them
    teacher_custom_tests = []
    if getattr(current_user, 'role', None) == 'teacher':
        try:
            from app.models import CustomTest, Exam
            custom_tests = CustomTest.query.filter_by(created_by_user_id=current_user.id).order_by(CustomTest.created_at.desc()).limit(5).all()
            for ct in custom_tests:
                exam = Exam.query.get(ct.exam_id) if ct.exam_id else None
                teacher_custom_tests.append({
                    'exam_id': exam.id if exam else None,
                    'title': exam.title if exam else f'Custom Test #{ct.id}',
                    'created_at': ct.created_at,
                    'status': ct.status
                })
        except Exception:
            pass

    return render_template(
        'main/dashboard.html',
        total_subjects=total_subjects,
        total_topics=total_topics,
        total_questions=total_questions,
        class_xi_subjects=class_xi_subjects,
        class_xii_subjects=class_xii_subjects,
        show_class_popup=show_class_popup,
        student_class=student_class,
        teacher_custom_tests=teacher_custom_tests
    )


@bp.route('/subjects/<class_level>')
def subjects(class_level):
    """Show subjects for a specific class"""
    if class_level not in ['XI', 'XII']:
        return "Invalid class level", 404
    
    subjects = Subject.query.filter_by(class_level=class_level).all()
    return render_template('main/subjects.html', 
                         subjects=subjects, 
                         class_level=class_level)

@bp.route('/topics/<int:subject_id>')
def topics(subject_id):
    """Show topics for a specific subject"""
    subject = Subject.query.get_or_404(subject_id)
    topics = Topic.query.filter_by(subject_id=subject_id).all()
    
    # Add question count for each topic
    for topic in topics:
        topic.question_count = Question.query.filter_by(topic_id=topic.id).count()
    
    return render_template('main/topics.html', 
                         subject=subject, 
                         topics=topics)

@bp.route('/about')
def about():
    """About page"""
    return render_template('main/about.html')

@bp.route('/help')
def help():
    """Help and FAQ page"""
    return render_template('main/help.html')

# --------------------------
# Update Class (Modify or Set)
# --------------------------
@bp.route('/update_class', methods=['POST'])
@login_required
def update_class():
    """Update an existing class level or create a new one"""
    import logging
    logging.warning(f"update_class: request.data={request.data}")
    data = request.get_json(force=True, silent=True)
    if not data:
        logging.warning("update_class: No JSON data received")
        return jsonify({'success': False, 'message': 'Missing class_level'}), 200
    class_level = data.get('class_level')
    logging.warning(f"update_class: class_level={class_level}")
    if not class_level:
        return jsonify({'success': False, 'message': 'Missing class_level'}), 200
    if class_level not in ['XI','XII']:
        return jsonify({'success': False, 'message': 'Invalid class level'}), 200
    student_class = StudentClass.query.filter_by(user_id=current_user.id).first()
    if student_class:
        student_class.class_level = class_level
    else:
        new_sc = StudentClass(user_id=current_user.id, class_level=class_level)
        db.session.add(new_sc)
    db.session.commit()
    return jsonify({'success': True}), 200
@bp.app_context_processor
def inject_student_class():
    student_class = None
    if current_user.is_authenticated and getattr(current_user, 'role', None) == 'student':
        student_class = get_student_class(current_user.id)
    return dict(student_class=student_class)