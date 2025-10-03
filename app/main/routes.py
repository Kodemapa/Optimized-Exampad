"""
Main Blueprint Routes - Dashboard and home pages
"""

import json
import os
import re
import time
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.main import bp
from app.models import Subject, Topic, Question, require_student_access, db
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
@require_student_access('browse_class')
def subjects(class_level):
    """Show subjects for a specific class"""
    if class_level not in ['XI', 'XII']:
        return "Invalid class level", 404
    
    subjects = Subject.query.filter_by(class_level=class_level).all()
    return render_template('main/subjects.html', 
                         subjects=subjects, 
                         class_level=class_level)

@bp.route('/topics/<int:subject_id>')
@require_student_access('browse_class')
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
@bp.route('/student-access')
@login_required
def student_access():
    """Student Access page for superadmin"""
    from app.models import User
    from flask import flash
    
    # Check if current user is superadmin
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    return render_template('main/student_access.html')

@bp.route('/teacher_access')
@login_required
def teacher_access():
    """Teacher Access page for superadmin"""
    from app.models import User
    from flask import flash
    
    # Check if current user is superadmin
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    return render_template('main/teacher_access.html')

@bp.app_context_processor
def inject_student_class():
    student_class = None
    if current_user.is_authenticated and getattr(current_user, 'role', None) == 'student':
        student_class = get_student_class(current_user.id)
    return dict(student_class=student_class)


# Data Upload Routes for SuperAdmin
UPLOAD_FOLDER = 'uploads'

@bp.route('/data-upload')
@login_required
def data_upload():
    """Data upload page for superadmin"""
    # Check if current user is superadmin
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Get all subjects with their class organization
    subjects = Subject.query.all()
    
    # Fixed Class XI subjects
    xi_names = ['mathematics', 'physics', 'chemistry', 'biology']
    xi_subjects = []
    xii_subjects = []
    xi_ids = set()
    
    # Place Class XI subjects in fixed order
    for name in xi_names:
        for subject in subjects:
            if subject.name.strip().lower() == name:
                xi_subjects.append(subject)
                xi_ids.add(subject.id)
                break
    
    # All other subjects go to Class XII
    for subject in subjects:
        if subject.id not in xi_ids:
            xii_subjects.append(subject)
    
    # Get topics for each subject (convert to serializable format)
    subject_topics = {}
    for subject in subjects:
        topic_list = Topic.query.filter_by(subject_id=subject.id).all()
        subject_topics[subject.id] = topic_list
    
    return render_template('main/data_upload.html', 
                         subjects=subjects, 
                         subject_topics=subject_topics, 
                         xi_subjects=xi_subjects, 
                         xii_subjects=xii_subjects)

@bp.route('/data-upload/topics/<int:subject_id>')
@login_required
def get_topics_for_upload(subject_id):
    """Get topics for a subject (AJAX endpoint)"""
    if current_user.role != 'superadmin':
        return jsonify({'error': 'Access denied'}), 403
    
    topics = Topic.query.filter_by(subject_id=subject_id).all()
    return jsonify({'topics': [(t.id, t.name) for t in topics]})

@bp.route('/data-upload/upload', methods=['POST'])
@login_required
def upload_questions():
    """Upload questions from JSON files"""
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        files = request.files.getlist('jsonfile')
        subject_id = request.form['subject']
        topic_id = request.form.get('topic')
        new_topic = request.form.get('new_topic')

        if not files or all(file.filename == '' for file in files):
            flash('No files selected!', 'error')
            return redirect(url_for('main.data_upload'))

        # Create upload directory if it doesn't exist
        upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', UPLOAD_FOLDER)
        os.makedirs(upload_dir, exist_ok=True)

        # Add new topic if provided
        if new_topic:
            topic = Topic(name=new_topic, subject_id=subject_id)
            db.session.add(topic)
            db.session.commit()
            topic_id = topic.id

        # Get topic and subject names for the success message
        topic = Topic.query.get(topic_id)
        subject = Subject.query.get(subject_id)
        topic_name = topic.name if topic else "Unknown Topic"
        subject_name = subject.name if subject else "Unknown Subject"

        total_questions_added = 0
        processed_files = 0
        failed_files = []

        # Process each file
        for file in files:
            if file.filename == '':
                continue
                
            try:
                # Save and parse JSON
                filepath = os.path.join(upload_dir, file.filename)
                file.save(filepath)
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Try different JSON structures
                questions = None
                if 'result' in data and 'data' in data['result'] and 'sec_questions' in data['result']['data']:
                    questions = data['result']['data']['sec_questions']
                elif 'sec_questions' in data:
                    questions = data['sec_questions']
                elif 'questions' in data:
                    questions = data['questions']
                elif isinstance(data, list):
                    questions = data
                else:
                    questions = []

                if questions is None:
                    questions = []

                # Helper function to fix URLs
                def fix_urls(text):
                    """Fix URLs that start with static/ by prepending https://kampusly.in/"""
                    if not text or not isinstance(text, str):
                        return text
                    # Replace static/ URLs with https://kampusly.in/static/
                    # This handles various formats like src="static/...", href="static/...", etc.
                    pattern = r'(["\'])(static/[^"\']*)\1'
                    replacement = r'\1https://kampusly.in/\2\1'
                    
                    # Also handle URLs without quotes (though less common)
                    text = re.sub(pattern, replacement, text)
                    
                    # Handle cases where static/ appears at the beginning of a line or after whitespace
                    pattern2 = r'\bstatic/([^\s<>"\']*)'
                    replacement2 = r'https://kampusly.in/static/\1'
                    text = re.sub(pattern2, replacement2, text)
                    
                    return text
                
                # Insert questions
                questions_added = 0
                skipped_questions = 0
                
                for i, q in enumerate(questions):
                    if not q or len(q) < 3 or not q[2]: 
                        continue
                    
                    # Fix URLs in question text
                    question_text = fix_urls(q[2])
                    
                    # Process options - convert numbers to letters
                    raw_options = q[3] if len(q) > 3 and q[3] else []
                    processed_options = {}
                    
                    if isinstance(raw_options, list):
                        # Convert list of options to A,B,C,D format
                        option_letters = ['A', 'B', 'C', 'D']
                        for idx, option in enumerate(raw_options[:4]):  # Only take first 4 options
                            if idx < len(option_letters):
                                # Fix URLs in option text
                                processed_options[option_letters[idx]] = fix_urls(option)
                    elif isinstance(raw_options, dict):
                        # Convert numeric keys to letters
                        option_letters = ['A', 'B', 'C', 'D']
                        numeric_keys = ['1', '2', '3', '4']
                        
                        for i, letter in enumerate(option_letters):
                            numeric_key = str(i + 1)
                            if numeric_key in raw_options:
                                # Fix URLs in option text
                                processed_options[letter] = fix_urls(raw_options[numeric_key])
                            elif numeric_keys[i] in raw_options:
                                # Fix URLs in option text
                                processed_options[letter] = fix_urls(raw_options[numeric_keys[i]])
                    
                    options = json.dumps(processed_options) if processed_options else None
                    
                    # Handle correct_answer - convert to letters and validate
                    correct_answer = None
                    if len(q) > 4 and q[4] and len(q[4]) > 0:
                        try:
                            # Get the answer index/value
                            answer_value = q[4][0]
                            
                            # If it's a number, convert to letter
                            if isinstance(answer_value, (int, str)):
                                answer_num = int(answer_value)
                                
                                # Skip questions with answers > 4 (invalid)
                                if answer_num > 4 or answer_num < 1:
                                    skipped_questions += 1
                                    continue
                                
                                # Convert 1,2,3,4 to A,B,C,D
                                option_letters = ['A', 'B', 'C', 'D']
                                correct_answer = option_letters[answer_num - 1]
                            else:
                                # If already a letter, validate it
                                if str(answer_value).upper() in ['A', 'B', 'C', 'D']:
                                    correct_answer = str(answer_value).upper()
                                else:
                                    skipped_questions += 1
                                    continue
                        except (ValueError, TypeError, IndexError):
                            skipped_questions += 1
                            continue
                    else:
                        skipped_questions += 1
                        continue
                    
                    # Fix URLs in explanation text
                    explanation = fix_urls(q[6]) if len(q) > 6 and q[6] else None
                    
                    # Generate unique qid
                    timestamp = str(int(time.time() * 1000))
                    base_filename = os.path.splitext(file.filename)[0]
                    qid = f"{base_filename}_{i+1}_{timestamp}"
                    
                    # Check if qid already exists and make it unique
                    original_qid = qid
                    counter = 1
                    while True:
                        existing = Question.query.filter_by(qid=qid).first()
                        if not existing:
                            break
                        qid = f"{original_qid}_{counter}"
                        counter += 1
                    
                    try:
                        question = Question(
                            qid=qid,
                            question_text=question_text,
                            options=options,
                            correct_answer=correct_answer,
                            explanation=explanation,
                            topic_id=topic_id
                        )
                        db.session.add(question)
                        questions_added += 1
                    except Exception as e:
                        print(f"Error inserting question {i+1} from {file.filename}: {e}")
                        continue
                
                db.session.commit()
                
                # Clean up uploaded file
                os.remove(filepath)
                
                total_questions_added += questions_added
                processed_files += 1
                
                # Add skipped questions info to the file processing summary
                if skipped_questions > 0:
                    failed_files.append(f"{file.filename}: {skipped_questions} questions skipped (invalid answers)")
                
            except Exception as e:
                failed_files.append(f"{file.filename}: {str(e)}")
                # Clean up file if it exists
                if os.path.exists(filepath):
                    os.remove(filepath)

        # Create success/error message
        if processed_files > 0:
            message = f'Successfully processed {processed_files} file(s) and added {total_questions_added} questions to "{topic_name}" under "{subject_name}" subject!'
            if failed_files:
                message += f' Failed files: {", ".join(failed_files)}'
            flash(message, 'success')
        else:
            flash(f'Failed to process any files. Errors: {", ".join(failed_files)}', 'error')
        
    except Exception as e:
        flash(f'Error processing files: {str(e)}', 'error')
    
    return redirect(url_for('main.data_upload'))

@bp.route('/data-upload/delete-subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    """Delete a subject and all its topics/questions"""
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Delete all topics and questions under this subject
        topics = Topic.query.filter_by(subject_id=subject_id).all()
        for topic in topics:
            Question.query.filter_by(topic_id=topic.id).delete()
        Topic.query.filter_by(subject_id=subject_id).delete()
        Subject.query.filter_by(id=subject_id).delete()
        db.session.commit()
        flash('Subject deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting subject: {str(e)}', 'error')
    
    return redirect(url_for('main.data_upload'))

@bp.route('/data-upload/delete-topic/<int:topic_id>', methods=['POST'])
@login_required
def delete_topic(topic_id):
    """Delete a topic and all its questions"""
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        Question.query.filter_by(topic_id=topic_id).delete()
        Topic.query.filter_by(id=topic_id).delete()
        db.session.commit()
        flash('Topic deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting topic: {str(e)}', 'error')
    
    return redirect(url_for('main.data_upload'))

@bp.route('/data-upload/edit-topic/<int:topic_id>', methods=['POST'])
@login_required
def edit_topic(topic_id):
    """Edit a topic name"""
    if current_user.role != 'superadmin':
        flash('Access denied. Superadmin role required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    new_name = request.form.get('new_name')
    if not new_name:
        flash('No new name provided for topic!', 'error')
        return redirect(url_for('main.data_upload'))
    
    try:
        topic = Topic.query.get(topic_id)
        if topic:
            topic.name = new_name
            db.session.commit()
            flash('Topic name updated successfully!', 'success')
        else:
            flash('Topic not found!', 'error')
    except Exception as e:
        db.session.rollback()
        flash(f'Error editing topic: {str(e)}', 'error')
    
    return redirect(url_for('main.data_upload'))